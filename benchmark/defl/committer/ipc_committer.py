import asyncio
import logging
import uuid
from asyncio import IncompleteReadError, Queue, StreamReader, StreamWriter
from typing import Dict, Optional

from defl.committer.utils import LengthDelimitedCodec
from proto.defl_pb2 import ClientRequest, Response, RegisterInfo, WeightsResponse, ObsidoRequest


class IpcCommitter:
    def __init__(self,
                 client_name: str,
                 server_host: str,
                 consensus_port: int,
                 obsido_port: int,
                 fetch_queue: Queue,
                 listen_backlog=5):
        self.client_name = client_name
        self.server_host = server_host
        self.consensus_port = consensus_port
        self.obsido_port = obsido_port
        self.listen_backlog = listen_backlog

        # async net stuff
        self.passive_server: asyncio.base_events.Server
        self.active_server: asyncio.base_events.Server
        self.replica_tx: StreamWriter
        self.replica_rx: StreamReader
        self.obsido_tx: StreamWriter
        self.obsido_rx: StreamReader
        self.codec = LengthDelimitedCodec(8)
        self.fetch_queue = fetch_queue

        # async sync stuff
        self.__response_map: Dict[str, Queue] = {}
        self.__response_map_lock = asyncio.Lock()

    async def clear_session(self):
        self.obsido_tx.close()
        await self.obsido_tx.wait_closed()
        self.obsido_rx, self.obsido_tx = await asyncio.open_connection(self.server_host, self.obsido_port)

        self.replica_tx.close()
        await self.replica_tx.wait_closed()
        self.replica_rx, self.replica_tx = await asyncio.open_connection(self.server_host, self.consensus_port)

        async with self.__response_map_lock:
            logging.critical("Response map: %s", self.__response_map)
            # clear the map
            for v in self.__response_map.values():
                del v
            self.__response_map.clear()
            logging.critical("Response map: %s", self.__response_map)

    async def connect_to_server(self):
        while True:
            try:
                self.replica_rx, self.replica_tx = await asyncio.open_connection(self.server_host, self.consensus_port)
                self.obsido_rx, self.obsido_tx = await asyncio.open_connection(self.server_host, self.obsido_port)
                break
            except ConnectionRefusedError:
                logging.warning('Connection refused, retrying...')
                await asyncio.sleep(0.1)
        logging.info('Connected to server')

    async def transmit(self, client_request, tx, rx) -> bool:
        msg = client_request.SerializeToString()
        logging.debug(
            f'Transmitting [{client_request.request_uuid}] {client_request.Method.Name(client_request.method)} with {len(msg)} bytes')
        await self.codec.async_length_delimited_send(tx, msg)
        resp = await self.codec.async_length_delimited_recv(rx)
        resp = resp.decode()
        logging.debug(f'Immediate response: {resp}')
        return resp == 'Ack'

    async def handle_active(self, reader: StreamReader, writer: StreamWriter):
        while True:
            try:
                resp = await self.codec.async_length_delimited_recv(reader)
            except IncompleteReadError:
                # What the fuck with asyncio?
                logging.warning('Incomplete read, closing writer...')
                writer.close()
                await writer.wait_closed()
                await asyncio.sleep(0.1)
                continue

            logging.info(f'Received {len(resp)} bytes')
            response = Response()
            response.ParseFromString(resp)
            logging.debug(f'HANDLE [{response.request_uuid}] {Response.Status.Name(response.stat)}\tresponse_uuid={response.response_uuid}')
            logging.debug("acquiring `self.__response_map_lock`")
            async with self.__response_map_lock:
                if response.request_uuid in self.__response_map:
                    queue = self.__response_map[response.request_uuid]
                    del self.__response_map[response.request_uuid]
                else:
                    logging.warning(f'Received response for unknown request {response.request_uuid}')
            logging.debug("released `self.__response_map_lock`")
            await queue.put(response)

    async def handle_passive(self, reader: StreamReader, writer: StreamWriter):
        while True:
            try:
                resp = await self.codec.async_length_delimited_recv(reader)
            except IncompleteReadError:
                # What the fuck with asyncio?
                logging.warning('LAST_WEIGHTS Incomplete read, closing writer...')
                writer.close()
                await writer.wait_closed()
                await asyncio.sleep(0.1)
                continue

            logging.info(f'LAST_WEIGHTS Received {len(resp)} bytes')
            response = WeightsResponse()
            response.ParseFromString(resp)
            logging.debug(f'LAST_WEIGHTS HANDLE [{response.response_uuid}]')
            await self.fetch_queue.put(response)

    async def collect(self, client_request_uuid) -> Optional[Response]:
        request_uuid = client_request_uuid
        response_queue: Queue = Queue(1)
        logging.debug("acquiring `self.__response_map_lock`")
        async with self.__response_map_lock:
            self.__response_map[request_uuid] = response_queue
        logging.debug("released `self.__response_map_lock`")
        logging.debug(f'Waiting for response for {request_uuid} by queue.get()')
        response: Response = await response_queue.get()
        assert type(response) == Response
        logging.debug(f'COLLECT [{response.request_uuid}] {Response.Status.Name(response.stat)}\tresponse_uuid={response.response_uuid}')
        return response

    async def client_register(self) -> bool:
        client_request = ObsidoRequest(
            method=ObsidoRequest.Method.CLIENT_REGISTER,
            request_uuid=str(uuid.uuid4()),
            register_info=RegisterInfo(
                host='127.0.0.1',
                port=self.active_server.sockets[0].getsockname()[1],
                pasv_host='127.0.0.1',
                pasv_port=self.passive_server.sockets[0].getsockname()[1],
            ),
            client_name=self.client_name,
        )
        return await self.transmit(client_request, self.obsido_tx, self.obsido_rx)

    async def committer_bootstrap(self) -> bool:
        """Return if the client is successfully registered to the server"""
        await self.connect_to_server()

        # starting servers
        self.active_server = await asyncio.start_server(self.handle_active, '127.0.0.1', 0)
        self.passive_server = await asyncio.start_server(self.handle_passive, '127.0.0.1', 0)
        logging.info('Started servers')

        asyncio.create_task(self.active_server.serve_forever())
        asyncio.create_task(self.passive_server.serve_forever())
        return await self.client_register()

    async def fetch_w_last(self):
        client_request = ObsidoRequest(
            method=ObsidoRequest.Method.FETCH_W_LAST,
            request_uuid=str(uuid.uuid4()),
            client_name=self.client_name,
            register_info=None,
        )
        try:
            assert await self.transmit(client_request, self.obsido_tx, self.obsido_rx)
        except AssertionError:
            logging.error('Failed to transmit FETCH_W_LAST')
        except asyncio.CancelledError:
            self.obsido_tx.close()
            await self.obsido_tx.wait_closed()
            self.obsido_rx, self.obsido_tx = await asyncio.open_connection(self.server_host, self.obsido_port)

    async def update_weights(self, target_epoch_id: int, weights_b: bytes) -> Optional[Response]:
        client_request = ClientRequest(
            method=ClientRequest.Method.UPD_WEIGHTS,
            request_uuid=str(uuid.uuid4()),
            client_name=self.client_name,
            target_epoch_id=target_epoch_id,
            weights=weights_b,
        )
        try:
            assert await self.transmit(client_request, self.replica_tx, self.replica_rx)
        except AssertionError:
            logging.error('Failed to transmit UPD_WEIGHTS')
            return None
        except asyncio.CancelledError:
            self.replica_tx.close()
            await self.replica_tx.wait_closed()
            self.replica_rx, self.replica_tx = await asyncio.open_connection(self.server_host, self.consensus_port)
        try:
            return await self.collect(client_request.request_uuid)
        except asyncio.CancelledError:
            logging.debug("acquiring `self.__response_map_lock`")
            async with self.__response_map_lock:
                if client_request.request_uuid in self.__response_map:
                    del self.__response_map[client_request.request_uuid]
            logging.debug("released `self.__response_map_lock`")
            return None

    async def new_epoch_vote(self, target_epoch_id: int) -> Optional[Response]:
        client_request = ClientRequest(
            method=ClientRequest.Method.NEW_EPOCH_VOTE,
            request_uuid=str(uuid.uuid4()),
            client_name=self.client_name,
            target_epoch_id=target_epoch_id,
            weights=None,
        )
        try:
            assert await self.transmit(client_request, self.replica_tx, self.replica_rx)
        except AssertionError:
            logging.error('Failed to transmit NEW_EPOCH_VOTE')
            return None
        except asyncio.CancelledError:
            self.replica_tx.close()
            await self.replica_tx.wait_closed()
            self.replica_rx, self.replica_tx = await asyncio.open_connection(self.server_host, self.consensus_port)
        try:
            return await self.collect(client_request.request_uuid)
        except asyncio.CancelledError:
            logging.debug("acquiring `self.__response_map_lock`")
            async with self.__response_map_lock:
                if client_request.request_uuid in self.__response_map:
                    del self.__response_map[client_request.request_uuid]
            logging.debug("released `self.__response_map_lock`")
            return None


class ObsidoResponseQueue(asyncio.Queue):
    def __init__(self):
        super().__init__()

    async def drain(self) -> WeightsResponse:
        fetch_resp: WeightsResponse = await self.get()
        logging.debug(f"response_uuid={fetch_resp.response_uuid} epoch_id={fetch_resp.r_last_epoch_id}")
        while True:
            try:
                pending_fetch_resp = self.get_nowait()
                logging.debug(f"response_uuid={pending_fetch_resp.response_uuid} epoch_id={fetch_resp.r_last_epoch_id}")
                if fetch_resp.r_last_epoch_id < pending_fetch_resp.r_last_epoch_id:
                    fetch_resp = pending_fetch_resp
            except asyncio.QueueEmpty:
                break
        return fetch_resp
