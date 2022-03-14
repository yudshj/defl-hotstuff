import typing

TFDSArgs = typing.Dict[str, typing.Any]

TFDSConfig = typing.TypedDict('TFDSConfig', {
    'ds_name': str,
    'fit_args': TFDSArgs,
    'evaluate_args': TFDSArgs,
})

ClientConfig = typing.TypedDict('ClientConfig', {
    'attack': str,
    'batch_size': int,
    'tfds_config': TFDSConfig,
    'local_train_epochs': int,
    # ----------------------------------------- #
    'client_name': str,
    'server_name': str,
    'obsido_port': int,
    'host': str,
    'init_model_path': str,
    'fetch': int,
    'gst': int,
})