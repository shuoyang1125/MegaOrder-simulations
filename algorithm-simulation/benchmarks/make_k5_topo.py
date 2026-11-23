#! /usr/bin/env python

# Materialize the K5 synthetic topology (the paper's motivating example and
# test_r2r.py's Part B acceptance demo) as the standard on-disk artifacts the
# mega / exact / tse benchmark pipeline consumes, so K5 runs through the
# exact same scripts as the real WAN topologies:
#
#   topologies/site_topologies/K5.graphml
#       5-node complete directed graph. Problem._read_graph_graphml(top=False)
#       forces every link capacity to 1000.0, matching the K5 demo.
#   topologies/server2site-{size}/K5.graphml_server2site.pkl
#       ref_table: one -1 gateway per site + size servers per site
#       (length 5 + 5*size), same layout as the real topologies.
#   traffic-matrices/site-traffic-matrices/uniform/
#       K5.graphml_uniform_{100..109}_1.0_1150.0_traffic-matrix.pkl
#       Ten reproducible site TMs generated like UniformTrafficMatrix:
#       every off-diagonal demand is sampled independently from U(0, 1150),
#       stored as float32, and the diagonal is set to zero.
#
# Run from benchmarks/:
#   python make_k5_topo.py                # server_per_site = 10
#   python make_k5_topo.py --server 5

import argparse
import os
import pickle
import sys

sys.path.append('..')

import networkx as nx
import numpy as np

from lib.config import TOPOLOGIES_DIR, TM_DIR

K5_SITES = 5
K5_MAX_DEMAND = 1150.0
K5_TARGET_SEEDS = tuple(range(100, 110))


def k5_targets(seed):
    """Generate a standard uniform site TM, matching UniformTrafficMatrix."""
    rs = np.random.RandomState(seed)
    t = (rs.rand(K5_SITES, K5_SITES) * K5_MAX_DEMAND).astype(
        np.float32)
    np.fill_diagonal(t, 0.0)
    return t


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', type=int, default=10,
                        help='servers per site (default 10)')
    args = parser.parse_args()
    size = args.server

    # ---- site topology: complete directed graph -------------------------
    G = nx.DiGraph()
    G.add_nodes_from(range(K5_SITES))
    for a in range(K5_SITES):
        for b in range(K5_SITES):
            if a != b:
                G.add_edge(a, b, capacity=1000.0)
    topo_fname = os.path.join(TOPOLOGIES_DIR, 'site_topologies', 'K5.graphml')
    nx.write_graphml(G, topo_fname)
    print('wrote {}'.format(topo_fname))

    # ---- server2site table: 5 gateways (-1) + 5*size servers ------------
    ref = []
    for s in range(K5_SITES):
        ref.append(-1)
        ref.extend([s] * size)
    ref = np.asarray(ref)
    ref_fname = os.path.join(
        TOPOLOGIES_DIR, 'server2site-{}'.format(size),
        'K5.graphml_server2site.pkl')
    with open(ref_fname, 'wb') as w:
        pickle.dump(ref, w, protocol=4)
    print('wrote {} (len {}, servers {})'.format(
        ref_fname, len(ref), (ref != -1).sum()))

    # ---- ten standard uniform site TMs, seeds 100..109 -------------------
    for target_seed in K5_TARGET_SEEDS:
        tm = k5_targets(target_seed)
        tm_fname = os.path.join(
            TM_DIR, 'site-traffic-matrices', 'uniform',
            'K5.graphml_uniform_{}_1.0_{}_traffic-matrix.pkl'.format(
                target_seed, K5_MAX_DEMAND))
        tmp = tm_fname + '.tmp{}'.format(os.getpid())
        with open(tmp, 'wb') as w:
            pickle.dump(tm, w, protocol=4)
        os.rename(tmp, tm_fname)
        print('wrote {} (total demand {:.1f})'.format(
            tm_fname, tm.sum()))

    # ---- sanity: the round trip must be the identity node mapping -------
    from lib.problem import Problem
    G2 = Problem._read_graph_graphml(topo_fname, False)
    assert len(G2) == K5_SITES
    for u, v in G2.edges():
        assert G2[u][v]['capacity'] == 1000.0
    # node label order after convert_node_labels_to_integers must be the
    # file's document order, so TM rows/cols line up with site ids 0..4
    assert list(G2.nodes) == list(range(K5_SITES)), \
        'node relabeling is not the identity: {}'.format(list(G2.nodes))
    assert all(G2.has_edge(a, b)
               for a in range(K5_SITES) for b in range(K5_SITES)
               if a != b), 'not a complete directed graph'
    print('verified: identity node mapping, complete digraph, caps 1000')


if __name__ == '__main__':
    main()
