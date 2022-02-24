use std::collections::HashMap;

pub mod defl {
    include!(concat!(env!("OUT_DIR"), "/defl.rs"));
}

pub type WLastType = HashMap<String, Vec<u8>>;
pub type ContactsType = HashMap<String, (String, i32)>;
