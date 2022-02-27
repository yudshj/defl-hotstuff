use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::Arc;
use std::sync::RwLock;

use prost::Message;
use thiserror::Error;

use network::SimpleSender;

use crate::defl::Response;
use crate::SimpleRegisterInfo;

#[derive(Error, Debug)]
pub enum RespondError {
    #[error("Client {client_name} not registered")]
    NotRegisteredError {
        client_name: String,
    },

    #[error("Failed to send some data to client {client_name} due to network error.")]
    NetworkError {
        client_name: String,
    },
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
        let host;
        let port;
        if let Some(register_info) = self.contacts.read().unwrap().get(&client_name) {
            host = register_info.host.clone();
            port = register_info.port.clone();
        } else {
            return Err(RespondError::NotRegisteredError { client_name });
        }
        let data: Vec<u8> = response.encode_to_vec();
        let length = data.len();
        let address = SocketAddr::new(host.parse().unwrap(), port);
        if self.sender.send(address, data.into()).await {
            Ok(length)
        } else {
            Err(RespondError::NetworkError { client_name })
        }
    }

    pub async fn client_register(
        &mut self,
        client_name: String,
        register_info: SimpleRegisterInfo,
    ) {
        self.contacts.write().unwrap().insert(client_name, register_info);
    }
}
