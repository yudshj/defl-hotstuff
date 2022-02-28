use std::collections::HashSet;
use std::sync::{Arc, Mutex};

use bytes::Bytes;
use log::{info, warn};
use prost::Message;
use tokio::sync::mpsc::{channel, Receiver};
use uuid::Uuid;

use consensus::{Block, Consensus};
use crypto::SignatureService;
use mempool::{Mempool, MempoolMessage};
use obsido::Obsido;
use proto::defl::*;
// Sync the mempool with the consensus and nodes.
use proto::defl::client_request::Method;
use proto::defl::response::Status;
use proto::defl_sender::{DeflSender, RespondError};
use proto::DeflDatabank;
use store::Store;

use crate::config::{Committee, ConfigError, Parameters, Secret};
use crate::config::Export as _;

/// The default channel capacity for this module.
pub const CHANNEL_CAPACITY: usize = 1_000;

pub struct Node {
    pub commit: Receiver<Block>,
    pub block_store: Store,
    last_defl_databank: Arc<Mutex<DeflDatabank>>,
    cur_defl_databank: DeflDatabank,
    voted_clients: HashSet<String>,
    defl_sender: DeflSender,
    quorum: usize,
}

impl Node {
    pub async fn new(
        committee_file: &str,
        key_file: &str,
        store_path: &str,
        parameters: Option<&str>,
        quorum: usize,
        obsido_port: u16,
    ) -> Result<Self, ConfigError> {
        let (tx_commit, rx_commit) = channel(CHANNEL_CAPACITY);
        let (tx_consensus_to_mempool, rx_consensus_to_mempool) = channel(CHANNEL_CAPACITY);
        let (tx_mempool_to_consensus, rx_mempool_to_consensus) = channel(CHANNEL_CAPACITY);

        // Read the committee and secret key from file.
        let committee = Committee::read(committee_file)?;
        let secret = Secret::read(key_file)?;
        let name = secret.name;
        let secret_key = secret.secret;

        // Load default parameters if none are specified.
        let parameters = match parameters {
            Some(filename) => Parameters::read(filename)?,
            None => Parameters::default(),
        };

        // Make the data store.
        let store = Store::new(store_path).expect("Failed to create store");

        // Make DeFL components.
        let defl_sender = DeflSender::new();
        let cur_defl_databank = DeflDatabank::new(0);
        let last_defl_databank = Arc::new(Mutex::new(DeflDatabank::new(-1)));

        // Run the signature service.
        let signature_service = SignatureService::new(secret_key);

        // Make a new mempool.
        Mempool::spawn(
            name,
            committee.mempool,
            parameters.mempool,
            store.clone(),
            rx_consensus_to_mempool,
            tx_mempool_to_consensus,
        );

        Obsido::spawn(
            obsido_port,
            defl_sender.clone(),
            last_defl_databank.clone(),
        );

        // Run the consensus core.
        Consensus::spawn(
            name,
            committee.consensus,
            parameters.consensus,
            signature_service,
            store.clone(),
            rx_mempool_to_consensus,
            tx_consensus_to_mempool,
            tx_commit,
        );

        info!("Node {} successfully booted", name);
        Ok(Self {
            commit: rx_commit,
            block_store: store,
            last_defl_databank,
            cur_defl_databank,
            voted_clients: HashSet::new(),
            defl_sender,
            quorum,
        })
    }

    pub fn print_key_file(filename: &str) -> Result<(), ConfigError> {
        Secret::new().write(filename)
    }

    pub async fn handle_upd(
        &self,
        target_epoch_id: i64,
        weights: &Option<Vec<u8>>,
    ) -> Result<(), Status> {
        match (target_epoch_id == self.cur_defl_databank.epoch_id, weights) {
            (true, Some(_)) => Ok(()),
            (true, None) => Err(Status::NoWeightsInRequestError),
            (false, _) => Err(Status::UwTargetEpochIdError),
        }
    }

    pub async fn handle_ner(&self, target_epoch_id: i64) -> Result<(), Status> {
        if target_epoch_id == self.cur_defl_databank.epoch_id {
            Ok(())
        } else {
            Err(Status::NerTargetEpochIdError)
        }
    }

    pub async fn get_responses(
        &mut self,
        client_request: ClientRequest,
    ) -> (Response, Option<WeightsResponse>) {
        let ClientRequest {
            method,
            request_uuid,
            client_name,
            target_epoch_id,
            weights,
        } = client_request;
        let mut passive_response = None;
        let stat = match Method::from_i32(method) {
            Some(Method::UpdWeights) => {
                info!("Batch tx: UPD_WEIGHTS");
                match self.handle_upd(target_epoch_id, &weights).await {
                    Ok(()) => {
                        if let Some(_) = self
                            .cur_defl_databank
                            .client_weights
                            .insert(client_name, weights.unwrap())
                        {
                            warn!("UPD_WEIGHTS: client_name already exists, overwriting...");
                        }
                        Status::Ok
                    }
                    Err(status_error) => status_error,
                }
            }
            Some(Method::NewEpochRequest) => {
                info!("Batch tx: NEW_EPOCH_REQUEST.");
                match self.handle_ner(target_epoch_id).await {
                    Ok(()) => {
                        if self.voted_clients.insert(client_name.clone()) {
                            info!("Client [{}] voted.", client_name);

                            // check meet quorum
                            if self.voted_clients.len() < self.quorum {
                                info!(
                                    "Not enough clients voted: {} / {}.",
                                    self.voted_clients.len(),
                                    self.quorum
                                );
                                Status::NotMeetQuorumWait
                            } else {
                                info!(
                                    "Enough clients voted. Total weights: {}.",
                                    self.cur_defl_databank.client_weights.len()
                                );
                                self.cur_defl_databank.client_weights.iter().for_each(
                                    |(client_name, _)| {
                                        info!("    Client [{}].", client_name);
                                    },
                                );
                                passive_response = Some(WeightsResponse {
                                    request_uuid: None,
                                    response_uuid: Uuid::new_v4().to_string(),
                                    r_last_epoch_id: self.cur_defl_databank.epoch_id,
                                    w_last: self.cur_defl_databank.client_weights.clone(),
                                });
                                self.last_defl_databank
                                    .lock()
                                    .unwrap()
                                    .clone_from(&self.cur_defl_databank);
                                self.cur_defl_databank.epoch_id += 1;
                                self.cur_defl_databank.client_weights.clear();
                                self.voted_clients.clear();
                                info!("Entering new epoch.");
                                Status::Ok
                            }
                        } else {
                            warn!("Client [{}] has already voted.", client_name);
                            Status::ClientAlreadyVotedError
                        }
                    }
                    Err(status_error) => status_error,
                }
            }
            _ => {
                warn!("Block should be filtered out previously. Ignoring...");
                Status::ServerInternalError
            }
        };
        info!("Responding {:?} {}", stat, &request_uuid);
        let response = Response {
            stat: stat.into(),
            request_uuid,
            response_uuid: uuid::Uuid::new_v4().to_string(),
        };
        (response, passive_response)
    }

    pub async fn analyze_transaction(&mut self, client_tx: Vec<u8>) {
        let client_request = ClientRequest::decode(Bytes::from(client_tx))
            .expect("Failed to decode client request.");
        let client_name = client_request.client_name.clone();
        let (response, passive_response) = self.get_responses(client_request).await;
        let request_uuid = response.request_uuid.clone();
        match self
            .defl_sender
            .respond_to_client(client_name.clone(), response)
            .await
        {
            Ok(len) => {
                info!(
                    "Responded [{}] bytes={} request_uuid={}",
                    client_name, len, request_uuid
                );
            }
            Err(RespondError::RegistrationError { client_name: _ }) => {
                info!("Client [{}] is not registered.", client_name);
            }
            Err(RespondError::NetworkError { client_name: _ }) => {
                warn!(
                    "Network error occurred while responding to [{}].",
                    client_name
                );
            }
            Err(RespondError::ContactsLockPoisonError) => {
                warn!(
                    "`contacts` lock poison error occurred while responding to [{}].",
                    client_name
                );
            }
        }
        if let Some(passive_response) = passive_response {
            self.defl_sender
                .respond_to_client_passive(passive_response)
                .await
                .unwrap();
        }
    }

    pub async fn analyze_block(&mut self) {
        while let Some(block) = self.commit.recv().await {
            // This is where we can further process committed block.
            info!("Analyzing block {:?}", block);
            if block.payload.is_empty() {
                continue;
            }
            for digest in block.payload {
                let serialized_batch = self
                    .block_store
                    .read(digest.to_vec())
                    .await
                    .expect("Call store read failed.")
                    .expect("Digest not in `block_store`.");
                // SerializedBatchMessage
                if let Ok(MempoolMessage::Batch(batch)) =
                bincode::deserialize(serialized_batch.as_slice())
                {
                    info!("Analyzing BATCH_LEN={} batch...", batch.len());
                    for client_tx in batch {
                        self.analyze_transaction(client_tx).await;
                    }
                }
            }
        }
    }
}
