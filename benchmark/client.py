import argparse
import asyncio
import json
import os
import threading
import time
import uuid

import tensorflow as tf

from defl.aggregator import MultiKrumAggregator
from defl.committer import IpcCommitter
from defl.committer.ipc_committer import ObsidoResponseQueue
from defl.dataloader import Cifar10DataLoader, Sentiment140DataLoader
from defl.trainer import Trainer
from defl.types import *
from defl.weightpoisoner import *
from proto.defl_pb2 import Response, WeightsResponse


def sleep_then_info(sleep_time: float, message: str):
    time.sleep(sleep_time)
    logging.info(message)

# def gpu_memory_limit(num_MB: int = 4096):
#     gpus = tf.config.experimental.list_physical_devices('GPU')
#     if gpus:
#         # Restrict TensorFlow to only allocate 1GB of memory on the first GPU
#         try:
#             tf.config.experimental.set_virtual_device_configuration(
#                 gpus[0],
#                 [tf.config.experimental.VirtualDeviceConfiguration(memory_limit=num_MB)])
#             logical_gpus = tf.config.experimental.list_logical_devices('GPU')
#             print(len(gpus), "Physical GPUs,", len(logical_gpus), "Logical GPUs")
#         except RuntimeError as e:
#             # Virtual devices must be set before GPUs have been initialized
#             print(e)
            
# gpu_memory_limit(2500)



_NUM_BYZANTINE = 1
_MULTIKRUM_FACTOR = 2
_GAUSSIAN_ATTACK_FACTOR = 1/1000
_SIGNFLIP_ATTACK_FACTOR = -1


async def start(params: ClientConfig):
    if params['task'] == 'cifar10':
        dataloader = Cifar10DataLoader()
    elif params['task'] == 'sentiment140':
        dataloader = Sentiment140DataLoader()
    else:
        raise ValueError("Unknown task {}".format(params['task']))

    callbacks = []
    label_flip = False
    if params['attack'] == 'none':
        pass
    elif params['attack'] == 'gaussian':
        callbacks.append(GaussianNoiseWeightPoisoner(_GAUSSIAN_ATTACK_FACTOR))
    elif params['attack'] == 'sign':
        callbacks.append(SignFlipWeightPoisoner(_SIGNFLIP_ATTACK_FACTOR))
    elif params['attack'] == 'label':
        label_flip = True
        # raise NotImplementedError("Label-flip poisoning is not implemented yet.")
    else:
        raise ValueError("Unknown poisoning method.")

    # learning stuff
    train_data, test_data = dataloader.load_data(params['data_config'], params['batch_size'], label_flip, repeat_train=True)
    logging.info("Train step_per_epoch: {}".format(dataloader.train_steps_per_epoch))
    logging.info("Test step_per_epoch: {}".format(dataloader.test_steps_per_epoch))
    model = dataloader.load_model(params['init_model_path'], use_saved_compile=False)
    trainer = Trainer(
        model=model,
        train_data=train_data,
        test_data=test_data,
        local_train_steps=params['local_train_steps'],
        aggregator=MultiKrumAggregator(_MULTIKRUM_FACTOR),
        num_byzantine=_NUM_BYZANTINE,
        dataloader=dataloader,
    )

    # committer stuff
    client_name = str(uuid.uuid4())
    fetch_queue = ObsidoResponseQueue()
    host, port = params['host'].split(':')
    committer = IpcCommitter(client_name, host, int(port), params['obsido_port'], fetch_queue)
    await committer.committer_bootstrap()

    # defl stuff
    epoch_id = -1

    fetch_timeout: float = params['fetch'] / 1000.0
    gst_timeout: float = params['gst'] / 1000.0
    logging.info("+++++++++++++++++++++++++ [CLIENT] +++++++++++++++++++++++++")
    logging.info("+ client_name:        {:36s} +".format(client_name))
    logging.info("+ task:               {:36s} +".format(params['task']))
    logging.info("+ attack:             {:36s} +".format(params['attack']))
    logging.info("+ fetch_timeout:      {:36s} +".format('%.2f seconds' % fetch_timeout))
    logging.info("+ gst_timeout:        {:36s} +".format('%.2f seconds' % gst_timeout))
    logging.info("+ local_train_steps:  {:36s} +".format('%d' % params['local_train_steps']))
    logging.info("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    logging.info("[INIT LOOP]")
    logging.info("Current epoch id is %d.", epoch_id)
    epoch_id = await client_routine(committer, epoch_id, fetch_queue, 0, gst_timeout, trainer, callbacks,
                                    evaluate=False)
    model_save_path = "./models/{}/epoch_{:05d}.h5".format(client_name, epoch_id)
    trainer.model.save_model(model_save_path)
    logging.info("Saved model to %s", model_save_path)

    i = 0
    while True:
        i += 1
        logging.info("[LOOP %d]", i)
        logging.info("Current epoch id is %d. Waiting PASSIVE %.0f seconds...", epoch_id, fetch_timeout)
        epoch_id = await client_routine(committer, epoch_id, fetch_queue, fetch_timeout, gst_timeout, trainer,
                                        callbacks, evaluate=True)
        model_save_path = "./models/{}/epoch_{:05d}.h5".format(client_name, epoch_id)
        trainer.model.save_model(model_save_path)
        logging.info("Saved model to %s", model_save_path)



async def active_fetch_after(sleep_time, committer):
    await asyncio.sleep(sleep_time)
    logging.info("PASSIVE received nothing. Fetching...")
    await committer.fetch_w_last()


async def client_routine(committer, epoch_id, fetch_queue: ObsidoResponseQueue, fetch_timeout, gst_timeout: float,
                         trainer: Trainer, callbacks: List[tf.keras.callbacks.Callback], evaluate: bool = True):
    active_fetch_task = asyncio.create_task(active_fetch_after(fetch_timeout, committer))
    fetch_resp: WeightsResponse = await fetch_queue.drain()
    active_fetch_task.cancel()

    logging.debug(
        f'Collected: {fetch_resp.request_uuid} with epoch_id={fetch_resp.r_last_epoch_id} and size of {fetch_resp.ByteSize()} bytes')

    # LOL! Remote seems to be old.
    if epoch_id > fetch_resp.r_last_epoch_id:
        logging.warning("Remote epoch id is not bigger than current epoch id. This is not good!")
        return epoch_id

    # TAT! Now we have to do some dirty work
    next_epoch_id = fetch_resp.r_last_epoch_id + 1
    # last_weights_to_check = \
    # if last_weights_to_check is not None:
    #     assert fetch_resp.w_last[client_name] == last_weights_to_check
    #     logging.info("REMOTE LAST_WEIGHTS OF THE CLIENT ARE THE SAME AS LOCAL LAST_WEIGHTS")
    logging.info("Creating GST event...")
    gst_event = threading.Thread(target=sleep_then_info, args=(gst_timeout, "GST arrived."))
    gst_event.start()

    # aggregate weights
    logging.info("Aggregating weights...")
    trainer.aggregate_weights(fetch_resp.w_last)

    # test accuracy
    if evaluate:
        logging.info("Evaluating...")
        score = trainer.evaluate()
        logging.info('[AGGREGATED] loss: {0[0]}, accuracy: {0[1]}'.format(score))

    # local_train
    logging.info("Local training...")
    trainer.local_train(callbacks=callbacks)

    cur_weights = trainer.get_serialized_weights()

    # # test accuracy
    # score = await trainer.evaluate()
    # logging.info('[LOCAL_TRAIN] Test loss: {0[0]}, test accuracy: {0[1]}'.format(score))

    # send weights
    logging.info("Updating weights...")
    upd_weight_resp = await committer.update_weights(next_epoch_id, cur_weights)
    logging.debug(f'Collected: {Response.Status.Name(upd_weight_resp.stat)} with {upd_weight_resp.ByteSize()} bytes')
    # if upd_weight_resp.stat == Response.Status.OK:
    #     last_weights_to_check = cur_weights

    # wait_for_GST
    logging.info("Waiting for GST...")
    gst_event.join()

    # vote for new epoch
    logging.info("Voting new epoch %d...", next_epoch_id)
    new_epoch_resp = await committer.new_epoch_vote(next_epoch_id)
    logging.debug(f'Collected: {Response.Status.Name(new_epoch_resp.stat)} with {new_epoch_resp.ByteSize()} bytes')
    # assert r.stat == Response.Status.OK or r.stat == Response.Status.NOT_MEET_QUORUM_WAIT

    return next_epoch_id


def main():
    formatter = logging.Formatter(r"[%(asctime)s - %(levelname)s - %(funcName)s]: %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    main_logger = logging.getLogger()
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('config', type=str, help='Path to config file.')
    args = parser.parse_args()

    with open(args.config, 'r') as f:
        params: ClientConfig = json.load(f)
    
    logging.info("Loaded json config: %s", args.config)
    logging.info("Environments: {}".format(params['env']))
    logging.info("Data config:")
    for k, v in params['data_config'].items():
        logging.info("\t{}: {}".format(k, v))

    for k, v in params['env'].items():
        os.environ[k] = v

    asyncio.run(start(params))


if __name__ == '__main__':
    main()
