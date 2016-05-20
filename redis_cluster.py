#!/usr/bin/env python
import argparse
import logging
import os
import socket

from hiredis import ProtocolError, ReplyError
from redis import StrictRedis

import redistrib.command
from redistrib.clusternode import Talker


NUM_SLOTS = 16384


def _make_parts(n):
    p = NUM_SLOTS/n
    remain = NUM_SLOTS-(p*n)

    partitions = []
    i = 0
    count = 0
    s = remain
    while count < n:
        q = i
        r = i + p - 1
        if s:
            r += 1
            s -= 1
        partitions.append((q, r))
        i = (r + 1)
        count += 1
    return partitions


def _map_cluster(node_host, node_port):
    cluster = {}
    slaves = []
    node_port = int(node_port)
    nodes, master = redistrib.command.list_nodes(node_host, node_port)
    for node in nodes:
        if 'master' in node.role_in_cluster:
            if node.node_id not in cluster:
                cluster[node.node_id] = {'self': node, 'slaves': []}
        else:
            slaves.append(node)

    for slave in slaves:
        cluster[slave.master_id]['slaves'].append(slave)

    if slaves:
        cluster_replication_factor = int(len(cluster) / len(slaves))
    else:
        cluster_replication_factor = 0
    return cluster, slaves, cluster_replication_factor


def create(new_nodes, replicas=0):
    """
    Function to create a new cluster ONLY from nodes not already initialized. NOTE: this function replicates
    redis-trib.rb 'create' command, EXCEPT that it can take less than 3 nodes for initialization.
    """

    logging.debug("creating new cluster using nodes {} with RF {}".format(new_nodes, replicas))
    node_list = []
    for n in new_nodes:
        logging.debug("new node: {}".format(n))
        node_list.append((n['host'], int(n['port'])))

    master_count = len(node_list)
    if replicas:
        master_count /= (replicas + 1)
        if master_count < 1:
            logging.error("Not enough fresh nodes to accommodate replication factor of {}".format(replicas))
            return

    master_count = int(master_count)
    master_list = node_list[:master_count]
    slave_list = node_list[master_count:]

    if len(master_list) > 1:
        logging.info("Creating cluster with the following nodes as masters: {}".format(master_list))
        redistrib.command.start_cluster_on_multi(master_list)
    else:
        host = master_list[0][0]
        port = master_list[0][1]
        logging.info("Creating single master: {} {}".format(host, port))
        m = StrictRedis(host=host, port=port)
        s = ""
        for i in xrange(1, NUM_SLOTS):
            s += "{} ".format(i)
        cmd = 'CLUSTER ADDSLOTS {}'.format(s)
        logging.debug("Sending following command: {}".format(cmd))
        m.execute_command(cmd)

    if replicas:
        logging.info("Adding following nodes as slaves evenly across masters: {}".format(slave_list))
        for i, s in enumerate(slave_list):
            m = master_list[i % master_count]
            redistrib.command.replicate(m[0], m[1], s[0], s[1])
    return True


def expand_cluster(master_host, master_port, new_nodes, num_new_masters=None):
    """
    function to add a set of nodes to an existing cluster. NOTE: this function presumes that the list of new nodes are
     NOT present on existing instances. Future versions MAY try to re-balance slaves among IP Addresses.
    :param master_host: machine IP (string) of any healthy cluster node
    :param master_port: machine Port of the master_host
    :param new_nodes: list of {"host": "[ip_addr]", "port": "[port_num]"} objects
    :param num_new_masters: if you want a specific ammount to be new masters, set this parameter Default: function will
        attempt to auto-detect existing replication factor, and populate, accordingly.
    :return:
    """

    logging.debug('master_instance: {}:{}'.format(master_host, master_port))
    cluster, slaves, cluster_replication_factor = _map_cluster(master_host, master_port)
    logging.debug("cluster: {}".format(cluster.items()))
    logging.debug("slaves: {}".format(slaves))

    if not cluster:
        logging.error("Empty Cluster for Host {} {}".format(master_host, master_port))
        return

    num_sets_to_add = int(len(new_nodes)/(cluster_replication_factor + 1))
    if not num_sets_to_add:
        logging.error("Cluster has a replication factor of {}. Insufficient number of new nodes given.")
        return

    new_replication_factor = cluster_replication_factor
    if num_new_masters:
        if num_new_masters < len(new_nodes):
            logging.error("Insufficient number of new nodes ({}) to accommodate number of "
                          "masters requested ({})".format(len(new_nodes), num_new_masters))
            return
        num_sets_to_add = min(num_sets_to_add, num_new_masters)
        new_replication_factor = min(cluster_replication_factor, (len(new_nodes)/(num_new_masters + 1)))

    logging.debug("crf: {}".format(new_replication_factor))

    master_list = None

    logging.info("Adding nodes {} to Cluster Instance {}:{}".format(new_nodes, master_host, master_port))

    while num_sets_to_add:
        if not master_list:
            master_list = cluster.values()
        logging.debug("master list: {}".format(master_list))
        for master in master_list:
            if 'self' in master:
                logging.debug("self: {} {}".format(master['self'].host,master['self'].port ))
        num_sets_to_add -= 1
        new_master_node = new_nodes.pop()
        master = master_list.pop()
        existing_master_node = master['self']
        existing_slave_nodes = master['slaves']
        logging.info('Adding new node {} to cluster as a master.'.format(new_master_node))
        logging.debug('new_master_node: {}:{} being added to existing_master_node: {}:{}'.format(existing_master_node.host, existing_master_node.port, new_master_node['host'], new_master_node['port']))

        redistrib.command.join_cluster(existing_master_node.host, existing_master_node.port,
                                       new_master_node['host'], int(new_master_node['port']))
        logging.debug('master node joined to cluster!')

        for j in range(new_replication_factor):
            new_slave_node = new_nodes.pop()
            existing_slave_node = existing_slave_nodes.pop()
            logging.info('Adding new node {} as slave to master {}'.format(new_slave_node['port'],
                                                                           existing_master_node.node_id))
            redistrib.command.replicate(existing_master_node.host, existing_master_node.port, new_slave_node['host'],
                                        int(new_slave_node['port']))
            if existing_slave_node:
                logging.info("Switching existing slave node {} to new master {}:{}".format(existing_slave_node.port,
                                                                                           new_master_node['host'],
                                                                                           new_master_node['port']))

                redistrib.command.replicate(new_master_node['host'], int(new_master_node['port']),
                                            existing_slave_node.host, existing_slave_node.port)
            else:
                logging.warn("Slave node underrun for replication {} of factor {}".format(j+1, new_replication_factor))

    while new_nodes:
        logging.debug("{} new nodes left over, so adding them as slaves.".format(len(new_nodes)))
        cluster, _, new_replication_factor = _map_cluster(master_host, master_port)
        underweight = []
        for master in cluster.values():
            if len(master['slaves']) < new_replication_factor:
                underweight.append(master)

        if underweight:
            while underweight and new_nodes:
                master = underweight.pop()
                existing_master_node = master['self']
                new_slave_node = new_nodes.pop()
                logging.info("Adding new node {}:{} as slave to underweight master {}".format(
                    new_slave_node['host'], new_slave_node['port'], existing_master_node.node_id
                ))
                redistrib.command.replicate(existing_master_node.host, existing_master_node.port,
                                            new_slave_node['host'], int(new_slave_node['port']))
        else:
            master_nodes = cluster.values()
            while master_nodes and new_nodes:
                new_master_node = new_nodes.pop()
                master = master_nodes.pop()
                existing_master_node = master['self']
                logging.info("Adding new node {}:{} as slave to master {}".format(
                    new_slave_node['host'], new_slave_node['port'], existing_master_node.node_id
                ))
                redistrib.command.replicate(existing_master_node.host, existing_master_node.port,
                                            new_master_node['host'], int(new_master_node['port']))


def evaluate_cluster(foreign_nodes, local_nodes, replication_factor=None, new_masters=None):
    """
    For algorythmic reasons, this method ensures we only add nodes from our own instance.

    If any of the local nodes are eligible to be joined to a stable cluster, and if there is a single stable cluster,
    this method calls 'expand cluster'.

    :param foreign_nodes: list of ojects representing redis nodes expected to exist in the same cluster, with each item as {'ip': 'N.N.N.N', 'port':N}
    :param replication_factor:
    :param new_masters:
    :return:
    """
    new_nodes = {}
    cluster_nodes = []

    logging.debug("foreign nodes: {}".format(foreign_nodes))
    logging.debug("local nodes: {}".format(local_nodes))

    logging.debug("finding all in foreign_nodes that are not joined to a cluster already")
    for node in foreign_nodes + local_nodes:
        logging.debug("checking cluster status of node")
        with Talker(node['host'], int(node['port'])) as t:
            try:
                redistrib.command._ensure_cluster_status_unset(t)
                if node['host'] not in new_nodes:
                    new_nodes[node['host']] = []
                new_nodes[node['host']].append(int(node['port']))
            except ProtocolError:
                cluster_nodes.append(node)
    new_nodes_list = []
    for host, ports in new_nodes.iteritems():
        for port in ports:
            new_nodes_list.append({'host': host, 'port': port})

    if new_nodes_list:
        logging.info("new nodes found: {}".format(new_nodes_list))

    cluster = {}
    if cluster_nodes:
        _cluster_nodes = []
        for node in cluster_nodes:
            logging.debug("cluster node: {}".format(node))
            if not cluster:
                cluster, _, _ = _map_cluster(node['host'], node['port'])

            _cluster, _, _ = _map_cluster(node['host'], node['port'])
            for master in _cluster:
                if master not in _cluster_nodes:
                    _cluster_nodes.append(master)
                if master not in cluster:
                    logging.error("Disjoint clusters! Exiting.")
                    #exit(1)

        logging.info('number of nodes in cluster: {}'.format(len(cluster_nodes)))
        logging.info('number of master nodes in existing cluster: {}'.format(len(_cluster_nodes)))
    if not new_nodes:
        logging.info("No new nodes found. Cluster is Healthy!")
        logging.debug("cluster map: {}".format(cluster))
        exit(0)

    # there are new nodes, and any existing cluster is healthy...
    if not cluster_nodes:
        if new_masters > 0:
            replication_factor = int(len(foreign_nodes)/new_masters)
        elif new_masters == 0:
            replication_factor = 0
        create(new_nodes_list, replication_factor)
    else:
        if replication_factor:
            new_masters = int(len(foreign_nodes)*(1/(replication_factor + 1)))
        master = cluster_nodes.pop()
        expand_cluster(master['host'], master['port'], new_nodes_list, new_masters)


def reset_node(node):
    logging.info("Clearing {} node {}:{}".format(node.role_in_cluster, node.host, node.port))
    with Talker(node.host, node.port) as t:
        try:
            t.talk('CLUSTER', 'RESET')
        except ReplyError:
            logging.warn("Keys exist. Attempting to remove keys.")
        t.talk('FLUSHALL')


def remove_cluster(foreign_nodes):
    for node in foreign_nodes:
        logging.info('Clearing cluster from node {}:{}'.format(node['host'], node['port']))
        cluster, _, _ = _map_cluster(node['host'], node['port'])
        for master in cluster.values():
            for slave in master['slaves']:
                try:
                    reset_node(slave)
                except socket.error:
                    logging.warn("Cannot reach node: {}".format(slave))
                    pass
            try:
                reset_node(master['self'])
            except socket.error:
                logging.warn("Cannot reach node: {}".format(master))
                pass


def _decode_hosts(host_list):
    if not host_list:
        return []
    logging.debug("decoding list: {}".format(host_list))
    hosts = []
    for host in host_list:
        try:
            h = host.split(":")
            h_ip = socket.gethostbyname(h[0])
            hosts.append({'host': h_ip, 'port': int(h[1])})
        except IndexError:
            logging.error("invalid host: {}".format(host))
    if not hosts:
        logging.error("No valid hosts provided.")
        exit(0)
    return hosts


# from http://stackoverflow.com/questions/14117415
def _check_negative(value):
    ivalue = int(value)
    if ivalue < 0:
        raise argparse.ArgumentTypeError("%s is an invalid positive int value" % value)
    return ivalue


def main():
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(name)-12s %(levelname)-8s - %(funcName)20s :: %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    help_str = """Utility to take redis instances on a local instance, and join it to a remote cluster.

    This utility is idempotent. Tt will not make adjustments to it's local nodes if they already exist in a cluster.
    Remote cluster discovery is left to the engineer.

    It is not necessary to claim the local nodes in the '--foreign-nodes' list, but it does not harm the utility to do so.

    This utility will check for total cluster integrity, weather or not the local instances are already joined in a
    cluster, and ensure that all instances provided have identical cluster maps (that is, that they exist in the same
    cluster) by ensuring that each node claims the same set of master nodes. We rely on Redis Cluster Gossip to ensure
    concurrent maping acuracy, but it is still possible for disjoint graphs between nodes due to the dynamic cluster
    topology that this utility can create.

    If the set of master nodes known by any one node has an incongruence against the set of master nodes known by any
    other node, then this utility will error out, and log same.

    It is adviseable, therefore, that all possible external cluster redis nodes are (by ip/port) given as arguments to
    this utility, to excellerate detection of a disjoint cluster graph.
    """
    parser = argparse.ArgumentParser(help_str)
    parser.add_argument('-f', '--foreign-nodes',
                        type=str,
                        nargs="+",
                        action='store',
                        help="json list of foreign cluster nodes, of form ['<host_ip>:<port_number>']",
                        )
    parser.add_argument('-l', '--local-nodes',
                        type=str,
                        nargs="+",
                        action='store',
                        help="json list of ports of local cluster nodes, of form [<port_number>,...]",
                        default=['6380', '6381'])
    parser.add_argument('-L', '--localhost',
                        type=str,
                        action='store',
                        default='127.0.0.1')
    parser.add_argument('-g', '--log-dir',
                        type=str,
                        default="/var/log/redis-trib",
                        help="directory path to place logfile (default '/var/log/redis-trib'")
    parser.add_argument('-d', '--debug',
                        help="DEBUG loglevel. Default: INFO",
                        action='store_true',
                        default=False)

    mx = parser.add_mutually_exclusive_group(required=True)
    mx.add_argument('-r', '--replication-factor',
                    action='store',
                    help="required number of slaves per master; default=1")
    mx.add_argument('-m', '--new-masters',
                    action='store',
                    help="required number of new masters; default=0")
    mx.add_argument('-c', '--clear-cluster',
                    action='store_true',
                    help="clear any cluster attached to any nodes listed")

    args = parser.parse_args()

    local_node_list = [args.localhost+':'+str(p) for p in args.local_nodes]
    local_nodes = _decode_hosts(local_node_list)

    if args.debug:
        logger.setLevel(logging.DEBUG)

    log_dir = args.log_dir+"redis-trib.py.log"
    if os.path.exists(log_dir):
        f_handler = logging.FileHandler(log_dir)
        f_handler.setFormatter(formatter)
        logger.addHandler(f_handler)

    if args.replication_factor:
        args.replication_factor = _check_negative(args.replication_factor)

    if args.new_masters:
        args.new_masters = _check_negative(args.new_masters)

    if args.clear_cluster:
        hosts = _decode_hosts(args.foreign_nodes)
        remove_cluster(hosts)
    else:
        foreign_nodes = _decode_hosts(args.foreign_nodes)
        evaluate_cluster(foreign_nodes, local_nodes, args.replication_factor, args.new_masters)


if __name__ == "__main__":
    main()
