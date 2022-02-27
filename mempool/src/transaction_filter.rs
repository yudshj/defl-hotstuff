use std::sync::{Arc, Mutex};

use bytes::Bytes;
use log::{info, warn};
use prost::Message;
use tokio::sync::mpsc::{Receiver, Sender};

use proto::defl::{ClientRequest, Response};
use proto::defl::client_request::Method;
use proto::defl::response::Status;
use proto::defl_sender::DeflSender;
use proto::DeflDatabank;

use crate::batch_maker::Transaction;

pub struct TransactionFilter {
    defl_databank: Arc<Mutex<DeflDatabank>>,
    rx_filter: Receiver<Transaction>,
    tx_batch_maker: Sender<Transaction>,
}

impl TransactionFilter {
    pub fn spawn(
        defl_sender: DeflSender,
        defl_databank: Arc<Mutex<DeflDatabank>>,
        rx_filter: Receiver<Transaction>,
        tx_batch_maker: Sender<Transaction>,
    ) {
        tokio::spawn(async move {
            Self {
                defl_databank,
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
                info!("filtering transactions {}", request_uuid.clone());
                match Method::from_i32(method) {
                    Some(Method::FetchWLast) => {
                        let defl_databank = self.defl_databank.lock().unwrap().clone();
                        let response = Response {
                            stat: Status::Ok.into(),
                            request_uuid,
                            response_uuid: uuid::Uuid::new_v4().to_string(),
                            w_last: defl_databank.client_weights,
                            r_last_epoch_id: Option::from(defl_databank.epoch_id),
                        };
                        let request_uuid = response.request_uuid.clone();
                        match defl_sender
                            .respond_to_client(client_name.clone(), response)
                            .await
                        {
                            Ok(len) => info!(
                                "Responded FETCH_W_LAST [{}]\tepoch_id={}\tbytes={}\trequest_uuid={}",
                                client_name, defl_databank.epoch_id, len, request_uuid
                            ),
                            Err(_) => warn!("Failed to respond FETCH_W_LAST [{}].", client_name),
                        }
                    },
                    Some(Method::ClientRegister) => {
                        if let Some(register_info) = register_info {
                            info!("Registering client {}", &client_name);
                            defl_sender
                                .client_register(client_name, register_info.into())
                                .await;
                        }
                    },
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
