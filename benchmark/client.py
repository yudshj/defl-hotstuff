#!/opt/homebrew/bin/python3
# ./client 127.0.0.1:9007 --size 1024000 --rate 4 --timeout 1000 2> logs/client-3.log
# +++++++++
# protoc -I=proto/src/ --python_out=benchmark/proto/ --mypy_out=benchmark/proto/ defl.proto
import argparse
import asyncio
import logging
import random
import time
import uuid

from committer import IpcCommitter


async def main():
    formatter = logging.Formatter(r"[%(asctime)s - %(funcName)s - %(levelname)s]: %(message)s")
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    main_logger = logging.getLogger()
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('host', help='host', type=str)
    parser.add_argument('--size', default='1024000',
                        help='size of file to send', type=int)
    parser.add_argument('--rate', default='4',
                        help='rate of sending', type=int)
    parser.add_argument('--timeout', default='1000',
                        help='timeout of sending (miliseconds)', type=int)

    args = parser.parse_args()
    h, p = args.host.split(':')

    r = random.randint(1, 1000000000)
    duration = 1.0 / args.rate
    client_name = str(uuid.uuid4())
    committer = IpcCommitter(client_name, h, int(p), args.timeout / 1000.0)
    await committer.committer_bootstrap()
    while True:
        r += 1
        response = await committer.fetch_w_last()
        logging.info(f'\n++++++++++++ [Collect] +++++++++++++\n{response}++++++++++++++++++++++++++++++++++++')
        await asyncio.sleep(duration)

if __name__ == '__main__':
    asyncio.run(main())
