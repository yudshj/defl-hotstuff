use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, PoisonError};
use std::sync::RwLock;

use prost::Message;
use thiserror::Error;

use network::SimpleSender;

use crate::defl::{Response, WeightsResponse};
use crate::defl_sender::RespondError::ContactsLockPoisonError;
use crate::SimpleRegisterInfo;

#[derive(Error, Debug)]
pub enum RespondError {
    #[error("Client {client_name} not registered")]
    RegistrationError { client_name: String },

    #[error("Failed to send some data to client {client_name} due to network error.")]
    NetworkError { client_name: String },

    #[error("R/w contacts error.")]
    ContactsLockPoisonError,
}

impl<T> From<PoisonError<T>> for RespondError {
    fn from(_: PoisonError<T>) -> Self {
        ContactsLockPoisonError
    }
}

pub struct DeflSender {
    pub contacts: Arc<RwLock<HashMap<String, SimpleRegisterInfo>>>,
    pub sender: SimpleSender,
}

impl Clone for DeflSender {
    fn clone(&self) -> Self {
        DeflSender {
            contacts: self.contacts.clone(),
            sender: SimpleSender::new(),
        }
    }
}

impl DeflSender {
    pub fn new() -> Self {
        DeflSender {
            contacts: Arc::new(RwLock::new(HashMap::new())),
            sender: SimpleSender::new(),
        }
    }

    /// Returns the bytes of the response if successful, otherwise returns an error.
    pub async fn respond_to_client(
        &mut self,
        client_name: String,
        response: Response,
    ) -> Result<usize, RespondError> {
        let SimpleRegisterInfo {
            host,
            port,
            pasv_host: _,
            pasv_port: _,
        } = self
            .contacts
            .read()?
            .get(&client_name)
            .ok_or(RespondError::RegistrationError {
                client_name: client_name.clone(),
            })?
            .clone();
        let data: Vec<u8> = response.encode_to_vec();
        let length = data.len();
        let address = SocketAddr::new(host.parse().unwrap(), port);
        if self.sender.send(address, data.into()).await {
            Ok(length)
        } else {
            Err(RespondError::NetworkError { client_name })
        }
    }

    /// Returns the bytes of the response if successful, otherwise returns an error.
    pub async fn respond_to_all_client(
        &mut self,
        response: WeightsResponse,
    ) -> Result<usize, RespondError> {
        let contacts = self.contacts.read()?.clone();
        let data: Vec<u8> = response.encode_to_vec();
        let length = data.len();
        for (_, SimpleRegisterInfo { pasv_host, pasv_port, host: _host, port: _port }) in contacts {
            let address = SocketAddr::new(pasv_host.parse().unwrap(), pasv_port);
            self.sender.send(address, data.clone().into()).await;
        }
        Ok(length)
    }

    pub async fn client_register(
        &mut self,
        client_name: String,
        register_info: SimpleRegisterInfo,
    ) {
        self.contacts
            .write()
            .unwrap()
            .insert(client_name, register_info);
    }
}
