#!/opt/homebrew/bin/python3.10
import subprocess
import argparse
import json

from benchmark.commands import CommandMaker
from benchmark.config import Key, LocalCommittee, NodeParameters
from benchmark.utils import PathMaker

# Generate configuration files.

def generate_config(node_params: dict, base_port: int, num_nodes: int):
    keys = []
    key_files = [PathMaker.key_file(i) for i in range(num_nodes)]
    for filename in key_files:
        cmd = CommandMaker.generate_key(filename).split()
        subprocess.run(cmd, check=True)
        keys += [Key.from_file(filename)]

    names = [x.name for x in keys]
    committee = LocalCommittee(names, base_port)
    committee.print(PathMaker.committee_file())
    NodeParameters(node_params).print(PathMaker.parameters_file())
    return committee


if __name__ == '__main__':
    NODES = 4
    BASE_PORT = 9000
    NODE_PARAMS = {
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

    parser = argparse.ArgumentParser()
    parser.add_argument('--nodes', type=int, default=NODES)
    parser.add_argument('--base_port', type=int, default=BASE_PORT)
    parser.add_argument('--node_params_json_path', type=str, required=False)
    args = parser.parse_args()

    node_params = NODE_PARAMS
    if args.node_params_json_path is not None:
        with open(args.node_params_json_path, 'r') as f:
            node_params = json.load(f)
    committee = generate_config(node_params, args.base_port, args.nodes)
    print(json.dumps(committee.front))