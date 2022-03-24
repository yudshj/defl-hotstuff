from abc import ABC, abstractmethod
from typing import Tuple

import numpy as np
import tensorflow as tf
from defl.types import *
from keras import Model
from tensorflow.python.data import Dataset


def load_array(path: str):
    format = path.split('.')[-2:]
    if format[-1] == 'npy':
        ret = np.load(path)
    elif format[-1] == 'npz':
        if format[-2] == 'csr' or format[-2] == 'csc':
            import scipy.sparse as sp
            ret = sp.load_npz(path).toarray()
        else:
            # Get the FIRST array stored in `npz`.
            ret = next(np.load(path).values().__iter__())
    else:
        raise ValueError(f'Unknown format: {format}')
    return ret


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
