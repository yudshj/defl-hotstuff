from abc import ABC, abstractmethod
from typing import Tuple

import tensorflow as tf
from keras import Model
from tensorflow.python.data import Dataset

from defl.types import *


class DataLoader(ABC):

    @staticmethod
    def compile(model: Model):
        pass

    @staticmethod
    def load_model(model_path: str, use_saved_compile: bool = False) -> Model:
        model: Model = tf.keras.models.load_model(model_path, compile=use_saved_compile)
        return model

    @abstractmethod
    def load_data(self,
                  dataset_config: DataConfig,
                  batch_size: int,
                  do_label_flip: bool,
                  shuffle_train: bool = True,
                  train_augmentation: bool = True,
                  ) -> Tuple[Dataset, Dataset]:
        pass
