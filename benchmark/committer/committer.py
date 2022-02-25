import abc
from proto.defl_pb2 import Response

class Committer:
    def __init__(self):
        pass

    @abc.abstractmethod
    def fetch_w_last(self) -> Response:
        pass

    @abc.abstractmethod
    def new_weights(self, target_epoch_id: int, weights_b: bytes) -> Response:
        pass

    @abc.abstractmethod
    def new_epoch_request(self, target_epoch_id: int) -> Response:
        pass
