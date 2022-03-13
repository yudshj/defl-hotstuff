import logging
from abc import abstractmethod
from typing import List

import numpy


class WeightPoisoner:
    """
    Abstract class for all poisoners.
    """
    @abstractmethod
    def poison(self, grad: List[numpy.ndarray]) -> List[numpy.ndarray]:
        """
        Poison the gradients.
        """
        pass

    def __call__(self, grad: List[numpy.ndarray]) -> List[numpy.ndarray]:
        """
        Call the poisoner.
        """
        return self.poison(grad)


class NoWeightPoisoner(WeightPoisoner):
    """
    No poisoning.
    """

    def poison(self, grad: List[numpy.ndarray]) -> List[numpy.ndarray]:
        return grad


class GaussianNoiseWeightPoisoner(WeightPoisoner):
    """
    Gaussian noise poisoning.
    """

    def __init__(self, std: float):
        self.std = std

    def poison(self, grad: List[numpy.ndarray]) -> List[numpy.ndarray]:
        return [g_i + numpy.random.normal(0, self.std, g_i.shape) for g_i in grad]


class SignFlipWeightPoisoner(WeightPoisoner):
    """
    Sign flip poisoning.
    """

    def __init__(self, sigma: float):
        if sigma > 0:
            logging.warning(
                "Using a positive sigma value for sign flip poisoning is not recommended.")
        self.sigma = sigma

    def poison(self, grad: List[numpy.ndarray]) -> List[numpy.ndarray]:
        return [self.sigma * g_i for g_i in grad]


class SameValueWeightPoisoner(WeightPoisoner):
    """
    Same value poisoning.
    """

    def __init__(self, value: float):
        self.value = value

    def poison(self, grad: List[numpy.ndarray]) -> List[numpy.ndarray]:
        return [self.value * numpy.ones(g_i.shape) for g_i in grad]
