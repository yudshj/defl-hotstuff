import argparse
import copy
import json
import logging
import os
import shutil
import subprocess
import typing
import uuid
from logging import info, warning
from time import sleep

from benchmark.defl.types import *

PYTHON_PATH = os.path.abspath(shutil.which('python3'))
NODE_PATH = os.path.abspath('./benchmark/node')


def gen_client_cmd(python_path: str, client_name: str, client_config_path: str):
    return '{} client.py {} 2> logs/{}.log ; bash'.format(
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

    if os.path.exists('benchmark/node'):
        info("Found node binary in benchmark/node")
    else:
        info("Creating softlink to node binary...")
        p = subprocess.run(
            ['ln', '-s', '../target/release/node', 'benchmark/node'],
            check=True
        )
        info("Created softlink to node binary")

    info("Generating configs for server nodes...")
    p = subprocess.run(
        [PYTHON_PATH, "gen_config.py", "--nodes", str(num_nodes), "--base_port", str(committee_base_port),
         "--node_params_json_path", node_params_json_path],
        capture_output=True,
        cwd='./benchmark',
        check=True
    )
    info("Generated configs for server nodes")

    committee_front = json.loads(p.stdout)

    for id, cur_client_config in enumerate(client_config_list):
        assert ('attack' in cur_client_config)
        assert ('batch_size' in cur_client_config)
        assert ('data_config' in cur_client_config)
        assert ('local_train_steps' in cur_client_config)

        data_config = cur_client_config['data_config']
        if data_config['x_train']:
            data_config['x_train'] = os.path.abspath(data_config['x_train'])
        if data_config['y_train']:
            data_config['y_train'] = os.path.abspath(data_config['y_train'])
        if data_config['x_test']:
            data_config['x_test'] = os.path.abspath(data_config['x_test'])
        if data_config['y_test']:
            data_config['y_test'] = os.path.abspath(data_config['y_test'])
        if data_config['x_val']:
            data_config['x_val'] = os.path.abspath(data_config['x_val'])
        if data_config['y_val']:
            data_config['y_val'] = os.path.abspath(data_config['y_val'])

        if 'task' not in cur_client_config:
            cur_client_config['task'] = conf['task']

        if 'client_name' not in cur_client_config:
            cur_client_config['client_name'] = "client-" + str(id)
        # cur_client_config['client_name'] += '-' + str(uuid.uuid4())[:8]

        if 'server_name' not in cur_client_config:
            cur_client_config['server_name'] = "node-" + str(id)
        # cur_client_config['server_name'] += '-' + str(uuid.uuid4())[:8]

        if 'obsido_port' not in cur_client_config:
            cur_client_config['obsido_port'] = obsido_base_port + id

        if 'host' not in cur_client_config:
            cur_client_config['host'] = committee_front[id]

        if 'init_model_path' not in cur_client_config:
            cur_client_config['init_model_path'] = init_model_path

        if 'fetch' not in cur_client_config:
            cur_client_config['fetch'] = 20_000

        if 'gst' not in cur_client_config:
            cur_client_config['gst'] = 25_000

    info("Compiling protobuf code...")
    p = subprocess.run(
        ['protoc', '-I=proto/src/', '--python_out=benchmark/proto/', '--mypy_out=benchmark/proto/', 'defl.proto'],
        capture_output=False,
        check=True
    )
    info("Compiled protobuf code")

    info("Compiling rust node...")
    subprocess.run(['cargo', 'build', '--release', '-j8'], capture_output=False, check=True)
    info("Compiled rust node")

    info("Cleaning up old databases...")
    subprocess.run(['fd', '-HI', '^.db-[0-9]+$', 'benchmark', '-x', 'rm', '-rf', '{}'], capture_output=False,
                       check=True)
    info("Cleaned up old databases")

    client_sessions = []
    server_sessions = []

    db_to_remove = []

    info("Generating configs for client nodes...")
    for id, client_config in enumerate(client_config_list):
        file_name = '.{}.json'.format(client_config['client_name'])
        path = os.path.join('benchmark', file_name)
        path = os.path.abspath(path)
        with open(path, 'w') as f:
            json.dump(client_config, f, indent=4, sort_keys=True)

        client_sessions.append((
            client_config['client_name'],
            gen_client_cmd(PYTHON_PATH, client_config['client_name'], path),
            './benchmark',
            client_config['env']))

        server_sessions.append((
            client_config['server_name'],
            gen_server_cmd(NODE_PATH, id, client_config['obsido_port']),
            './benchmark',
            client_config['env']))
        
        db_to_remove.append(f".db-{id}")
    
    info("Removing db files...")
    for db_file in db_to_remove:
        subprocess.run(['rm', '-rf', db_file], cwd='./benchmark')
    info("Removed db files.")

    all_sessions = client_sessions + server_sessions

    print("  Session configs: (name, cmd, cwd)")
    for item in all_sessions:
        print('    ', item)

    info("Starting all sessions...")
    for session_name, session_cmd, session_cwd, additional_envs in all_sessions:
        tmp = []
        for k, v in additional_envs.items():
            tmp.append('-e')
            tmp.append('{}={}'.format(k, v))
        subprocess.run(
            ['tmux', 'new-session', *tmp, '-d', '-s', session_name, session_cmd],
            cwd=session_cwd,
        )
    info("Started all sessions")

    info("Sleeping for {} seconds...".format(args.sleep_sec))
    try:
        # subprocess.run(['termdown', str(args.sleep_sec)])
        # subprocess.run(['sleep', str(args.sleep_sec)])
        if args.sleep_sec > 0:
            for i in range(args.sleep_sec, 0, -10):
                info(f'Remaining {i} seconds...')
                sleep(10)
        else:
            while True:
                info('Sleeping for 10 seconds...')
                sleep(10)
    except KeyboardInterrupt:
        print()
        warning("Keyboard interrupt detected, killing sessions...")
        pass

    info("Killing all sessions...")
    for session_name, _, session_cwd, _ in all_sessions:
        subprocess.run(
            ['tmux', 'kill-session', '-t', session_name],
            cwd=session_cwd
        )
    info("Killed all sessions.")
