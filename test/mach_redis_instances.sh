#!/usr/bin/env bash
docker run -d --name redis-cluster-a --net=host orca.quixey.com/redis-cluster-a
docker run -d --name redis-cluster-b --net=host orca.quixey.com/redis-cluster-b
docker run -d --name redis-cluster-c --net=host orca.quixey.com/redis-cluster-c
docker run -d --name redis-cluster-d --net=host orca.quixey.com/redis-cluster-d
