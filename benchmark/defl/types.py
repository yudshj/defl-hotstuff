from typing import TypedDict, Literal, Optional

DataConfig = TypedDict("DataConfig", {
    'x_train': str,
    'y_train': str,
    'x_test': str,
    'y_test': str,
    'x_val': Optional[str],
    'y_val': Optional[str],
})

ATTACK_METHOD = Literal['none', 'gaussian', 'sign', 'label']
AGGREGATOR_TYPE = Literal['krum', 'multikrum', 'fedavg']

ClientConfig = TypedDict('ClientConfig', {
    'aggregator': AGGREGATOR_TYPE,
    'attack': ATTACK_METHOD,
    'batch_size': int,
    'data_config': DataConfig,
    'local_train_steps': int,
    'env': dict,
    'save_freq': int,

    # ----------------------------------------- #
    'task': str,
    'client_name': str,
    'server_name': str,
    'obsido_port': int,
    'host': str,
    'init_model_path': str,
    'fetch': int,
    'gst': int,

    # ----------- byzantine config ------------ #
    'num_byzantine': int,
    'multikrum_factor': int,
    'gaussian_attack_factor': Optional[float],
    'signflip_attack_factor': Optional[float],
})
