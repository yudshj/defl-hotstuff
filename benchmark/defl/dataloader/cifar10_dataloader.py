from typing import Tuple

import numpy as np
import tensorflow as tf
from keras import Model

from defl.types import *
from .dataloader import DataLoader

_LR = 1e-3
_NUM_CLASSES = 10
_DATA_AUGMENTER = tf.keras.Sequential([
    tf.keras.layers.RandomFlip('horizontal'),
    tf.keras.layers.RandomTranslation(0.1, 0.1, fill_mode='nearest'),
])


class Cifar10DataLoader(DataLoader):
    def __init__(self):
        self.steps_per_epoch: int = -1

    @staticmethod
    def gen_init_model() -> tf.keras.Model:
        from keras.layers import Dense, Conv2D, Activation, AveragePooling2D
        from keras.layers import Input, Flatten, Concatenate, BatchNormalization

        # start model definition
        # densenet CNNs (composite function) are made of BN-ReLU-Conv2D
        input_shape = (32, 32, 3)
        # network parameters
        num_classes = 10
        num_dense_blocks = 3

        # DenseNet-BC with dataset augmentation
        # Growth rate   | Depth |  Accuracy (paper)| Accuracy (this)      |
        # 12            | 100   |  95.49%          | 93.74%               |
        # 24            | 250   |  96.38%          | requires big mem GPU |
        # 40            | 190   |  96.54%          | requires big mem GPU |
        growth_rate = 12
        depth = 100
        num_bottleneck_layers = (depth - 4) // (2 * num_dense_blocks)

        num_filters_bef_dense_block = 2 * growth_rate
        compression_factor = 0.5

        inputs = Input(shape=input_shape)
        x = BatchNormalization()(inputs)
        x = Activation('relu')(x)
        x = Conv2D(num_filters_bef_dense_block,
                   kernel_size=3,
                   padding='same',
                   kernel_initializer='he_normal')(x)
        x = Concatenate()([inputs, x])

        # stack of dense blocks bridged by transition layers
        for i in range(num_dense_blocks):
            # a dense block is a stack of bottleneck layers
            for j in range(num_bottleneck_layers):
                y = BatchNormalization()(x)
                y = Activation('relu')(y)
                y = Conv2D(4 * growth_rate,
                           kernel_size=1,
                           padding='same',
                           kernel_initializer='he_normal')(y)
                y = BatchNormalization()(y)
                y = Activation('relu')(y)
                y = Conv2D(growth_rate,
                           kernel_size=3,
                           padding='same',
                           kernel_initializer='he_normal')(y)
                x = Concatenate()([x, y])

            # no transition layer after the last dense block
            if i == num_dense_blocks - 1:
                continue

            # transition layer compresses num of feature maps and reduces the size by 2
            num_filters_bef_dense_block += num_bottleneck_layers * growth_rate
            num_filters_bef_dense_block = int(num_filters_bef_dense_block * compression_factor)
            y = BatchNormalization()(x)
            y = Conv2D(num_filters_bef_dense_block,
                       kernel_size=1,
                       padding='same',
                       kernel_initializer='he_normal')(y)
            x = AveragePooling2D()(y)

        # add classifier on top
        # after average pooling, size of feature map is 1 x 1
        x = AveragePooling2D(pool_size=8)(x)
        y = Flatten()(x)
        outputs = Dense(num_classes,
                        kernel_initializer='he_normal',
                        activation='softmax')(y)

        # instantiate and compile model
        # orig paper uses SGD but RMSprop works better for DenseNet
        model = Model(inputs=inputs, outputs=outputs)
        Cifar10DataLoader.compile(model)
        return model

    @staticmethod
    def compile(model: Model):
        model.compile(
            optimizer=tf.keras.optimizers.RMSprop(learning_rate=_LR),
            loss=tf.keras.losses.CategoricalCrossentropy(),
            metrics=[tf.keras.metrics.CategoricalAccuracy()],
        )

    @staticmethod
    def data_augmentation(img, label):
        return _DATA_AUGMENTER(img), label

    @staticmethod
    def _load_data_x_y(x_path: str,
                       y_path: str,
                       do_label_flip: bool,
                       data_augment: bool,
                       ) -> tf.data.Dataset:
        x = np.load(x_path)
        y = np.load(y_path)

        if do_label_flip:
            y = _NUM_CLASSES - y - 1

        # normalize to [0, 1]
        x = x.astype(np.float32) / 255.

        # convert to one-hot
        y = tf.one_hot(y, depth=_NUM_CLASSES)

        ret = tf.data.Dataset.from_tensor_slices((x, y))
        if data_augment:
            ret = ret.map(Cifar10DataLoader.data_augmentation, num_parallel_calls=tf.data.AUTOTUNE)

        return ret

    def load_data(self,
                  dataset_config: DataConfig,
                  batch_size: int,
                  do_label_flip: bool,
                  shuffle_train: bool = True,
                  repeat_train: bool = False,
                  train_augmentation: bool = True,
                  ) -> Tuple[tf.data.Dataset, tf.data.Dataset]:

        with tf.device('/cpu:0'):
            train_ds = self._load_data_x_y(dataset_config['x_train'], dataset_config['y_train'],
                                           do_label_flip, train_augmentation)
            test_ds = self._load_data_x_y(dataset_config['x_test'], dataset_config['y_test'],
                                          do_label_flip, False)
            # val_ds = None
            # TODO: validation dataset may NOT be `None`

            self.steps_per_epoch = (len(train_ds) + batch_size - 1) // batch_size

            if shuffle_train:
                train_ds = train_ds.shuffle(buffer_size=len(train_ds))

            if repeat_train:
                train_ds = train_ds.repeat()

            train_ds = train_ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)
            test_ds = test_ds.batch(batch_size).prefetch(tf.data.AUTOTUNE)

        return train_ds, test_ds
