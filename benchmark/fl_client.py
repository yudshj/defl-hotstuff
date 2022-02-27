#!/Users/maghsk/miniforge3/envs/tf/bin/python3
# protoc -I=proto/src/ --python_out=benchmark/proto/ --mypy_out=benchmark/proto/ defl.proto
import argparse
import asyncio
import logging
import uuid

import tensorflow as tf

from defl.aggregator import KrumAggregator
from defl.committer import IpcCommitter
from defl.trainer import Trainer
from proto.defl_pb2 import Response

NUM_BYZANTINE = 1
LOCAL_TRAIN_EPOCHS = 1
INIT_MODEL_PATH = 'defl/data/init_model.h5'

async def load_data():
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
    return train_data, test_data

async def main():
    formatter = logging.Formatter(r"[%(asctime)s - %(levelname)s - %(funcName)s]: %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    main_logger = logging.getLogger()
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('host', help='host', type=str)
    parser.add_argument('--gst', default='2000',
                        help='train time in milliseconds', type=int)
    parser.add_argument('--fetch', default='500',
                        help='train time in milliseconds', type=int)
    parser.add_argument('--timeout', default='1000',
                        help='timeout of sending milliseconds', type=int)
    args = parser.parse_args()

    # learning stuff
    train_data, test_data = await load_data()
    model = tf.keras.models.load_model(INIT_MODEL_PATH)
    model.compile(optimizer='sgd', loss='categorical_crossentropy', metrics=['accuracy'])
    trainer = Trainer(
        model,
        train_data,
        test_data,
        LOCAL_TRAIN_EPOCHS,
        KrumAggregator(),
        NUM_BYZANTINE,
    )

    # committer stuff
    server_host, server_port = args.host.split(':')
    client_name = str(uuid.uuid4())
    committer = IpcCommitter(client_name, server_host, int(server_port), args.timeout / 1000.0)
    await committer.committer_bootstrap()

    # defl stuff
    last_weights = None
    epoch_id = -1
    for i in range(100):
        logging.info("[LOOP %d] Current epoch id is %d. Fetching...", i, epoch_id)
        fetch_resp = await committer.fetch_w_last()
        logging.debug(f'Collected: {Response.Status.Name(fetch_resp.stat)} with {fetch_resp.ByteSize()} bytes')
        if epoch_id <= fetch_resp.r_last_epoch_id:
            if client_name in fetch_resp.w_last:
                assert fetch_resp.w_last[client_name] == last_weights

            logging.debug("Creating GST event...")
            gst_event = asyncio.create_task(asyncio.sleep(args.gst / 1000.0))

            # aggregate weights
            logging.info("Aggregating weights...")
            await trainer.aggregate_weights(fetch_resp.w_last)

            # test accuracy
            score = await trainer.evaluate()
            logging.info('[AGGREGATED] Test loss: {0[0]}, test accuracy: {0[1]}'.format(score))

            # local_train
            logging.info("Local training...")
            cur_weights = await trainer.local_train()

            # test accuracy
            score = await trainer.evaluate()
            logging.info('[LOCAL_TRAIN] Test loss: {0[0]}, test accuracy: {0[1]}'.format(score))

            # send weights
            logging.info("Updating weights...")
            upd_weight_resp = await committer.new_weights(fetch_resp.r_last_epoch_id + 1, cur_weights)
            logging.debug(f'Collected: {Response.Status.Name(upd_weight_resp.stat)} with {upd_weight_resp.ByteSize()} bytes')
            epoch_id = fetch_resp.r_last_epoch_id + 1
            last_weights = cur_weights

            # wait_for_GST
            # TODO: check validity
            logging.info("Waiting for GST...")
            await gst_event

            logging.info("Voting new epoch...")
            new_epoch_resp = await committer.new_epoch_request(epoch_id)
            logging.debug(f'Collected: {Response.Status.Name(new_epoch_resp.stat)} with {new_epoch_resp.ByteSize()} bytes')
            # assert r.stat == Response.Status.OK or r.stat == Response.Status.NOT_MEET_QUORUM_WAIT
        else:
            # fetch burst
            logging.info("+++ Remote is not updated. Waiting for a next fetch...")
            await asyncio.sleep(args.fetch / 1000.0)


if __name__ == '__main__':
    asyncio.run(main())
