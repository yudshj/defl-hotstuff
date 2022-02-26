use std::sync::{Arc, Mutex};

use bytes::Bytes;
use log::{info, warn};
use prost::Message;
use tokio::sync::mpsc::{Receiver, Sender};

use proto::defl::{ClientRequest, Response};
use proto::defl::client_request::Method;
use proto::defl::response::Status;
use proto::defl_sender::DeflSender;
use proto::NodeInfo;

use crate::batch_maker::Transaction;

pub struct TransactionFilter {
    node_info: Arc<Mutex<NodeInfo>>,
    rx_filter: Receiver<Transaction>,
    tx_batch_maker: Sender<Transaction>,
}

impl TransactionFilter {
    pub fn spawn(
        defl_sender: DeflSender,
        node_info: Arc<Mutex<NodeInfo>>,
        rx_filter: Receiver<Transaction>,
        tx_batch_maker: Sender<Transaction>,
    ) {
        tokio::spawn(async move {
            Self {
                node_info,
                rx_filter,
                tx_batch_maker,
            }
                .run(defl_sender)
                .await;
        });
    }

    async fn run(&mut self, mut defl_sender: DeflSender) {
        loop {
            // Assemble client transactions into batches of preset size.
            if let Some(transaction) = self.rx_filter.recv().await {
                // Filter out transactions
                let client_request =
                    ClientRequest::decode(Bytes::from(transaction.clone())).unwrap();
                let ClientRequest {
                    method,
                    request_uuid,
                    client_name,
                    target_epoch_id: _,
                    weights: _,
                    register_info,
                } = client_request;
                match Method::from_i32(method) {
                    Some(Method::FetchWLast) => {
                        let node_info = self.node_info.lock().unwrap().clone();
                        let response = Response {
                            stat: Status::Ok.into(),
                            request_uuid,
                            w_last: node_info.client_weights,
                            r_last_epoch_id: Option::from(node_info.epoch_id),
                        };
                        match defl_sender
                            .respond_to_client(client_name.clone(), response)
                            .await
                        {
                            Ok(_) => info!("Respond FETCH_W_LAST client={} epoch_id={}", client_name, node_info.epoch_id),
                            Err(_) => warn!("Failed to respond `w_last` to client {}", client_name),
                        }
                    }
                    Some(Method::ClientRegister) => {
                        if let Some(register_info) = register_info {
                            defl_sender
                                .client_register(client_name, register_info.into())
                                .await;
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
