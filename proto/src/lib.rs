use std::collections::HashMap;

pub mod defl_sender;

pub mod defl {
    include!(concat!(env!("OUT_DIR"), "/defl.rs"));
}

#[derive(Clone, PartialEq, Debug)]
pub struct SimpleRegisterInfo {
    pub host: String,
    pub port: u16,
    pub pasv_host: String,
    pub pasv_port: u16,
}

impl Into<SimpleRegisterInfo> for defl::RegisterInfo {
    fn into(self) -> SimpleRegisterInfo {
        SimpleRegisterInfo {
            host: self.host,
            port: self.port as u16,
            pasv_host: self.pasv_host,
            pasv_port: self.pasv_port as u16,
        }
    }
}

pub type ClientWeightsType = HashMap<String, Vec<u8>>;

#[derive(Debug, Clone)]
pub struct DeflDatabank {
    pub client_weights: ClientWeightsType,
    pub epoch_id: i64,
}

impl DeflDatabank {
    pub fn new(init_epoch_id: i64) -> DeflDatabank {
        DeflDatabank {
            client_weights: HashMap::new(),
            epoch_id: init_epoch_id,
        }
    }
}
