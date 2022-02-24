use std::io::Cursor;
use prost::Message;

pub mod defl {
    include!(concat!(env!("OUT_DIR"), "/defl.rs"));
}

pub fn deserialize_client_request(buf: &[u8]) -> Result<defl::ClientRequest, prost::DecodeError> {
    defl::ClientRequest::decode(&mut Cursor::new(buf))
}