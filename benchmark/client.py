#!/opt/homebrew/bin/python3
# ./client 127.0.0.1:9007 --size 1024000 --rate 4 --timeout 1000 2> logs/client-3.log
# +++++++++
# in proto/src/ :
# protoc -I=. --python_out=../../benchmark/proto/ --mypy_out=../../benchmark/proto/ defl.proto
import argparse
import logging
import random
import select
import socket  # 导入 socket 模块
import time
import uuid

# import select
from proto.defl_pb2 import ClientRequest, RegisterInfo


def length_delimited_send(sock: socket.socket, data: bytes):
    length = len(data)
    sock.sendall(length.to_bytes(4, 'big'))
    sock.sendall(data)


def length_delimited_recv(sock: socket.socket) -> bytes:
    length = int.from_bytes(sock.recv(4), 'big')
    logging.info("ought to recv %d bytes", length)
    return sock.recv(length)


def recv_1024(sock: socket.socket) -> bytes:
    return sock.recv(1024)


if __name__ == '__main__':
    main_logger = logging.getLogger()
    main_logger.addHandler(logging.StreamHandler())
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
    sock_addr = (h, int(p))

    r = random.randint(1, 1000000000)
    duration = 1.0 / args.rate

    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(args.timeout / 1000.0)
        try:
            sock.connect(sock_addr)
            break
        except:
            time.sleep(0.1)
            continue

    pasv_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    pasv_sock.settimeout(6000)
    pasv_sock.bind(('127.0.0.1', 0))
    pasv_sock.listen(5)

    post_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    post_sock.settimeout(6000)
    post_sock.bind(('127.0.0.1', 0))
    post_sock.listen(5)

    register_info = RegisterInfo(
        pasv_host='127.0.0.1',
        pasv_port=pasv_sock.getsockname()[1],
        host='127.0.0.1',
        port=post_sock.getsockname()[1],
    )
    logging.info(f"{register_info}")
    client_request = ClientRequest(
        method=ClientRequest.Method.CLIENT_REGISTER,
        request_uuid=str(uuid.uuid4()),
        register_info=register_info,
        client_name=str(uuid.uuid4()),
        target_epoch_id=1,
        weights=None,
    )
    msg = client_request.SerializeToString()
    length_delimited_send(sock, msg)
    resp = length_delimited_recv(sock)
    logging.info('Register response: %s', resp.decode())

    client_request.method = ClientRequest.Method.FETCH_W_LAST
    inputs_list = [post_sock, sock]
    while True:
        r += 1
        weights = r.to_bytes(4, 'big')
        client_request.weights = weights
        client_request.request_uuid = str(uuid.uuid4())
        client_request.ClearField('register_info')

        msg = client_request.SerializeToString()
        length_delimited_send(sock, msg)

        cnt = 0
        while cnt < 2:
            logging.info("++selecting...")
            read_sockets, write_sockets, error_sockets = select.select(inputs_list, [], [], None)
            for s in read_sockets:
                if s is sock:
                    cnt += 1
                    logging.info('recv from sock')
                    resp = length_delimited_recv(sock)
                    assert resp.decode() == 'Ack'
                    logging.info('Ack for FWL')
                elif s is post_sock:
                    conn, addr = s.accept()
                    inputs_list.append(conn)
                else:
                    cnt += 1
                    logging.info('recv from post_sock')
                    resp = length_delimited_recv(s)
                    logging.info('positive response: %s', [x for x in resp])

            for s in error_sockets:
                # remove s from inputs_list
                inputs_list.remove(s)

        time.sleep(duration)
        logging.info('')
