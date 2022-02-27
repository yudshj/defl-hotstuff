import h5py
import io
import logging
import zstd

import tensorflow as tf

from typing import Dict
from tensorflow.python.keras.saving import hdf5_format


class Trainer:
    def __init__(self, model, train_data, test_data, local_train_epochs, aggregator, num_byzantine):
        self.model = model
        self.local_train_epochs = local_train_epochs
        self.train_data = train_data
        self.test_data = test_data
        self.agg = aggregator
        self.num_byzantine = num_byzantine
        self.init_weights = self.model.get_weights()

    async def aggregate_weights(self, weights: Dict[str, bytes]):
        if len(weights) == 0:
            self.model.set_weights(self.init_weights)
            logging.warning("No weights received, using initial weights!")
        else:
            for client_name, client_weights_h5_zstd in weights.items():
                client_weights_h5 = zstd.decompress(client_weights_h5_zstd)
                with io.BytesIO(client_weights_h5) as bytes_file:
                    with h5py.File(bytes_file, 'r') as f:
                        hdf5_format.load_weights_from_hdf5_group(f, self.model.layers)
                self.agg.add_client_delta(self.model.get_weights())
            w_agg = self.agg.aggregate(self.num_byzantine)
            self.model.set_weights(w_agg)
            self.agg.clear_aggregator()
            # test accuracy
            score = self.model.evaluate(self.test_data[0], self.test_data[1], verbose=0)
            logging.info('[AGGREGATED] Test loss: {0[0]}, test accuracy: {0[1]}'.format(score))

    async def local_train(self) -> bytes:
        '''Return the weights of the model after local training'''
        # self.model.compile(optimizer='sgd', loss='categorical_crossentropy', metrics=['accuracy'])
        self.model.fit(self.train_data[0], self.train_data[1],
                       epochs=self.local_train_epochs,
                       verbose=1,
                       # validation_data=self.test_data
                       )

        with io.BytesIO() as bytes_file:
            with h5py.File(bytes_file, 'w') as f:
                hdf5_format.save_weights_to_hdf5_group(f, self.model.layers)
            payload = bytes_file.getvalue()
        return zstd.compress(payload, 9)
