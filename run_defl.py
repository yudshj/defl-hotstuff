import argparse
import json
import logging
import os
import shutil
import subprocess
import typing
from logging import info, warning
from time import sleep
from benchmark.defl.types import *

PYTHON_PATH = os.path.abspath(shutil.which('python3'))
NODE_PATH = os.path.abspath('./benchmark/node')


def gen_client_cmd(python_path: str, client_name: str, client_config_path: str):
    return '{} client.py {} 2> logs/{}.log'.format(
        python_path,
        client_config_path,
        client_name
    )


def gen_server_cmd(rust_node_path: str, id: int, obsido_port: int):
    return (
        f"{rust_node_path} -vv run "
        f"--obsido {obsido_port} "
        f"--keys .node-{id}.json "
        f"--committee .committee.json "
        f"--store .db-{id} "
        f"--parameters .parameters.json "
        f"2> logs/node-{id}.log"
    )


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

    parser = argparse.ArgumentParser()
    parser.add_argument('--sleep_sec', type=int, default=150)
    parser.add_argument('--config', type=str, default="defl_config.json")
    args = parser.parse_args()

    conf = json.load(open(args.config, 'r'))
    committee_base_port = conf["committee_base_port"]
    obsido_base_port = conf["obsido_base_port"]
    client_config_list: typing.List[ClientConfig] = conf["client_config"]

    node_params_json_path = os.path.abspath(conf["node_params_path"])
    init_model_path = os.path.abspath(conf["init_model_path"])

    num_nodes = len(client_config_list)

    info("Generating configs for server nodes...")
    p = subprocess.run(
        ["./gen_config.py", "--nodes", str(num_nodes), "--base_port", str(committee_base_port),
         "--node_params_json_path", node_params_json_path],
        capture_output=True,
        cwd='./benchmark',
        check=True
    )
    info("Generated configs for server nodes")

    committee_front = json.loads(p.stdout)

    for id, cur_client_config in enumerate(client_config_list):
        assert('attack' in cur_client_config)
        assert('batch_size' in cur_client_config)
        assert('tfds_config' in cur_client_config)

        if 'name' not in cur_client_config:
            cur_client_config['name'] = "client-" + str(id)
        if 'obsido_port' not in cur_client_config:
            cur_client_config['obsido_port'] = obsido_base_port + id
        if 'host' not in cur_client_config:
            cur_client_config['host'] = committee_front[id]
        if 'init_model_path' not in cur_client_config:
            cur_client_config['init_model_path'] = init_model_path
        if 'fetch' not in cur_client_config:
            cur_client_config['fetch'] = 20_000
        if 'gst' not in cur_client_config:
            cur_client_config['gst'] = 6_000

    info("Compiling protobuf code...")
    p = subprocess.run(
        ['protoc', '-I=proto/src/', '--python_out=benchmark/proto/', '--mypy_out=benchmark/proto/', 'defl.proto'],
        capture_output=False,
        check=True
    )
    info("Compiled protobuf code")

    info("Compiling rust node...")
    p = subprocess.run(['cargo', 'build', '--release', '-j8'], capture_output=False, check=True)
    info("Compiled rust node")

    info("Cleaning up old databases...")
    p = subprocess.run(['fd', '-HI', '^.db-[0-9]+$', 'benchmark', '-x', 'rm', '-rf', '{}'], capture_output=False,
                       check=True)
    info("Cleaned up old databases")


    client_sessions = []
    server_sessions = []

    info("Generating configs for client nodes...")
    for id, client_config in enumerate(client_config_list):
        file_name = '.{}.json'.format(client_config['name'])
        path = os.path.join('benchmark', file_name)
        path = os.path.abspath(path)
        with open(path, 'w') as f:
            json.dump(client_config, f)
        
        client_sessions.append((client_config['name'], gen_client_cmd(PYTHON_PATH, client_config['name'], path), './benchmark'))
        server_sessions.append((f'node-{id}', gen_server_cmd(NODE_PATH, id, client_config['obsido_port']), './benchmark'))

    all_sessions = client_sessions + server_sessions

    print("  Session configs: (name, cmd, cwd)")
    for item in all_sessions:
        print('    ', item)

    info("Starting all sessions...")
    for session_name, session_cmd, session_cwd in all_sessions:
        subprocess.run(
            ['tmux', 'new-session', '-d', '-s', f'defl_{session_name}', session_cmd],
            cwd=session_cwd
        )
    info("Started all sessions")

    info("Sleeping for {} seconds...".format(args.sleep_sec))
    try:
        # subprocess.run(['termdown', str(args.sleep_sec)])
        # subprocess.run(['sleep', str(args.sleep_sec)])
        for i in range(args.sleep_sec, 0, -1):
            if i % 10 == 0:
                info(f'Remaining {i} seconds...')
            sleep(1)
    except KeyboardInterrupt:
        print()
        warning("Keyboard interrupt detected, killing sessions...")
        pass

    info("Killing all sessions...")
    subprocess.run(['tmux', 'kill-server'])
    info("Killed all sessions.")