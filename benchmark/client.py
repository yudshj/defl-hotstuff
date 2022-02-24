#!/opt/homebrew/bin/python3
# ./client 127.0.0.1:9007 --size 1024000 --rate 4 --timeout 1000 2> logs/client-3.log
import argparse
import socket               # 导入 socket 模块
import random
import time
import logging

def length_delimited_send(sock, data):
    length = len(data)
    sock.sendall(length.to_bytes(4, 'big'))
    sock.sendall(data)

def length_delimited_recv(sock):
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
        msg = b"hello, world!" + r.to_bytes(4, 'big')
        length_delimited_send(s, msg)
        resp = length_delimited_recv(s)
        logging.info('response: %s', resp.decode())
        time.sleep(duration)