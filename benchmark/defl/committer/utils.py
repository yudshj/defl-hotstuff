import logging
from socket import socket
from asyncio import StreamReader, StreamWriter


class LengthDelimitedCodec:
    def __init__(self, length_field_length: int):
        self.length_field_length = length_field_length

    def length_delimited_send(self, sock: socket, data: bytes):
        length = len(data)
        sock.send(length.to_bytes(self.length_field_length, byteorder='big', signed=False) + data)

    def length_delimited_recv(self, sock: socket) -> bytes:
        length = sock.recv(self.length_field_length)
        length = int.from_bytes(length, byteorder='big', signed=False)
        payload = sock.recv(length)
        return payload

    async def async_length_delimited_recv(self, reader: StreamReader):
        length = await reader.readexactly(self.length_field_length)
        length = int.from_bytes(length, byteorder='big', signed=False)
        logging.debug(f'Ought to receive {length} bytes')
        payload = await reader.readexactly(length)
        return payload

    async def async_length_delimited_send(self, writer: StreamWriter, data: bytes):
        length = len(data)
        logging.debug(f'Ought to send {length} bytes')
        writer.write(length.to_bytes(self.length_field_length, byteorder='big', signed=False) + data)
        await writer.drain()
