from typing import Tuple

import numpy as np
import scipy.sparse as sp
import tensorflow as tf
import tensorflow_addons as tfa
from keras import Model

from defl.dataloader import DataLoader
from defl.types import *

_SEQUENCE_LENGTH = 60
_LSTM_SIZE = 128


class Sentiment140DataLoader(DataLoader):
    def __init__(self):
        self.steps_per_epoch: int = -1

    @staticmethod
    def gen_init_model(embedding_matrix_path: str) -> tf.keras.Model:
        embedding_matrix: np.ndarray = np.load(embedding_matrix_path)
        embedding_matrix = np.pad(embedding_matrix, ((0, 0), (0, 1)), 'constant', constant_values=0)
        embedding_matrix[-1][-1] = 1

        inputs = tf.keras.layers.Input(shape=(_SEQUENCE_LENGTH,))
        x = tf.keras.layers.Embedding(embedding_matrix.shape[0],embedding_matrix.shape[1],weights=[embedding_matrix],trainable=False,mask_zero=True)(inputs)
        x = tf.keras.layers.Bidirectional(tf.keras.layers.LSTM(_LSTM_SIZE, return_sequences=True))(x)
        # x = tf.keras.layers.SpatialDropout1D(0.2)(x)
        x = tf.keras.layers.MultiHeadAttention(num_heads=4, key_dim=200)(x, x)
        x = tf.keras.layers.Dropout(0.15)(x)
        x = tf.keras.layers.Flatten()(x)
        x = tf.keras.layers.Dense(32, activation='relu')(x)
        x = tf.keras.layers.BatchNormalization()(x)
        x = tf.keras.layers.Dropout(0.15)(x)
        outputs = tf.keras.layers.Dense(1, activation='sigmoid')(x)
        model = tf.keras.Model(inputs=inputs, outputs=outputs, name='sentiment140_init_model')
        model.summary()
        return model

    def custom_compile(self, model: Model):
        model.compile(
            loss=tf.keras.losses.BinaryCrossentropy(from_logits=False),
            optimizer=tfa.optimizers.AdamW(learning_rate=1e-3, weight_decay=1e-4),
            metrics=[tf.keras.metrics.BinaryAccuracy()]
        )

    @staticmethod
    def _load_data_x_y(x_path: str,
                       y_path: str,
                       do_label_flip: bool
                       ) -> tf.data.Dataset:
        format = x_path.split('.')[-2:]
        if format[-1] == 'npy':
            x = np.load(x_path)
        elif format[-1] == 'npz' and format[-2] == 'csr':
            x = sp.load_npz(x_path).toarray()
        else:
            raise ValueError(f'Unknown format: {format}')

        y = np.load(y_path)
        y_max = np.max(y)
        y_min = np.min(y)

        if do_label_flip:
            y = y_max - y + y_min

        y = y.astype(np.float32) / 4.0

        ret = tf.data.Dataset.from_tensor_slices((x, y))

        return ret

    def load_data(self,
                  dataset_config: DataConfig,
                  batch_size: int,
                  do_label_flip: bool,
                  to_one_hot: bool = True,
                  shuffle_train: bool = True,
                  repeat_train: bool = False,
                  normalize: bool = True,
                  augmentation=None,
                  ) -> Tuple[tf.data.Dataset, tf.data.Dataset]:

        with tf.device('/cpu:0'):
            train_ds = Sentiment140DataLoader._load_data_x_y(dataset_config['x_train'], dataset_config['y_train'],
                                                             do_label_flip)
            test_ds = Sentiment140DataLoader._load_data_x_y(dataset_config['x_test'], dataset_config['y_test'],
                                                            do_label_flip)
            # val_ds = None
            # TODO: validation dataset may NOT be `None`

            self.steps_per_epoch = (len(train_ds) + batch_size - 1) // batch_size

            if shuffle_train:
                train_ds = train_ds.shuffle(buffer_size=50000)

            if repeat_train:
                train_ds = train_ds.repeat()

            train_ds = train_ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)
            test_ds = test_ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)

        return train_ds, test_ds
