from abc import ABC, abstractmethod
from typing import Tuple

import tensorflow as tf
from keras import Model
from tensorflow.python.data import Dataset

from defl.types import *


class DataLoader(ABC):

    @abstractmethod
    def custom_compile(self, model: Model):
        pass

    def load_model(self, model_path: str, use_saved_compile: bool = True) -> Model:
        model: Model = tf.keras.models.load_model(model_path, compile=use_saved_compile)

        if not use_saved_compile or not model.compiled_loss:
            self.custom_compile(model)
            pass

        return model

    @abstractmethod
    def load_data(self,
                  dataset_config: DataConfig,
                  batch_size: int,
                  do_label_flip: bool,
                  to_one_hot: bool = True,
                  shuffle_train: bool = True,
                  normalize: bool = True,
                  augmentation=None,
                  ) -> Tuple[Dataset, Dataset]:
        pass
