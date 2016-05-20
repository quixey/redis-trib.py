quixey/redis-trib.py
====================

Pythonic redis cluster tools.

This fork fixes issues found in the orrininal HunanTV v0.4.0, and 
increments versioning. 

To install locally:

    sudo pip install -e git+ssh://git@github.com:quixey/redis-trib.py.git@0.5.2#egg=redis-trib.py
    
Or, for your requirements.txt:

    -e git+ssh://git@github.com:quixey/redis-trib.py.git@0.5.2#egg=redis-trib.py

Quick Start

    # to start a new cluster with one redis instance
    ./redis_cluster.py -r 0 -L 192.168.99.100 -l 6380 
    
    # to add a set of new instances to an existing cluster
    ./redis_cluster.py -r 1 -L 192.168.99.100 -l 6380 6381 -f 192.168.99.100:6382 192.168.99.100:6383
    
    # to reset all nodes in a cluster back to individual zero-states
    ./redis_cluster.py -c -f 192.168.99.100:6380 192.168.99.100:6381 

Usage Nodes

<ul>
<li> All redis nodes must be configured as cluster nodes in their individual redis.conf file. 
<li> '-n'/'--new-nodes' argument is always required.
<li> -n requires a valid IP address or hostname.
<li> redis_cluster.py detects if any instances are already in a cluster, and will automatically add any non-joined nodes to the existing cluster.
<li> For -r/-m, If there are no nodes that are not attached to a cluster (as a slave or a master), then the script will exit. 
<li> If any two nodes are found to not be in the same cluster, then the script will exit before making changes.
<li> If -r/-m is 0, redis_cluster.py will attempt to divine and maintain the existing replication factor (in the case of adding new nodes to an existing cluster), or create a cluster with no slaves (if there is no existing cluster).
<li> If -c is used, redis_cluster.py will traverse and zero the entire node tree of every instance provided by detecting all masters in the cluster and then, for each master, zero every attached slave, then the master itself.
</ul>
