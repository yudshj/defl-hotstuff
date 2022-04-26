from .ipc_committer import IpcCommitter
from .local_committer import LocalCommitter
from typing import Union
Committer = Union [IpcCommitter, LocalCommitter]