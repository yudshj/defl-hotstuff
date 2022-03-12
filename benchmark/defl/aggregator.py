import abc
from typing import List

import numpy as np
import tensorflow as tf


def apply_delta(server_model: tf.keras.Model, delta: List[np.ndarray]):
    old_weights = server_model.get_weights()
    new_weights = [old + d for old, d in zip(old_weights, delta)]
    server_model.set_weights(new_weights)


class AbstractAggregator(abc.ABC):
    def __init__(self) -> None:
        self.layers_weight: List[List[np.ndarray]] = []

    def clear_aggregator(self):
        self.layers_weight = []

    def add_client_weight(self, client_weight: List[np.ndarray]):
        if len(self.layers_weight) == 0:
            self.layers_weight = [[] for _ in range(len(client_weight))]
        for i, delta in enumerate(client_weight):
            self.layers_weight[i].append(np.array(delta))

    @abc.abstractmethod
    def aggregate(self, num_byzantine: int):
        pass


class FedAvgAggregator(AbstractAggregator):
    def aggregate(self, num_byzantine: int):
        delta = []
        for layer in self.layers_weight:
            delta.append(np.mean(layer, axis=0))
        return delta


class MedianAggregator(AbstractAggregator):
    def aggregate(self, num_byzantine: int):
        delta = []
        for layer in self.layers_weight:
            delta.append(np.median(layer, axis=0))
        return delta


class TrimmedMeanAggregator(AbstractAggregator):

    def aggregate(self, num_byzantine: int):
        delta = []
        num_clients = len(self.layers_weight[0])
        beta = num_byzantine / num_clients
        exclusions = int(np.round(2 * beta * num_clients))
        low = exclusions // 2
        high = exclusions // 2
        high += exclusions % 2
        high = num_clients - high
        if low == high:
            high = min(num_clients, high + 1)
        for i, layer in enumerate(self.layers_weight):
            layer = np.sort(layer, axis=0)[low:high]
            delta.append(np.mean(layer, axis=0))
        return delta


class MultiKrumAggregator(AbstractAggregator):

    def __init__(self, m) -> None:
        super().__init__()
        self.m = m

    def aggregate(self, num_byzantine: int):
        num_clients = len(self.layers_weight[0])
        num_layers = len(self.layers_weight)
        k = num_clients - num_byzantine - 2
        k = max(1, k)
        flattened_deltas = []
        for client_index in range(num_clients):
            client_data = []
            for layer_index in range(num_layers):
                client_data.append(np.array(self.layers_weight[layer_index][client_index]).flatten())
            flattened_deltas.append(np.concatenate(client_data))
        deltas = np.vstack(flattened_deltas)

        distances = np.zeros((num_clients, num_clients))
        for i in range(num_clients):
            for j in range(i + 1, num_clients):
                distances[i, j] = np.square(deltas[i] - deltas[j]).sum()
                distances[j, i] = distances[i, j]

        distances.sort(axis=0)
        best_clients = np.argsort(distances[:k + 1].sum(axis=0))[:min(self.m, num_clients)]
        delta = []
        for layer in self.layers_weight:
            delta.append(np.mean(np.stack(layer)[best_clients], axis=0))
        return delta


class KrumAggregator(MultiKrumAggregator):

    def __init__(self) -> None:
        super().__init__(1)
