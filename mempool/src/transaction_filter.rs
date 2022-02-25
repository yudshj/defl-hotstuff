use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use bytes::Bytes;
use log::info;
use prost::Message;
use tokio::sync::mpsc::{Receiver, Sender};

use network::SimpleSender;
use proto::{ContactsType, WLastType};
use proto::defl::{ClientRequest, Response};
use proto::defl::client_request::Method;
use proto::defl::response::Status;

use crate::batch_maker::Transaction;

pub struct TransactionFilter {
    contacts: Arc<Mutex<ContactsType>>,
    w_last: Arc<Mutex<WLastType>>,
    rx_filter: Receiver<Transaction>,
    tx_batch_maker: Sender<Transaction>,
    sender: SimpleSender,
}

impl TransactionFilter {
    pub fn spawn(
        contacts: Arc<Mutex<ContactsType>>,
        w_last: Arc<Mutex<WLastType>>,
        rx_filter: Receiver<Transaction>,
        tx_batch_maker: Sender<Transaction>,
        sender: SimpleSender,
    ) {
        tokio::spawn(async move {
            Self {
                contacts,
                w_last,
                rx_filter,
                tx_batch_maker,
                sender,
            }
                .run()
                .await;
        });
    }

    async fn run(&mut self) {
        loop {
            // Assemble client transactions into batches of preset size.
            if let Some(transaction) = self.rx_filter.recv().await {
                // Filter out transactions
                let client_request =
                    ClientRequest::decode(Bytes::from(transaction.clone())).unwrap();
                match Method::from_i32(client_request.method) {
                    Some(Method::FetchWLast) => {
                        let host;
                        let port;
                        if let Some(register_info) = self
                            .contacts
                            .lock()
                            .unwrap()
                            .get(&client_request.client_name)
                        {
                            host = register_info.host.clone();
                            port = register_info.port.clone();
                        } else {
                            info!("{} is not registered", client_request.client_name);
                            continue;
                        }
                        let response = Response {
                            stat: Status::Ok.into(),
                            request_uuid: client_request.request_uuid,
                            w_last: self.w_last.lock().unwrap().clone().into(),
                        };

                        let data = response.encode_to_vec();
                        let address = SocketAddr::new(host.parse().unwrap(), port);
                        self.sender.send(address, Bytes::from(data)).await;
                        info!(
                            "DONG: sent {} bytes to {} - {}:{}",
                            response.encoded_len(),
                            client_request.client_name,
                            host,
                            port
                        );
                    }
                    Some(Method::ClientRegister) => {
                        // info!("DONG:");
                        if let Some(register_info) = client_request.register_info {
                            self.contacts
                                .lock()
                                .unwrap()
                                .insert(client_request.client_name.clone(), register_info.into());
                            info!("DONG: client {} registered", client_request.client_name);
                            info!("DONG: {:?}", self.contacts.lock().unwrap().clone());
                        }
                    }
                    _ => {
                        self.tx_batch_maker.send(transaction).await.unwrap();
                    }
                }
            }

            // Give the change to schedule other tasks.
            tokio::task::yield_now().await;
        }
    }
}
