use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};

use bytes::Bytes;
use log::{info, warn};
use prost::Message;
use tokio::sync::mpsc::{channel, Receiver};

use consensus::{Block, Consensus};
use crypto::SignatureService;
use mempool::{Mempool, MempoolMessage};
use network::SimpleSender;
use proto::defl::*;
// Sync the mempool with the consensus and nodes.
use proto::defl::client_request::Method;
use proto::defl::response::Status;
use proto::defl_sender::DeflSender;
use proto::NodeInfo;
use store::Store;

use crate::config::{Committee, ConfigError, Parameters, Secret};
use crate::config::Export as _;

/// The default channel capacity for this module.
pub const CHANNEL_CAPACITY: usize = 1_000;

pub struct Node {
    pub commit: Receiver<Block>,
    pub block_store: Store,
    last_node_info: Arc<Mutex<NodeInfo>>,
    cur_node_info: NodeInfo,
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
        let cur_node_info = NodeInfo::new(0);
        let last_node_info = Arc::new(Mutex::new(NodeInfo::new(-1)));

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
            DeflSender {
                sender: SimpleSender::new(),
                contacts: defl_sender.contacts.clone(),
            },
            last_node_info.clone(),
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
            last_node_info,
            cur_node_info,
            voted_clients: HashSet::new(),
            defl_sender,
            quorum,
        })
    }

    pub fn print_key_file(filename: &str) -> Result<(), ConfigError> {
        Secret::new().write(filename)
    }

    pub async fn analyze_block(&mut self) {
        while let Some(block) = self.commit.recv().await {
            // This is where we can further process committed block.
            // TODO: Here goes the application logic.
            for digest in block.payload {
                let serialized_batch = self
                    .block_store
                    .read(digest.to_vec())
                    .await
                    .expect("DONG: Call store read failed.")
                    .expect("DONG: Digest not in `block_store`.");
                // SerializedBatchMessage
                if let Ok(MempoolMessage::Batch(batch)) =
                bincode::deserialize(serialized_batch.as_slice())
                {
                    info!("DONG: Start analyzing batch ...");
                    for client_tx in batch {
                        // let tx_str = base64::encode(&client_tx);
                        // info!("DONG: Analyze client tx: [{}].", tx_str);
                        let client_request = ClientRequest::decode(Bytes::from(client_tx)).unwrap();
                        let ClientRequest {
                            method: _,
                            request_uuid,
                            client_name,
                            target_epoch_id: _,
                            weights,
                            register_info: _,
                        } = client_request;
                        let stat = match Method::from_i32(client_request.method) {
                            Some(Method::UpdWeights) => {
                                info!("DONG: NEW_WEIGHTS received.");
                                if let Some(target_epoch_id) = client_request.target_epoch_id {
                                    if target_epoch_id == self.cur_node_info.epoch_id {
                                        if let Some(weights) = weights {
                                            self.cur_node_info
                                                .client_weights
                                                .insert(client_name.clone(), weights);
                                            info!("DONG: `w_cur` updated.");
                                            Status::Ok.into()
                                        } else {
                                            warn!("DONG: No `weights` field in request.");
                                            Status::NoWeightsInRequestError.into()
                                        }
                                    } else {
                                        warn!("DONG: UNEXPECTED_EPOCH_ID {}", client_name);
                                        Status::UwTargetEpochIdError.into()
                                    }
                                } else {
                                    warn!("DONG: No `target_epoch_id` field in request.");
                                    Status::UwTargetEpochIdError.into()
                                }
                            }
                            Some(Method::NewEpochRequest) => {
                                info!("DONG: NEW_EPOCH_REQUEST received.");
                                if let Some(target_epoch_id) = client_request.target_epoch_id {
                                    if target_epoch_id == self.cur_node_info.epoch_id {
                                        if self.voted_clients.insert(client_name.clone()) {
                                            info!("DONG: Client [{}] voted.", client_name);

                                            // check meet quorum
                                            if self.voted_clients.len() < self.quorum {
                                                info!(
                                                    "DONG: Not enough clients voted: {} / {}.",
                                                    self.voted_clients.len(),
                                                    self.quorum
                                                );
                                                Status::NotMeetQuorumWait.into()
                                            } else {
                                                info!("DONG: Enough clients voted. Total weights: {}.", self.cur_node_info.client_weights.len());
                                                self.last_node_info
                                                    .lock()
                                                    .unwrap()
                                                    .clone_from(&self.cur_node_info);
                                                self.cur_node_info.epoch_id += 1;
                                                self.cur_node_info.client_weights.clear();
                                                self.voted_clients.clear();
                                                info!("DONG: `cur_node_info` updated.");
                                                Status::Ok.into()
                                            }
                                        } else {
                                            warn!(
                                                "DONG: Client [{}] has already voted.",
                                                client_name
                                            );
                                            Status::ClientAlreadyVotedError.into()
                                        }
                                    } else {
                                        warn!("DONG: UNEXPECTED_EPOCH_ID {}", client_name);
                                        Status::NerTargetEpochIdError.into()
                                    }
                                } else {
                                    warn!("DONG: No `target_epoch_id` field in request.");
                                    Status::NerTargetEpochIdError.into()
                                }
                            }
                            _ => {
                                warn!("DONG: Block should be filtered out previously. Ignoring...");
                                Status::ServerInternalError.into()
                            }
                        };
                        let response = Response {
                            stat,
                            request_uuid,
                            w_last: HashMap::new(),
                            r_last_epoch_id: None,
                        };
                        match self
                            .defl_sender
                            .respond_to_client(client_name, response)
                            .await
                        {
                            Ok(client_name) => {
                                info!("DONG: Sent response to client {}.", client_name);
                            }
                            Err(respond_error) => {
                                warn!("DONG: Failed to respond: {}", respond_error.msg);
                            }
                        }
                    }
                    info!("DONG: End analyzing batch!");
                }
            }
            // TODO: respond to client
            // TODO: 服务端 analyze 的时候通知 client (rust&python IPC)
        }
    }
}
