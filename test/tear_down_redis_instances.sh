#!/usr/bin/env bash

declare -a arr=("redis-cluster-a","redis-cluster-b","redis-cluster-c","redis-cluster-d")

for c in "${arr[@]}"
do
    #clean up
    echo "Stop and remove ${CONTAINER_NAME} test container"
    docker rm -f ${CONTAINER_NAME}

    echo "Remove existing ${IMAGE} image"
    docker rmi -f ${IMAGE}
done
