#!/bin/zsh
SLEEP_SEC=60
protoc -I=proto/src/ --python_out=benchmark/proto/ --mypy_out=benchmark/proto/ defl.proto
if [ $? -ne 0 ]; then
    echo "Failed to compile proto files"
    exit 1
fi
cargo build --release -j8
if [ $? -ne 0 ]; then
    echo "Failed to build rust files"
    exit 1
fi
#/usr/libexec/ApplicationFirewall/socketfilterfw --add $HOME/Gits/hotstuff/target/release/node

for i in {0..3}
do
    echo "Removing .db-$i";
    rm -rf "benchmark/.db-$i";
done

cd benchmark

./gen_config.py
if [ $? -ne 0 ]; then
    echo "Failed to generate config files"
    exit 1
fi

tmux new -d -s client-0 "./fl_client.py 127.0.0.1:9004 --gst 2000 --timeout 1000 2> logs/client-0.log"
tmux new -d -s client-1 "./fl_client.py 127.0.0.1:9005 --gst 2000 --timeout 1000 2> logs/client-1.log"
tmux new -d -s client-2 "./fl_client.py 127.0.0.1:9006 --gst 2000 --timeout 1000 2> logs/client-2.log"
tmux new -d -s client-3 "./fl_client.py 127.0.0.1:9007 --gst 2000 --timeout 1000 2> logs/client-3.log"
tmux new -d -s node-0 "./node -vv run --keys .node-0.json --committee .committee.json --store .db-0 --parameters .parameters.json 2> logs/node-0.log"
tmux new -d -s node-1 "./node -vv run --keys .node-1.json --committee .committee.json --store .db-1 --parameters .parameters.json 2> logs/node-1.log"
tmux new -d -s node-2 "./node -vv run --keys .node-2.json --committee .committee.json --store .db-2 --parameters .parameters.json 2> logs/node-2.log"
tmux new -d -s node-3 "./node -vv run --keys .node-3.json --committee .committee.json --store .db-3 --parameters .parameters.json 2> logs/node-3.log"

termdown ${SLEEP_SEC} --no-figlet
# echo "Sleeping for $SLEEP_SEC seconds"

if [ $? -ne 0 ]; then
    tmux kill-server
    exit 1
fi

tmux kill-server
