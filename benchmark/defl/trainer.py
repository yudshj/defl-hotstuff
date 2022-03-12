import io
import logging
from typing import Dict, List

import numpy as np
import tensorflow as tf
from tensorflow import Tensor
from tensorflow.keras.models import Model

from defl.aggregator import AbstractAggregator


class Trainer:
    def __init__(self, model: Model, train_data, test_data, local_train_epochs: int, aggregator: AbstractAggregator, num_byzantine: int):
        self.model: Model = model
        self.local_train_epochs: int = local_train_epochs
        self.train_data = tf.data.Dataset.from_tensor_slices(train_data).shuffle(5000).batch(32)
        self.test_data = tf.data.Dataset.from_tensor_slices(test_data).shuffle(5000).batch(32)
        self.agg: AbstractAggregator = aggregator
        self.num_byzantine: int = num_byzantine
        self.init_weights: List[Tensor] = self.model.get_weights()

    def aggregate_weights(self, weights: Dict[str, bytes]):
        if len(weights) == 0:
            self.model.set_weights(self.init_weights)
            logging.warning("No weights received, using initial weights!")
        else:
            for client_name, client_weights_npz in weights.items():
                # np.savez_compressed(bytes_file, *self.model.get_weights())
                with io.BytesIO(client_weights_npz) as bytes_file:
                    payload = np.load(bytes_file)
                    client_weights = list(payload[x] for x in sorted(payload.keys(), key=lambda x: int(x, 16)))
                self.agg.add_client_delta(client_weights)
            w_agg = self.agg.aggregate(self.num_byzantine)
            self.model.set_weights(w_agg)
            self.agg.clear_aggregator()

    def local_train(self):
        '''Return the weights of the model after local training'''
        # self.model.compile(optimizer='sgd', loss='categorical_crossentropy', metrics=['accuracy'])
        self.model.fit(
            self.train_data,
            epochs=self.local_train_epochs,
            verbose=1
        )
    
    def poison(self):
        # TODO: Poisoning the weights
        # self.model.get_weights()
        pass

    def serialize_model(self) -> bytes:
        with io.BytesIO() as bytes_file:
            kwargs = { f"{x:x}": y for x,y in enumerate(self.model.get_weights()) }
            np.savez_compressed(bytes_file, **kwargs)
            payload = bytes_file.getvalue()
        return payload
    
    def evaluate(self) -> List:
        return self.model.evaluate(self.test_data[0], self.test_data[1], verbose=0)
