#!/opt/homebrew/bin/python3
# ./client 127.0.0.1:9007 --size 1024000 --rate 4 --timeout 1000 2> logs/client-3.log
# +++++++++
# in proto/src/ :
# protoc -I=. --python_out=../../benchmark/proto/ --mypy_out=../../benchmark/proto/ defl.proto
import argparse
import json
import socket  # 导入 socket 模块
import random
import time
import logging
from io import BytesIO
import uuid
from typing import TypedDict
from proto.defl_pb2 import ClientRequest, MetaInfo, RequestMethod


def client_request_to_bytes(client_request: ClientRequest) -> bytes:
    return client_request.SerializeToString()


def length_delimited_send(sock: socket.socket, data: bytes):
    length = len(data)
    sock.sendall(length.to_bytes(4, 'big'))
    sock.sendall(data)


def length_delimited_recv(sock: socket.socket) -> bytes:
    length = int.from_bytes(sock.recv(4), 'big')
    return sock.recv(length)


if __name__ == '__main__':
    main_logger = logging.getLogger()
    main_logger.addHandler(logging.StreamHandler())
    main_logger.setLevel(logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('host', help='host', type=str)
    parser.add_argument('--size', default='1024000', help='size of file to send', type=int)
    parser.add_argument('--rate', default='4', help='rate of sending', type=int)
    parser.add_argument('--timeout', default='1000', help='timeout of sending (miliseconds)', type=int)

    args = parser.parse_args()
    h, p = args.host.split(':')
    sock_addr = (h, int(p))

    r = random.randint(1, 1000000000)
    duration = 1.0 / args.rate

    while True:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(args.timeout / 1000.0)
        try:
            s.connect(sock_addr)
            s.close()
            break
        except:
            time.sleep(0.1)
            continue

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(args.timeout / 1000.0)
    s.connect(sock_addr)
    while True:
        r += 1
        meta: MetaInfo = MetaInfo(
            method=RequestMethod.FETCH_W_LAST,
            request_uuid=str(uuid.uuid4()),
            listen_host="127.0.0.1",
            listen_port=8080,
            client_name="foobar1",
            target_epoch_id=1,
        )
        weights = r.to_bytes(4, 'big')
        client_request: ClientRequest = ClientRequest(
            meta=meta,
            weights=weights,
        )
        msg = client_request.SerializeToString()
        length_delimited_send(s, msg)
        resp = length_delimited_recv(s)
        logging.info('response: %s', resp.decode())
        time.sleep(duration)
