import io
import logging
from typing import Dict, List

import h5py
import numpy as np
import tensorflow as tf

from defl.aggregator import AbstractAggregator


# from defl.weightpoisoner import WeightPoisoner

def _serialize_numpy_array_list(arr_list: List[np.ndarray]) -> bytes:
    with io.BytesIO() as bytes_file:
        with h5py.File(bytes_file, 'w') as h5_file:
            h5_file.attrs['length'] = len(arr_list)
            for i, x in enumerate(arr_list):
                h5_file.create_dataset(f'weight_{i:03d}', data=x)
        payload = bytes_file.getvalue()
    return payload


def _get_trainable_weights(model: tf.keras.Model) -> List[np.ndarray]:
    lst = [x.numpy() for x in model.trainable_weights]
    return lst


def _deserialize_numpy_array_list(weights_bytes: bytes) -> List[np.ndarray]:
    with io.BytesIO(weights_bytes) as bytes_file:
        with h5py.File(bytes_file, 'r') as h5_file:
            arr_list = [h5_file[f'weight_{i:03d}'][:] for i in range(h5_file.attrs['length'])]
    return arr_list


def _set_trainable_weights(model: tf.keras.Model, arr_list: List[np.ndarray]) -> None:
    tf.keras.backend.batch_set_value(zip(model.trainable_weights, arr_list))


class Trainer:
    def __init__(self,
                 model: tf.keras.Model,
                 train_data,
                 test_data,
                 local_train_steps: int,
                 aggregator: AbstractAggregator,
                 num_byzantine: int):

        self.model: tf.keras.Model = model
        self.local_train_steps: int = local_train_steps
        self.train_data = train_data
        self.test_data = test_data
        self.agg: AbstractAggregator = aggregator
        self.num_byzantine: int = num_byzantine
        self.init_trainable_weights: List[np.ndarray] = _get_trainable_weights(self.model)

    def get_serialized_weights(self) -> bytes:
        return _serialize_numpy_array_list(_get_trainable_weights(self.model))

    def aggregate_weights(self, weights: Dict[str, bytes]):
        if len(weights) == 0:
            _set_trainable_weights(self.model, self.init_trainable_weights)
            # self.model.set_weights(self.init_weights)
            logging.warning("No weights received, using initial weights!")
        else:
            for client_name, client_weights_hdf5 in weights.items():
                client_weights = _deserialize_numpy_array_list(client_weights_hdf5)
                self.agg.add_client_weight(client_weights)
            w_agg = self.agg.aggregate(self.num_byzantine)
            # self.model.set_weights(w_agg)
            _set_trainable_weights(self.model, w_agg)
            self.agg.clear_aggregator()

    def local_train(self, callbacks: List[tf.keras.callbacks.Callback]):
        """Return the weights of the model after local training"""
        # optimizer = self.model.optimizer
        # loss_fn = self.model.loss

        self.model.fit(self.train_data,
                       steps_per_epoch=self.local_train_steps,
                       epochs=1,
                       verbose=1,
                       callbacks=callbacks
                       )

    def evaluate(self) -> List:
        return self.model.evaluate(self.test_data, verbose=1)
