#!/usr/bin/env bash

IP=$(docker-machine ip default || boot2docker ip || /sbin/ifconfig docker0 | grep 'inet addr:' | cut -d: -f2 | awk '{ print $1}' )

docker run -d -e "HOST_IP=${IP}" --name redis-cluster-a --net=host orca.quixey.com/redis-cluster-a
docker run -d -e "HOST_IP=${IP}" --name redis-cluster-b --net=host orca.quixey.com/redis-cluster-b
docker run -d -e "HOST_IP=${IP}" --name redis-cluster-c --net=host orca.quixey.com/redis-cluster-c
docker run -d -e "HOST_IP=${IP}" --name redis-cluster-d --net=host orca.quixey.com/redis-cluster-d
