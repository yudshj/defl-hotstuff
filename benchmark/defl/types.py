import typing

DataConfig = typing.TypedDict("DataConfig", {
    'x_train': str,
    'y_train': str,
    'x_test': str,
    'y_test': str,
    'x_val': str,
    'y_val': str,
})

ClientConfig = typing.TypedDict('ClientConfig', {
    'attack': str,
    'batch_size': int,
    'data_config': DataConfig,
    'local_train_steps': int,

    # ----------------------------------------- #
    'task': str,
    'client_name': str,
    'server_name': str,
    'obsido_port': int,
    'host': str,
    'init_model_path': str,
    'fetch': int,
    'gst': int,
})
