import asyncio
import logging
import uuid
from asyncio import Queue, new_event_loop
from typing import Dict

from committer import Committer
from proto.defl_pb2 import ClientRequest, Response, RegisterInfo

from committer.utils import async_length_delimited_recv, async_length_delimited_send


class IpcCommitter(Committer):
    def __init__(self,
                 client_name: str,
                 server_host: str,
                 server_port: int,
                 tx_replica_timeout=1,
                 rx_replica_timeout=3600,
                 listen_backlog=5):
        super().__init__()
        self.client_name = client_name
        self.server_host = server_host
        self.server_port = server_port
        self.tx_replica_timeout = tx_replica_timeout
        self.rx_replica_timeout = rx_replica_timeout
        self.listen_backlog = listen_backlog

        # async net stuff
        self.passive_server = None
        self.active_server = None
        self.replica_tx = None
        self.replica_rx = None

        # async sync stuff
        self.__response_map: Dict[str, Queue] = {}
        self.__response_map_lock = asyncio.Lock()

    async def start_servers(self):
        logging.info('Starting active server')
        self.active_server = await asyncio.start_server(self.handle_active, '127.0.0.1', 0)
        logging.info('Starting passive server')
        self.passive_server = await asyncio.start_server(self.handle_active, '127.0.0.1', 0)
        logging.info('Started servers')

    async def connect_to_server(self):
        while True:
            try:
                self.replica_rx, self.replica_tx = await asyncio.open_connection(self.server_host, self.server_port)
                break
            except ConnectionRefusedError:
                logging.warning('Connection refused, retrying...')
                await asyncio.sleep(0.1)
        logging.info('Connected to server')

    async def handle_active(self, reader, writer):
        while True:
            logging.debug('Handling active connection')
            resp = await async_length_delimited_recv(reader)
            logging.debug(f'Received {len(resp)} bytes')
            response = Response()
            response.ParseFromString(resp)
            logging.debug(f'Trying to acquire lock for {response.request_uuid}')
            async with self.__response_map_lock:
                logging.debug(f'Acquired lock for {response.request_uuid}')
                queue = self.__response_map[response.request_uuid]
                logging.debug(f'Got queue for {response.request_uuid}')
            logging.debug(f'Putting response in queue for {response.request_uuid}')
            await queue.put(response)
            logging.debug(f'Put response in queue for {response.request_uuid}')

    async def transmit(self, client_request: ClientRequest) -> bool:
        msg = client_request.SerializeToString()
        logging.info(f'Transmitting {client_request.request_uuid} with {len(msg)} bytes')
        await async_length_delimited_send(self.replica_tx, msg)
        resp = await async_length_delimited_recv(self.replica_rx)
        resp = resp.decode()
        logging.info(f'Immediate response for {client_request.request_uuid}: {resp}')
        return resp == 'Ack'

    async def collect(self, request_uuid: str) -> Response:
        logging.debug(f'Collecting response for {request_uuid}')
        response_queue = Queue(1)
        logging.debug(f'Trying to acquire lock for {request_uuid}')
        async with self.__response_map_lock:
            logging.debug(f'Acquired lock for {request_uuid}')
            self.__response_map[request_uuid] = response_queue
            logging.debug(f'Added {request_uuid} to response map')
        logging.debug(f'Waiting for response for {request_uuid}')
        response: Response = await response_queue.get()
        logging.debug(f'Got response for {request_uuid}')
        assert type(response) == Response
        return response

    async def client_register(self) -> bool:
        client_request = ClientRequest(
            method=ClientRequest.Method.CLIENT_REGISTER,
            request_uuid=str(uuid.uuid4()),
            register_info=RegisterInfo(
                host='127.0.0.1',
                port=self.active_server.sockets[0].getsockname()[1],  # active_sock.getsockname()[1],
                pasv_host='127.0.0.1',
                pasv_port=self.passive_server.sockets[0].getsockname()[1],
            ),
            client_name=self.client_name,
            target_epoch_id=None,
            weights=None,
        )
        return await self.transmit(client_request)

    async def committer_bootstrap(self) -> bool:
        """Return if the client is successfully registered to the server"""
        await asyncio.wait((
            asyncio.create_task(self.connect_to_server()),
            asyncio.create_task(self.start_servers())))

        # asyncio.create_task(self.active_server.serve_forever())
        # asyncio.create_task(self.passive_server.serve_forever())
        return await self.client_register()

    async def fetch_w_last(self) -> Response:
        client_request = ClientRequest(
            method=ClientRequest.Method.FETCH_W_LAST,
            request_uuid=str(uuid.uuid4()),
            client_name=self.client_name,
            target_epoch_id=None,
            weights=None,
            register_info=None,
        )
        assert await self.transmit(client_request)
        return await self.collect(client_request.request_uuid)

    async def new_weights(self, target_epoch_id: int, weights_b: bytes) -> Response:
        client_request = ClientRequest(
            method=ClientRequest.Method.NEW_WEIGHTS,
            request_uuid=str(uuid.uuid4()),
            client_name=self.client_name,
            target_epoch_id=target_epoch_id,
            weights=weights_b,
            register_info=None,
        )
        assert await self.transmit(client_request)
        return await self.collect(client_request.request_uuid)

    async def new_epoch_request(self, target_epoch_id: int) -> Response:
        client_request = ClientRequest(
            method=ClientRequest.Method.NEW_EPOCH,
            request_uuid=str(uuid.uuid4()),
            client_name=self.client_name,
            target_epoch_id=target_epoch_id,
            weights=None,
            register_info=None,
        )
        assert await self.transmit(client_request)
        return await self.collect(client_request.request_uuid)
