from abc import ABC, abstractmethod
from typing import Any, Tuple

import numpy as np
import tensorflow as tf

from defl.types import *


class DataLoader(ABC):
    @staticmethod
    @abstractmethod
    def gen_init_model() -> tf.keras.Model:
        pass

    @staticmethod
    @abstractmethod
    def give_me_compiled_model(model_path: str):
        pass

    @staticmethod
    @abstractmethod
    def data_augmentation(img: np.ndarray, label: Any) -> Tuple[np.ndarray, Any]:
        pass

    @abstractmethod
    def load_data(self,
                  dataset_config: DataConfig,
                  batch_size: int,
                  do_label_flip: bool,
                  to_one_hot: bool = True,
                  shuffle_train: bool = True,
                  normalize: bool = True,
                  augmentation=None,
                  ) -> Tuple[tf.data.Dataset, tf.data.Dataset]:
        pass
