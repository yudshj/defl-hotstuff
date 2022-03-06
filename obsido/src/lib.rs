use std::error::Error;
use std::net::SocketAddr;
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use bytes::Bytes;
use futures::sink::SinkExt as _;
use log::{debug, info, warn};
use prost::Message;
use tokio::sync::mpsc::{channel, Receiver, Sender};

use network::{MessageHandler, Receiver as NetworkReceiver, Writer};
use proto::defl::{ObsidoRequest, WeightsResponse};
use proto::defl::obsido_request::Method;
use proto::defl_sender::DeflSender;
use proto::DeflDatabank;

pub const CHANNEL_CAPACITY: usize = 1_000;


/// Defines how the network receiver handles incoming transactions.
#[derive(Clone)]
struct TxReceiverHandler {
    tx_filter: Sender<Vec<u8>>,
}

#[async_trait]
impl MessageHandler for TxReceiverHandler {
    async fn dispatch(&self, writer: &mut Writer, message: Bytes) -> Result<(), Box<dyn Error>> {
        debug!("Sending Ack to client");
        // Immediate response to the client.
        let _ = writer.send(Bytes::from("Ack")).await;

        // Send the transaction to the batch maker.
        self.tx_filter
            .send(message.to_vec())
            .await
            .expect("Failed to send transaction");

        // Give the change to schedule other tasks.
        tokio::task::yield_now().await;
        Ok(())
    }
}

pub struct ObsidoHandler {
    rx_filter: Receiver<Vec<u8>>,
    defl_sender: DeflSender,
    defl_databank: Arc<Mutex<DeflDatabank>>,
}

impl ObsidoHandler {
    pub fn spawn(
        defl_sender: DeflSender,
        defl_databank: Arc<Mutex<DeflDatabank>>,
        rx_filter: Receiver<Vec<u8>>,
    ) {
        tokio::spawn(async move {
            Self {
                defl_sender,
                defl_databank,
                rx_filter,
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
                    ObsidoRequest::decode(Bytes::from(transaction.clone())).unwrap();
                let ObsidoRequest {
                    method,
                    request_uuid,
                    client_name,
                    register_info,
                } = client_request;
                info!("filtering transactions {}", &request_uuid);
                Method::FetchWLast as i32;
                match Method::from_i32(method) {
                    Some(Method::FetchWLast) => {
                        let defl_databank = self.defl_databank.lock().unwrap().clone();
                        let response_uuid = uuid::Uuid::new_v4().to_string();
                        let response = WeightsResponse {
                            request_uuid: Some(request_uuid.clone()),
                            response_uuid: response_uuid.clone(),
                            w_last: defl_databank.client_weights,
                            r_last_epoch_id: defl_databank.epoch_id,
                        };
                        match self.defl_sender
                            .respond_to_all_client(response)
                            .await
                        {
                            Ok(len) => info!(
                                "Responded FETCH_W_LAST [{}]\tepoch_id={}\tbytes={}\trequest_uuid={}\tresponse_uuid={}",
                                client_name, defl_databank.epoch_id, len, request_uuid, response_uuid
                            ),
                            Err(_) => warn!("Failed to respond FETCH_W_LAST [{}].", client_name),
                        }
                    }
                    Some(Method::ClientRegister) => {
                        if let Some(register_info) = register_info {
                            info!("Registering client {}", &client_name);
                            self.defl_sender
                                .client_register(client_name, register_info.into())
                                .await;
                        }
                    }
                    None => {
                        warn!("Invalid obsido request method!");
                    }
                }
            }

            // Give the change to schedule other tasks.
            tokio::task::yield_now().await;
        }
    }
}


pub struct Obsido;

impl Obsido {
    pub fn spawn(
        obsido_port: u16,
        defl_sender: DeflSender,
        defl_databank: Arc<Mutex<DeflDatabank>>,
    ) {
        let (tx_filter, rx_filter) = channel(CHANNEL_CAPACITY);


        // We first receive clients' transactions from the network.
        let address: SocketAddr = SocketAddr::new("127.0.0.1".parse().unwrap(), obsido_port);
        NetworkReceiver::spawn(address, /* handler */ TxReceiverHandler { tx_filter });

        ObsidoHandler::spawn(defl_sender, defl_databank, rx_filter);

        info!("Obsido listening to client transactions on {}", address);
    }
}