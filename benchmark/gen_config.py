#!/opt/homebrew/bin/python3.10
import subprocess

from benchmark.commands import CommandMaker
from benchmark.config import Key, LocalCommittee, NodeParameters
from benchmark.utils import PathMaker

# Generate configuration files.

NODES = 4
BASE_PORT = 9000

''' Run benchmarks on localhost '''
node_params = {
    'consensus': {
        'timeout_delay': 1_000,
        'sync_retry_delay': 10_000,
    },
    'mempool': {
        'gc_depth': 50,
        'sync_retry_delay': 5_000,
        'sync_retry_nodes': 3,
        'batch_size': 15_000,
        'max_batch_delay': 100
    }
}

keys = []
key_files = [PathMaker.key_file(i) for i in range(NODES)]
for filename in key_files:
    cmd = CommandMaker.generate_key(filename).split()
    subprocess.run(cmd, check=True)
    keys += [Key.from_file(filename)]

names = [x.name for x in keys]
committee = LocalCommittee(names, 9000)
committee.print(PathMaker.committee_file())
NodeParameters(node_params).print(PathMaker.parameters_file())
# TODO: add run scripts
