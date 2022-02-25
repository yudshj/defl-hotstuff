use std::collections::HashMap;

pub mod defl {
    include!(concat!(env!("OUT_DIR"), "/defl.rs"));
}

#[derive(Clone, PartialEq, Debug)]
pub struct RegisterInfo {
    pub host: String,
    pub port: u16,
    pub pasv_host: String,
    pub pasv_port: u16,
}

impl Into<RegisterInfo> for defl::RegisterInfo {
    fn into(self) -> RegisterInfo {
        RegisterInfo {
            host: self.host,
            port: self.port as u16,
            pasv_host: self.pasv_host,
            pasv_port: self.pasv_port as u16,
        }
    }
}

pub type WLastType = HashMap<String, Vec<u8>>;
pub type ContactsType = HashMap<String, RegisterInfo>;
