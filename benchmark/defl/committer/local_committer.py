import asyncio
import logging
from pathlib import Path
import uuid
from typing import Dict, Optional
import sqlite3
import time

from proto.defl_pb2 import ClientRequest, Response, RegisterInfo, WeightsResponse, ObsidoRequest


class LocalCommitter:
    def __init__(self, client_name: str, base_dir: str, quorum_size: int):
        self.client_name: str = client_name
        self.base_dir: str = base_dir
        self.sql_conn = sqlite3.connect(Path(base_dir) / 'blockchain.db')
        self.quorum_size = quorum_size

    def committer_bootstrap(self) -> bool:
        return True

    def update_weights(self, target_epoch_id: int, weights_b: bytes) -> Optional[Response]:
        path = Path(self.base_dir) / 'weights' / f'{target_epoch_id}' / f'{self.client_name}.weights'
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            f.write(weights_b)
        sqlcmd = """
            INSERT INTO upd(client_name, epoch_id, file_path)
            VALUES (?, ?, ?)"""
        self.sql_conn.execute(sqlcmd, (self.client_name, target_epoch_id, path.absolute().as_posix()))
        self.sql_conn.commit()
        return Response(stat=Response.Status.OK)

    def new_epoch_vote(self, target_epoch_id: int) -> Optional[Response]:
        # sqlcmd = """
        #     INSERT INTO nev(client_name, epoch_id)
        #     VALUES (?, ?)"""
        # self.sql_conn.execute(sqlcmd, (self.client_name, target_epoch_id))
        # self.sql_conn.commit()
        return Response(stat=Response.Status.OK)

    def fetch_w_last(self, expected_last_epoch_id, **_kwargs) -> WeightsResponse:
        if expected_last_epoch_id < 0:
            return WeightsResponse(r_last_epoch_id=0, w_last={})
        sqlcmd = """
            SELECT client_name, file_path
            FROM upd
            WHERE epoch_id = ?"""
        while True:
            updates = self.sql_conn.execute(sqlcmd, (expected_last_epoch_id,)).fetchall()
            if len(updates) >= self.quorum_size:
                break
            time.sleep(1)
        w_last = {x[0]: open(x[1], 'rb').read() for x in updates}
        return WeightsResponse(r_last_epoch_id=expected_last_epoch_id, w_last=w_last)

    def clear_session(self):
        self.sql_conn.close()
        self.sql_conn = sqlite3.connect(Path(self.base_dir) / 'blockchain.db')
        pass