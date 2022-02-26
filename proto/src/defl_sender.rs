use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use prost::Message;

use network::SimpleSender;

use crate::defl::Response;
use crate::SimpleRegisterInfo;

#[derive(Debug, Clone)]
pub struct RespondError {
    pub msg: String,
}

pub struct DeflSender {
    pub contacts: Arc<Mutex<HashMap<String, SimpleRegisterInfo>>>,
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
            contacts: Arc::new(Mutex::new(HashMap::new())),
            sender: SimpleSender::new(),
        }
    }

    pub async fn respond_to_client(
        &mut self,
        client_name: String,
        response: Response,
    ) -> Result<(), RespondError> {
        let host;
        let port;
        if let Some(register_info) = self.contacts.lock().unwrap().get(&client_name) {
            host = register_info.host.clone();
            port = register_info.port.clone();
        } else {
            return Err(RespondError {
                msg: String::from("not registered"),
            });
        }
        let data: Vec<u8> = response.encode_to_vec();
        let address = SocketAddr::new(host.parse().unwrap(), port);
        self.sender.send(address, data.into()).await;
        Ok(())
    }

    pub async fn client_register(
        &mut self,
        client_name: String,
        register_info: SimpleRegisterInfo,
    ) {
        self.contacts
            .lock()
            .unwrap()
            .insert(client_name, register_info);
    }
}
