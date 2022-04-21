import argparse
import asyncio
import gc
import json
import os
import threading
import time
import uuid
from typing import Optional

from defl.aggregator import MultiKrumAggregator, FedAvgAggregator, KrumAggregator, AbstractAggregator
from defl.committer import IpcCommitter
from defl.committer.ipc_committer import ObsidoResponseQueue
from defl.dataloader import Cifar10DataLoader, Sentiment140DataLoader, DataLoader
from defl.trainer import Trainer
from defl.types import ClientConfig
from defl.weightpoisoner import *
from proto.defl_pb2 import Response, WeightsResponse


def sleep_then_info(sleep_time: float, message: str):
    time.sleep(sleep_time)
    logging.info(message)


def _get_aggregator(params: ClientConfig) -> AbstractAggregator:
    # get aggregator type
    if params['aggregator'] == 'multikrum':
        return MultiKrumAggregator(params['multikrum_factor'])
    elif params['aggregator'] == 'krum':
        return KrumAggregator()
    elif params['aggregator'] == 'fedavg':
        return FedAvgAggregator()
    else:
        raise ValueError("Unknown aggregator {}".format(params['aggregator']))


def _get_dataloader(params: ClientConfig) -> DataLoader:
    # get the dataloader of task
    if params['task'] == 'cifar10':
        return Cifar10DataLoader()
    elif params['task'] == 'sentiment140':
        return Sentiment140DataLoader()
    else:
        raise ValueError("Unknown task {}".format(params['task']))


def _get_attack_callback(params: ClientConfig) -> Optional[tf.keras.callbacks.Callback]:
    # get attack method
    if params['attack'] == 'none':
        return None
    elif params['attack'] == 'gaussian':
        assert params['gaussian_attack_factor'] is not None
        return GaussianNoiseWeightPoisoner(params['gaussian_attack_factor'])
    elif params['attack'] == 'sign':
        assert params['signflip_attack_factor'] is not None
        return SignFlipWeightPoisoner(params['signflip_attack_factor'])
    elif params['attack'] == 'label':
        return None
    else:
        raise ValueError("Unknown attack method {}".format(params['attack']))


def _get_label_flip(params: ClientConfig) -> bool:
    return params['attack'] == 'label'


async def start(params: ClientConfig):
    label_flip = _get_label_flip(params)
    dataloader = _get_dataloader(params)
    aggregator = _get_aggregator(params)
    attack_callback = _get_attack_callback(params)

    callbacks: List[tf.keras.callbacks.Callback] = [attack_callback] if attack_callback is not None else []
        

    # learning stuff
    train_data, test_data = dataloader.load_data(params['data_config'], params['batch_size'], label_flip,
                                                 repeat_train=True, shuffle_train=True, train_augmentation=True)
    logging.info("Train step_per_epoch: {}".format(dataloader.train_steps_per_epoch))
    logging.info("Test step_per_epoch: {}".format(dataloader.test_steps_per_epoch))
    model = dataloader.load_model(params['init_model_path'], use_saved_compile=False)
    trainer = Trainer(
        model=model,
        train_data=train_data,
        test_data=test_data,
        local_train_steps=params['local_train_steps'],
        aggregator=aggregator,
        num_byzantine=params['num_byzantine'],
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
    logging.info("+ local_train_steps:  {:36s} +".format('%d' % params['local_train_steps']))
    logging.info("+ save_freq:          {:36s} +".format('%d' % params['save_freq']))
    logging.info("+ batch_size:         {:36s} +".format('%d' % params['batch_size']))
    logging.info("+           -------------- [DeFL] --------------           +")
    logging.info("+ attack:             {:36s} +".format(params['attack']))
    logging.info("+ aggregator:         {:36s} +".format(params['aggregator']))
    logging.info("+ fetch_timeout:      {:36s} +".format('%.2f seconds' % fetch_timeout))
    logging.info("+ gst_timeout:        {:36s} +".format('%.2f seconds' % gst_timeout))
    logging.info("+           ------------- [Attack] -------------           +")
    logging.info("+ gaussian_factor:    {:36s} +".format('{}'.format(params['gaussian_attack_factor'])))
    logging.info("+ signflip_factor:    {:36s} +".format('{}'.format(params['signflip_attack_factor'])))
    logging.info("+           -------------- [Krum] --------------           +")
    logging.info("+ multikrum_factor:   {:36s} +".format('%d' % params['multikrum_factor']))
    logging.info("+ num_byzantine:      {:36s} +".format('%d' % params['num_byzantine']))
    logging.info("++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++")
    logging.info("[INIT LOOP]")
    logging.info("Current epoch id is %d.", epoch_id)
    epoch_id = await client_routine(committer, epoch_id, fetch_queue, 0, gst_timeout, trainer, callbacks,
                                    evaluate=False)
    model_save_path = "./models/{}/epoch_{:05d}.h5".format(client_name, epoch_id)

    i = 0
    while True:
        gc.collect()
        i += 1
        logging.info("[LOOP %d]", i)
        logging.info("Current epoch id is %d. Waiting PASSIVE %.0f seconds...", epoch_id, fetch_timeout)
        try:
            epoch_id = await asyncio.wait_for(client_routine(committer, epoch_id, fetch_queue, fetch_timeout, gst_timeout, trainer, callbacks, evaluate=True), timeout=gst_timeout * 2.5)
        except asyncio.TimeoutError:
            logging.critical("TIMEOUT FOR CLIENT ROUTINE! POSSIBLY A DEADLOCK OCCURRED.")
            await committer.clear_session()
            continue

        if i % params['save_freq'] == 0:
            model_save_path = "./models/{}/epoch_{:05d}.h5".format(client_name, epoch_id)
            trainer.model.save(model_save_path)
            logging.info("Saved model to %s", model_save_path)


async def active_fetch_after(sleep_time: float, committer):
    await asyncio.sleep(sleep_time)
    logging.info("PASSIVE received nothing. Fetching...")
    await committer.fetch_w_last()


async def client_routine(committer: IpcCommitter, epoch_id, fetch_queue: ObsidoResponseQueue, fetch_timeout, gst_timeout: float,
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
    if upd_weight_resp is None:
        logging.critical("[ERROR] Updating weights failed!")
        return epoch_id
    logging.debug(f'Collected: {Response.Status.Name(upd_weight_resp.stat)} with {upd_weight_resp.ByteSize()} bytes')
    # if upd_weight_resp.stat == Response.Status.OK:
    #     last_weights_to_check = cur_weights

    # wait for GST
    logging.info("Waiting for GST...")
    gst_event.join()

    # vote for new epoch
    logging.info("Voting new epoch %d...", next_epoch_id)
    new_epoch_resp = await committer.new_epoch_vote(next_epoch_id)
    if new_epoch_resp is None:
        logging.critical("[ERROR] Voting new epoch failed!")
        return epoch_id
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
