from asyncio import StreamReader, StreamWriter
import socket


def length_delimited_send(sock: socket.socket, data: bytes):
    length = len(data)
    sock.sendall(length.to_bytes(4, 'big'))
    sock.sendall(data)


def length_delimited_recv(sock: socket.socket) -> bytes:
    length = sock.recv(4)
    length = int.from_bytes(length, 'big')
    payload = sock.recv(length)
    return payload


def recv_1024(sock: socket.socket) -> bytes:
    return sock.recv(1024)


async def async_length_delimited_recv(reader: StreamReader):
    length = await reader.read(4)
    length = int.from_bytes(length, 'big')
    payload = await reader.read(length)
    return payload


async def async_length_delimited_send(writer: StreamWriter, data: bytes):
    length = len(data)
    writer.write(length.to_bytes(4, 'big'))
    writer.write(data)
    await writer.drain()
