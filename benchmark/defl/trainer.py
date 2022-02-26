import logging
import pickle
from typing import Dict


class Trainer:
    def __init__(self, model, train_data, test_data, local_train_epochs, aggregator, num_byzantine):
        self.model = model
        self.local_train_epochs = local_train_epochs
        self.train_data = train_data
        self.test_data = test_data
        self.agg = aggregator
        self.num_byzantine = num_byzantine
        self.init_weights = self.model.get_weights()

    async def aggregate_weights(self, weights: Dict[str, bytes]):
        if len(weights) == 0:
            self.model.set_weights(self.init_weights)
            logging.warning("No weights received, using initial weights!")
        else:
            for client_name, client_weights in weights:
                self.agg.add_client_delta(client_weights)
            w_agg = self.agg.aggregate(self.num_byzantine)
            self.model.set_weights(w_agg)
            self.agg.clear_aggregator()

    async def local_train(self):
        self.model.compile(optimizer='sgd', loss='categorical_crossentropy', metrics=['accuracy'])
        self.model.fit(self.train_data[0], self.train_data[1],
                       epochs=self.local_train_epochs,
                       verbose=1,
                       # validation_data=self.test_data
                       )

    async def get_serialized_weights(self) -> bytes:
        return pickle.dumps(self.model.get_weights())
