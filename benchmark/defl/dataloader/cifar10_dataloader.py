from typing import Any, Tuple

import numpy as np
import tensorflow as tf
import tensorflow_addons as tfa
from keras import Model

from defl.types import *
from .dataloader import DataLoader


class Cifar10DataLoader(DataLoader):
    def __init__(self):
        self.steps_per_epoch: int = -1

    @staticmethod
    def gen_init_model() -> tf.keras.Model:
        model = tf.keras.models.Sequential([
            tf.keras.layers.InputLayer(input_shape=(32, 32, 3)),
            tf.keras.layers.Conv2D(32, (3, 3), padding='same', activation='relu'),
            tf.keras.layers.Conv2D(32, (3, 3), activation='relu'),
            tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),
            tf.keras.layers.Dropout(0.25),
            tf.keras.layers.Conv2D(64, (3, 3), padding='same', activation='relu'),
            tf.keras.layers.Conv2D(64, (3, 3), activation='relu'),
            tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),
            tf.keras.layers.Dropout(0.25),
            tf.keras.layers.Flatten(),
            tf.keras.layers.Dense(512, activation='relu'),
            tf.keras.layers.Dropout(0.5),
            tf.keras.layers.Dense(10, activation='softmax')
        ], name='cifar10_init_model')

        # model.compile(optimizer='sgd', loss='categorical_crossentropy', metrics=['accuracy'])
        model.summary()
        return model

    def custom_compile(self, model: Model):
        model.compile(
            optimizer=tfa.optimizers.AdamW(learning_rate=1e-3, weight_decay=1e-4),
            loss=tf.keras.losses.CategoricalCrossentropy(),
            metrics=[tf.metrics.CategoricalAccuracy()]
        )

    @staticmethod
    def _load_data_x_y(x_path: str,
                       y_path: str,
                       do_label_flip: bool,
                       to_one_hot: bool,
                       normalize: bool,
                       augmentation: Any,
                       ) -> tf.data.Dataset:
        x = np.load(x_path)
        y = np.load(y_path)
        y_max = np.max(y)
        y_min = np.min(y)

        if do_label_flip:
            y = y_max - y + y_min
        if to_one_hot:
            y = tf.keras.utils.to_categorical(y, num_classes=y_max - y_min + 1)

        if normalize:
            x = x.astype(np.float32) / 255.

        ret = tf.data.Dataset.from_tensor_slices((x, y))
        if augmentation is not None:
            ret = ret.map(augmentation, num_parallel_calls=tf.data.AUTOTUNE)

        return ret

    @staticmethod
    def data_augmentation(img: np.ndarray, label: Any) -> Tuple[np.ndarray, Any]:
        img = tf.image.random_flip_left_right(img)
        img = tf.image.random_brightness(img, max_delta=32.0 / 255.0)
        img = tf.image.random_saturation(img, lower=0.5, upper=1.5)
        img = tf.clip_by_value(img, 0.0, 1.0)

        return img, label

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
            train_ds = Cifar10DataLoader._load_data_x_y(dataset_config['x_train'], dataset_config['y_train'],
                                                        do_label_flip, to_one_hot, normalize, augmentation)
            test_ds = Cifar10DataLoader._load_data_x_y(dataset_config['x_test'], dataset_config['y_test'],
                                                       do_label_flip, to_one_hot, normalize, augmentation)
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
