#!/bin/zsh
SLEEP_SEC=20
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

tmux new -d -s client-0 "./test_client.py 127.0.0.1:9004 --size 1024 --train 500 --gst 2000 --timeout 1000 2> logs/client-0.log"
tmux new -d -s client-1 "./test_client.py 127.0.0.1:9005 --size 1024 --train 500 --gst 2000 --timeout 1000 2> logs/client-1.log"
tmux new -d -s client-2 "./test_client.py 127.0.0.1:9006 --size 1024 --train 500 --gst 2000 --timeout 1000 2> logs/client-2.log"
tmux new -d -s client-3 "./test_client.py 127.0.0.1:9007 --size 1024 --train 500 --gst 2000 --timeout 1000 2> logs/client-3.log"
tmux new -d -s node-0 "./node -vv run --keys .node-0.json --committee .committee.json --store .db-0 --parameters .parameters.json 2> logs/node-0.log"
tmux new -d -s node-1 "./node -vv run --keys .node-1.json --committee .committee.json --store .db-1 --parameters .parameters.json 2> logs/node-1.log"
tmux new -d -s node-2 "./node -vv run --keys .node-2.json --committee .committee.json --store .db-2 --parameters .parameters.json 2> logs/node-2.log"
tmux new -d -s node-3 "./node -vv run --keys .node-3.json --committee .committee.json --store .db-3 --parameters .parameters.json 2> logs/node-3.log"

# termdown 10s --no-figlet
echo "Sleeping for $SLEEP_SEC seconds"

for i in {$SLEEP_SEC..0}
do
    echo $i;
    sleep 1;
done

tmux kill-server
