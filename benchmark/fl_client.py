#!/Users/maghsk/miniforge3/envs/tf/bin/python3
# protoc -I=proto/src/ --python_out=benchmark/proto/ --mypy_out=benchmark/proto/ defl.proto
import argparse
import asyncio
import uuid

import tensorflow as tf

from defl.aggregator import MultiKrumAggregator
from defl.committer import IpcCommitter
from defl.committer.ipc_committer import ObsidoResponseQueue
from defl.trainer import Trainer
from defl.weightpoisoner import *
from proto.defl_pb2 import WeightsResponse, Response

NUM_BYZANTINE = 1
LOCAL_TRAIN_EPOCHS = 1
INIT_MODEL_PATH = 'defl/data/init_model.h5'


def load_data():
    (x_train, y_train), (x_test, y_test) = tf.keras.datasets.cifar10.load_data()
    x_train = x_train[:1000]
    y_train = y_train[:1000]
    x_train = x_train.astype('float32')
    x_test = x_test.astype('float32')
    x_train /= 255
    x_test /= 255
    y_train = tf.keras.utils.to_categorical(y_train, 10)
    y_test = tf.keras.utils.to_categorical(y_test, 10)
    train_data = (x_train, y_train)
    test_data = (x_test, y_test)
    # just for fun~
    return train_data, test_data


async def main(params):
    if params.attack == 'none':
        poisoner = None
    elif params.attack == 'gaussian':
        poisoner = GaussianNoiseWeightPoisoner(1 / 1000)
    elif params.attack == 'sign':
        poisoner = SignFlipWeightPoisoner(-4)
    elif params.attack == 'label':
        raise NotImplementedError("Label-flip poisoning is not implemented yet.")
    else:
        raise ValueError("Unknown poisoning method.")

    # learning stuff
    train_data, test_data = load_data()
    model = tf.keras.models.load_model(INIT_MODEL_PATH)
    model.compile(optimizer='sgd', loss='categorical_crossentropy', metrics=['accuracy'])
    trainer = Trainer(
        model,
        train_data,
        test_data,
        LOCAL_TRAIN_EPOCHS,
        MultiKrumAggregator(2),  # KrumAggregator(),
        NUM_BYZANTINE,
    )

    # committer stuff
    client_name = str(uuid.uuid4())
    fetch_queue = ObsidoResponseQueue()
    committer = IpcCommitter(client_name, params.host, params.port, params.obsido_port, fetch_queue)
    await committer.committer_bootstrap()

    # defl stuff
    epoch_id = -1

    fetch_timeout = params.fetch / 1000.0
    gst_timeout = params.gst / 1000.0

    logging.info("[INIT LOOP]")
    logging.info("Current epoch id is %d.", epoch_id)
    epoch_id = await client_routine(committer, epoch_id, fetch_queue, 0, gst_timeout, trainer, poisoner)

    for i in range(1, 100):
        logging.info("[LOOP %d]", i)
        logging.info("Current epoch id is %d. Waiting PASSIVE %.0f seconds...", epoch_id, fetch_timeout)
        epoch_id = await client_routine(committer, epoch_id, fetch_queue, fetch_timeout, gst_timeout, trainer, poisoner)


async def active_fetch_after(sleep_time, committer):
    await asyncio.sleep(sleep_time)
    logging.info("PASSIVE received nothing. Fetching...")
    await committer.fetch_w_last()


async def client_routine(committer, epoch_id, fetch_queue: ObsidoResponseQueue, fetch_timeout, gst_timeout, trainer: Trainer, poisoner: WeightPoisoner):
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

    # # test accuracy
    # score = await trainer.evaluate()
    # logging.info('[AGGREGATED] Test loss: {0[0]}, test accuracy: {0[1]}'.format(score))

    # local_train
    logging.info("Local training...")
    trainer.local_train(poisoner=poisoner)

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
    formatter = logging.Formatter(r"[%(asctime)s - %(levelname)s - %(funcName)s]: %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    main_logger = logging.getLogger()
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('host', help='host', type=str)
    parser.add_argument('port', help='port', type=int)
    parser.add_argument('obsido_port', help='obsido_port', type=int)
    parser.add_argument('--attack', help='Attack method', choices=['none', 'gaussian', 'sign', 'label'], default='none')

    # 3 seconds
    parser.add_argument('--gst', default='3000', help='train time in milliseconds', type=int)

    # 20 seconds
    parser.add_argument('--fetch', default='20000', help='train time in milliseconds', type=int)

    args = parser.parse_args()

    asyncio.run(main(args))
