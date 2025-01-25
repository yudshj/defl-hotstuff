# DegaFL

This repository contains code for the paper [**DegaFL: Decentralized Gradient Aggregation for Cross-Silo Federated Learning**](https://ieeexplore.ieee.org/document/10756624).

If you find this code useful, please cite our work:

```latex
@article{DBLP:journals/tpds/HanHJHM25,
  author       = {Jialiang Han and
                  Yudong Han and
                  Xiang Jing and
                  Gang Huang and
                  Yun Ma},
  title        = {DegaFL: Decentralized Gradient Aggregation for Cross-Silo Federated
                  Learning},
  journal      = {{IEEE} Trans. Parallel Distributed Syst.},
  volume       = {36},
  number       = {2},
  pages        = {212--225},
  year         = {2025}
}
```

## Workflow Overview

![Approach](https://github.com/yudshj/defl-hotstuff/blob/main/Approach.png)

First, all nodes are initialized with the same model with randomly initialized weights. Then, in each training round, each node adaptively filters out poisoning gradients and aggregates correct gradients of the last round, performs local training, commits its gradients of the current round, and waits for GST\_LT to vote for the next round. Each node coordinates gradient update and aggregation by handling transactions committed by other nodes, i.e. maintaining and synchronizing $\mathit{round\_id}$ and gradients of the current and last rounds.

## Datasets

[CIFAR-10](https://www.cs.toronto.edu/~kriz/cifar.html)

[Sentiment140](https://www.kaggle.com/datasets/kazanova/sentiment140)

## Logs

![image](https://github.com/yudshj/defl-hotstuff/assets/16971372/e90c7949-d46b-40e1-932b-00714bfbbcd9)

![image](https://github.com/yudshj/defl-hotstuff/assets/16971372/807079a2-955d-4b7b-a7ab-330af563fa97)
