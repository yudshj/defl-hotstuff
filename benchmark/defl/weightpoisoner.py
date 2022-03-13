import logging
from abc import abstractmethod
from typing import List

import tensorflow as tf
import numpy as np


class WeightPoisoner(tf.keras.callbacks.Callback):
    def __init__(self):
        super().__init__()
        self.old_weights: List[np.ndarray] = []

    @abstractmethod
    def poison(self, grad: List[np.ndarray]) -> List[np.ndarray]:
        """
        Poison the gradients.
        """
        pass

    def on_train_begin(self, logs=None):
        self.old_weights = self.model.get_weights()

    def on_train_end(self, logs=None):
        new_weights = self.model.get_weights()
        gradient = self.poison([np.subtract(new_w, old_w) for new_w, old_w in zip(new_weights, self.old_weights)])
        self.model.set_weights([np.add(g, old_w) for g, old_w in zip(gradient, self.old_weights)])


class GaussianNoiseWeightPoisoner(WeightPoisoner):
    """
    Gaussian noise poisoning.
    """

    def __init__(self, std: float):
        super().__init__()
        self.std = std

    def poison(self, grad: List[np.ndarray]) -> List[np.ndarray]:
        return [g_i + np.random.normal(0, self.std, g_i.shape) for g_i in grad]


class SignFlipWeightPoisoner(WeightPoisoner):
    """
    Sign flip poisoning.
    """

    def __init__(self, sigma: float):
        super().__init__()
        if sigma > 0:
            logging.warning(
                "Using a positive sigma value for sign flip poisoning is not recommended.")
        self.sigma = sigma

    def poison(self, grad: List[np.ndarray]) -> List[np.ndarray]:
        return [self.sigma * g_i for g_i in grad]


class SameValueWeightPoisoner(WeightPoisoner):
    """
    Same value poisoning.
    """

    def __init__(self, value: float):
        super().__init__()
        self.value = value

    def poison(self, grad: List[np.ndarray]) -> List[np.ndarray]:
        return [self.value * np.ones(g_i.shape) for g_i in grad]
