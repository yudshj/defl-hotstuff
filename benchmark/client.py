#!/opt/homebrew/bin/python3
# ./client 127.0.0.1:9007 --size 1024000 --rate 4 --timeout 1000 2> logs/client-3.log
# +++++++++
# protoc -I=proto/src/ --python_out=benchmark/proto/ --mypy_out=benchmark/proto/ defl.proto
import argparse
import asyncio
import logging
import random
import time
from google.protobuf import text_format
import uuid

from committer import IpcCommitter
from proto.defl_pb2 import Response


async def main():
    formatter = logging.Formatter(r"[%(asctime)s - %(funcName)s - %(levelname)s]: %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    main_logger = logging.getLogger()
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('host', help='host', type=str)
    parser.add_argument('--size', default='1024',
                        help='size of file to send', type=int)
    parser.add_argument('--train', default='500',
                        help='train time in milliseconds', type=int)
    parser.add_argument('--gst', default='2000',
                        help='train time in milliseconds', type=int)
    parser.add_argument('--fetch', default='500',
                        help='train time in milliseconds', type=int)
    parser.add_argument('--timeout', default='1000',
                        help='timeout of sending (miliseconds)', type=int)

    args = parser.parse_args()
    h, p = args.host.split(':')

    epoch_id = -1
    client_name = str(uuid.uuid4())
    committer = IpcCommitter(client_name, h, int(p), args.timeout / 1000.0)
    await committer.committer_bootstrap()
    last_weights = None
    for i in range(100):
        w_last_resp = await committer.fetch_w_last()
        logging.info(f'{w_last_resp.request_uuid} Collected: {Response.Status.Name(w_last_resp.stat)} with {w_last_resp.ByteSize()} bytes')
        r_last_epoch_id = w_last_resp.r_last_epoch_id
        if epoch_id <= r_last_epoch_id:
            if client_name in w_last_resp.w_last:
                assert w_last_resp.w_last[client_name] == last_weights

            await asyncio.sleep(args.train / 1000.0)

            cur_weights = random.randbytes(args.size)
            logging.info("sending new weights")
            r = await committer.new_weights(r_last_epoch_id + 1, cur_weights)
            logging.info(f'{r.request_uuid} Collected: {Response.Status.Name(r.stat)} with {r.ByteSize()} bytes')
            assert r.stat == Response.Status.OK
            epoch_id = r_last_epoch_id + 1
            last_weights = cur_weights

            await asyncio.sleep(args.gst / 1000.0)

            logging.info("sending new epoch request")
            r = await committer.new_epoch_request(epoch_id)
            logging.info(f'{r.request_uuid} Collected: {Response.Status.Name(r.stat)} with {r.ByteSize()} bytes')
            assert r.stat == Response.Status.OK or r.stat == Response.Status.NOT_MEET_QUORUM_WAIT
        else:
            await asyncio.sleep(args.fetch / 1000.0)


if __name__ == '__main__':
    asyncio.run(main())
