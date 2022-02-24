use std::sync::{Arc, Mutex};
use bytes::Bytes;
use log::info;
use proto::{ContactsType, WLastType};
use crate::batch_maker::Transaction;
use tokio::sync::mpsc::{Receiver, Sender};
use proto::defl::{ClientRequest, RequestMethod, Response};
use prost::Message;

pub struct TransactionFilter {
    contacts: Arc<Mutex<ContactsType>>,
    w_last: Arc<Mutex<WLastType>>,
    rx_filter: Receiver<Transaction>,
    tx_batch_maker: Sender<Transaction>,
}

impl TransactionFilter {
    pub fn spawn(
        contacts: Arc<Mutex<ContactsType>>,
        w_last: Arc<Mutex<WLastType>>,
        rx_filter: Receiver<Transaction>,
        tx_batch_maker: Sender<Transaction>,
    ) {
        tokio::spawn(async move {
            Self {
                contacts,
                w_last,
                rx_filter,
                tx_batch_maker,
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
                let client_request = ClientRequest::decode(Bytes::from(transaction.clone())).unwrap();
                match RequestMethod::from_i32(client_request.method) {
                    Some(RequestMethod::FetchWLast) => {
                        // info!("DONG:");
                        if let Some((host, port)) = self.contacts.lock().unwrap().get(&client_request.client_name) {
                            let response = Response {
                                msg: String::from("OK"),
                                w_last: self.w_last.lock().unwrap().clone(),
                            };
                            // let buf = BytesMut::with_capacity(response.encoded_len());
                            // response.encode(&mut buf).unwrap();
                            info!("DONG: will send {} bytes to {} - {}:{}", response.encoded_len(), client_request.client_name, host, port);
                        }
                        // TODO!!!: Send `w_last` to the client
                    }
                    Some(RequestMethod::ClientRegister) => {
                        // info!("DONG:");
                        if let Some(socket) = client_request.socket {
                            self.contacts.lock().unwrap().insert(client_request.client_name.clone(), (socket.host, socket.port));
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