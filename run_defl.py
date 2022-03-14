import argparse
import json
import logging
import os
import shutil
import subprocess
import typing
from logging import info, warning
from time import sleep

PYTHON_PATH = os.path.abspath(shutil.which('python3'))
NODE_PATH = os.path.abspath('./benchmark/node')

ClientConfig = typing.TypedDict('NodeConfig', {
    'attack': str,
    'gst': int,
    'name': str,
    'obsido_port': int,
    'host': str,
    'init_model_path': str,
})


def gen_client_cmd(python_path: str, client_config: ClientConfig):
    return '{} client.py {} --attack {} --gst {} --obsido_port {} --init_model_path {} 2> logs/{}.log'.format(
        python_path,
        client_config['host'],
        client_config['attack'],
        client_config['gst'],
        client_config['obsido_port'],
        client_config['init_model_path'],
        client_config['name']
    )


def gen_server_cmd(rust_node_path: str, id: int, client_config: ClientConfig):
    return (
        f"{rust_node_path} -vv run "
        f"--obsido {client_config['obsido_port']} "
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
    client_config: typing.List[ClientConfig] = conf["client_config"]

    node_params_json_path = os.path.abspath(conf["node_params_path"])
    init_model_path = os.path.abspath(conf["init_model_path"])

    num_nodes = len(client_config)

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

    for id in range(num_nodes):
        client_config[id]['name'] = "client-" + str(id)
        client_config[id]['obsido_port'] = obsido_base_port + id
        client_config[id]['host'] = committee_front[id]
        client_config[id]['init_model_path'] = init_model_path

    print('  ', "Client configs:")
    for client in client_config:
        print('    ', json.dumps(client))

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

    client_sessions = [
        (conf['name'], gen_client_cmd(PYTHON_PATH, conf), './benchmark')
        for conf in client_config
    ]

    server_sessions = [
        (f'node-{id}', gen_server_cmd(NODE_PATH, id, conf), './benchmark')
        for id, conf in enumerate(client_config)
    ]

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
