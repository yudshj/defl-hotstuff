use std::sync::{Arc, Mutex};

use bytes::Bytes;
use log::{info, warn};
use prost::Message;
use tokio::sync::mpsc::{channel, Receiver};

use consensus::{Block, Consensus};
use crypto::SignatureService;
use mempool::{Mempool, MempoolMessage};
use proto::{ContactsType, WLastType};
use proto::defl::*;
// Sync the mempool with the consensus and nodes.
use proto::defl::client_request::Method;
use store::Store;

use crate::config::{Committee, ConfigError, Parameters, Secret};
use crate::config::Export as _;

/// The default channel capacity for this module.
pub const CHANNEL_CAPACITY: usize = 1_000;

pub struct Node {
    pub commit: Receiver<Block>,
    pub block_store: Store,
    pub contacts: Arc<Mutex<ContactsType>>,
    pub w_last: Arc<Mutex<WLastType>>,
}

impl Node {
    pub async fn new(
        committee_file: &str,
        key_file: &str,
        store_path: &str,
        parameters: Option<&str>,
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
        let contacts = Arc::new(Mutex::new(ContactsType::new()));
        let w_last = Arc::new(Mutex::new(WLastType::new()));

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
            contacts.clone(),
            w_last.clone(),
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
            contacts,
            w_last,
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
                        // TODO: Here we process TXs.
                        let tx_str = base64::encode(&client_tx);
                        info!("DONG: Analyze client tx: [{}].", tx_str);

                        let client_request = ClientRequest::decode(Bytes::from(client_tx)).unwrap();
                        match Method::from_i32(client_request.method) {
                            Some(Method::NewWeights) => {
                                info!("DONG:");
                            }
                            Some(Method::NewEpoch) => {
                                info!("DONG:");
                            }
                            _ => {
                                warn!("DONG: Block should be filtered out previously")
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
