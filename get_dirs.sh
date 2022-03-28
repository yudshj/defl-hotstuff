#!/bin/zsh
mkdir /mnt/defl-models/$1
mkdir /mnt/defl-logs/$1

ln -sf /mnt/defl-models/$1 /root/defl-hotstuff/benchmark/models
ln -sf /mnt/defl-logs/$1 /root/defl-hotstuff/benchmark/logs
