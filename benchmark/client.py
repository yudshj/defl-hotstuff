import argparse
import asyncio
import json
import uuid

from cifar10_dataloader import load_data
from defl.aggregator import MultiKrumAggregator
from defl.committer import IpcCommitter
from defl.committer.ipc_committer import ObsidoResponseQueue
from defl.trainer import Trainer
from defl.types import *
from defl.weightpoisoner import *
from proto.defl_pb2 import Response, WeightsResponse

NUM_BYZANTINE = 1


async def main(params: ClientConfig):
    callbacks = []
    label_flip = False
    if params['attack'] == 'none':
        pass
    elif params['attack'] == 'gaussian':
        callbacks.append(GaussianNoiseWeightPoisoner(1 / 1000))
    elif params['attack'] == 'sign':
        callbacks.append(SignFlipWeightPoisoner(-1))
    elif params['attack'] == 'label':
        label_flip = True
        # raise NotImplementedError("Label-flip poisoning is not implemented yet.")
    else:
        raise ValueError("Unknown poisoning method.")

    # learning stuff
    train_data, test_data = load_data(params['data_config'], params['batch_size'], label_flip)
    model = tf.keras.models.load_model(params['init_model_path'])
    model.compile(optimizer='sgd', loss='categorical_crossentropy', metrics=['accuracy'])
    trainer = Trainer(
        model,
        train_data,
        test_data,
        params['local_train_epochs'],
        MultiKrumAggregator(2),  # KrumAggregator(),
        NUM_BYZANTINE,
    )

    # committer stuff
    client_name = str(uuid.uuid4())
    fetch_queue = ObsidoResponseQueue()
    host, port = params['host'].split(':')
    committer = IpcCommitter(client_name, host, int(port), params['obsido_port'], fetch_queue)
    await committer.committer_bootstrap()

    # defl stuff
    epoch_id = -1

    fetch_timeout = params['fetch'] / 1000.0
    gst_timeout = params['gst'] / 1000.0

    logging.info("[INIT LOOP]")
    logging.info("Current epoch id is %d.", epoch_id)
    epoch_id = await client_routine(committer, epoch_id, fetch_queue, 0, gst_timeout, trainer, callbacks)

    for i in range(1, 100):
        logging.info("[LOOP %d]", i)
        logging.info("Current epoch id is %d. Waiting PASSIVE %.0f seconds...", epoch_id, fetch_timeout)
        epoch_id = await client_routine(committer, epoch_id, fetch_queue, fetch_timeout, gst_timeout, trainer, callbacks)


async def active_fetch_after(sleep_time, committer):
    await asyncio.sleep(sleep_time)
    logging.info("PASSIVE received nothing. Fetching...")
    await committer.fetch_w_last()


async def client_routine(committer, epoch_id, fetch_queue: ObsidoResponseQueue, fetch_timeout, gst_timeout, trainer: Trainer, callbacks: List[tf.keras.callbacks.Callback]):
    active_fetch_task = asyncio.create_task(active_fetch_after(fetch_timeout, committer))
    fetch_resp: WeightsResponse = await fetch_queue.drain()
    active_fetch_task.cancel()

    logging.info(f'Collected: {fetch_resp.request_uuid} with epoch_id={fetch_resp.r_last_epoch_id} and size of {fetch_resp.ByteSize()} bytes')

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
    logging.debug("Creating GST event...")
    gst_event = asyncio.create_task(asyncio.sleep(gst_timeout / 1000.0))
    # aggregate weights
    logging.info("Aggregating weights...")
    trainer.aggregate_weights(fetch_resp.w_last)

    # test accuracy
    score = trainer.evaluate()
    logging.info('[AGGREGATED] Test loss: {0[0]}, test accuracy: {0[1]}'.format(score))

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
    await gst_event

    # vote for new epoch
    logging.info("Voting new epoch %d...", next_epoch_id)
    new_epoch_resp = await committer.new_epoch_vote(next_epoch_id)
    logging.debug(f'Collected: {Response.Status.Name(new_epoch_resp.stat)} with {new_epoch_resp.ByteSize()} bytes')
    # assert r.stat == Response.Status.OK or r.stat == Response.Status.NOT_MEET_QUORUM_WAIT

    return next_epoch_id


if __name__ == '__main__':
    INIT_MODEL_PATH = 'defl/data/init_model.h5'

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

    asyncio.run(main(params))
