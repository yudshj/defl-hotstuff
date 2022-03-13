import io
import logging
from typing import Dict, List

import numpy as np
import tensorflow as tf
from tensorflow import Tensor
from tensorflow.keras.models import Model

from defl.aggregator import AbstractAggregator
from defl.weightpoisoner import WeightPoisoner


def _serialize_w_list(weights: List[np.ndarray]) -> bytes:
    with io.BytesIO() as bytes_file:
        kwargs = {f"{x:x}": y for x, y in enumerate(weights)}
        np.savez_compressed(bytes_file, **kwargs)
        payload = bytes_file.getvalue()
    return payload


def _deserialize_w_list(client_weights_npz: bytes) -> List[np.ndarray]:
    with io.BytesIO(client_weights_npz) as bytes_file:
        payload = np.load(bytes_file)
        client_weights = list(payload[x] for x in sorted(payload.keys(), key=lambda x: int(x, 16)))
    return client_weights


class Trainer:
    def __init__(self,
                 model: Model,
                 train_data,
                 test_data,
                 local_train_epochs: int,
                 aggregator: AbstractAggregator,
                 num_byzantine: int):

        self.model: Model = model
        self.local_train_epochs: int = local_train_epochs
        self.train_data = tf.data.Dataset.from_tensor_slices(train_data).shuffle(10000).batch(32)
        self.test_data = tf.data.Dataset.from_tensor_slices(test_data).shuffle(10000).batch(32)
        self.agg: AbstractAggregator = aggregator
        self.num_byzantine: int = num_byzantine
        self.init_weights: List[Tensor] = self.model.get_weights()

    def get_serialized_weights(self) -> bytes:
        return _serialize_w_list(self.model.get_weights())

    def aggregate_weights(self, weights: Dict[str, bytes]):
        if len(weights) == 0:
            self.model.set_weights(self.init_weights)
            logging.warning("No weights received, using initial weights!")
        else:
            for client_name, client_weights_npz in weights.items():
                client_weights = _deserialize_w_list(client_weights_npz)
                self.agg.add_client_weight(client_weights)
            w_agg = self.agg.aggregate(self.num_byzantine)
            self.model.set_weights(w_agg)
            self.agg.clear_aggregator()

    def local_train(self, callbacks: List[tf.keras.callbacks.Callback]):
        """Return the weights of the model after local training"""
        # optimizer = self.model.optimizer
        # loss_fn = self.model.loss

        self.model.fit(self.train_data,
                       epochs=self.local_train_epochs,
                       verbose=0,
                       callbacks=callbacks
                       )

    def evaluate(self) -> List:
        return self.model.evaluate(self.test_data, verbose=0)
