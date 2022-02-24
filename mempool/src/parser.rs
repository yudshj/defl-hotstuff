use serde::{Deserialize, Serialize};
use byteorder::{BigEndian, ByteOrder};
use bytes::{BufMut, BytesMut};

#[derive(PartialEq, Debug)]
pub enum RequestMethod {
    FetchWLast,
    NewWeights,
    NewEpoch,
}

impl Serialize for RequestMethod {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
        where
            S: serde::Serializer,
    {
        serializer.serialize_u8(match self {
            RequestMethod::FetchWLast => 0,
            RequestMethod::NewWeights => 1,
            RequestMethod::NewEpoch => 2,
        })
    }
}

impl<'de> Deserialize<'de> for RequestMethod {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
        where
            D: serde::Deserializer<'de>,
    {
        let method = u8::deserialize(deserializer)?;
        match method {
            0 => Ok(RequestMethod::FetchWLast),
            1 => Ok(RequestMethod::NewWeights),
            2 => Ok(RequestMethod::NewEpoch),
            _ => Err(serde::de::Error::custom("invalid method")),
        }
    }
}

#[derive(Serialize, Deserialize, PartialEq, Debug)]
pub struct MetaInfo {
    pub method: RequestMethod,
    pub listen_host: String,
    pub listen_port: u16,
    pub uuid: String,
    pub client_name: String,
    pub target_epoch_id: i64,
}

pub struct ClientRequest {
    pub meta: MetaInfo,
    pub weights: Vec<u8>,
}

impl From<&Vec<u8>> for ClientRequest {
    fn from(item: &Vec<u8>) -> Self {
        let slice = item.as_slice();
        let json_length = BigEndian::read_u32(slice);
        let json_index = json_length as usize + 4;
        let json_slice = &slice[4..json_index];
        let meta: MetaInfo = serde_json::from_slice(json_slice).unwrap();
        let weights_slice = &slice[json_index..];
        let weights = weights_slice.to_vec();
        ClientRequest {
            meta,
            weights,
        }
    }
}

impl Into<Vec<u8>> for ClientRequest {
    fn into(self) -> Vec<u8> {
        let meta_json = serde_json::to_vec(&self.meta).unwrap();
        let meta_length = meta_json.len();
        let mut buf = BytesMut::with_capacity(meta_length + self.weights.len() + 4);
        buf.put_u32(meta_length as u32);
        buf.put_slice(meta_json.as_slice());
        buf.put_slice(self.weights.as_slice());
        buf.freeze().to_vec()
    }
}


#[cfg(test)]
mod tests {
    use log::info;
    use crate::parser::*;

    #[test]
    fn it_works() {
        env_logger::init();
        let meta = MetaInfo {
            method: RequestMethod::FetchWLast,
            listen_host: "127.0.0.1".to_string(),
            listen_port: 8080,
            uuid: "uuid".to_string(),
            client_name: "client_name".to_string(),
            target_epoch_id: 1,
        };
        let weights = vec![1, 2, 3, 4];
        let request = ClientRequest {
            meta,
            weights,
        };
        let bytes: Vec<u8> = request.into();
        info!("{:?}", base64::encode(&bytes));
        let request = ClientRequest::from(&bytes);
        assert_eq!(request.meta.method, RequestMethod::FetchWLast);
    }
}