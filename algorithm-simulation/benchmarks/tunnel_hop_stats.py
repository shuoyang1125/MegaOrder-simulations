#!/usr/bin/env python
"""Hop-count statistics of the pre-established tunnels for each topology.

With no positional arguments, loads the historical edge-disjoint path dicts.
Alternatively, pass one or more path-dict pickle files explicitly. Reports the
per-topology hop-count distribution (min / median / mean / max) over all
tunnels, along with the number of tunnels and site pairs.

Output: stdout table + two CSV files in this directory.
"""

import argparse
import csv
import os
import pickle
import statistics

TOPOLOGIES_DIR = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), '..',
                 'topologies'))

TOPOLOGIES = ['Uninett2010', 'Deltacom', 'UsCarrier', 'Cogentco']
NUM_PATHS = 4
EDGE_DISJOINT = True
DIST_METRIC = 'inv-cap'


def load_path_dict(topo_name):
    fname = os.path.join(
        TOPOLOGIES_DIR, 'paths', 'site-paths',
        '{}.graphml-{}-paths_edge-disjoint-{}_dist-metric-{}-dict.pkl'.format(
            topo_name, NUM_PATHS, EDGE_DISJOINT, DIST_METRIC))
    with open(fname, 'rb') as f:
        return pickle.load(f)


def load_path_file(fname):
    with open(fname, 'rb') as f:
        return pickle.load(f)


def topology_from_path(fname):
    """Extract ``K5`` from ``K5.graphml-4-paths_...-dict.pkl``."""
    return os.path.basename(fname).split('.graphml-', 1)[0]


def hop_stats(path_dict):
    hops = []
    for paths in path_dict.values():
        for path in paths:
            hops.append(len(path) - 1)
    return hops


def hop_stats_by_index(path_dict):
    """Hop counts grouped by tunnel index (1st, 2nd, ... edge-disjoint path)."""
    by_index = {}
    for paths in path_dict.values():
        for idx, path in enumerate(paths):
            by_index.setdefault(idx, []).append(len(path) - 1)
    return by_index


def fmt_stats(hops):
    return 'min={} median={:.1f} mean={:.2f} max={}'.format(
        min(hops), statistics.median(hops), statistics.mean(hops),
        max(hops))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'path_files', nargs='*',
        help='explicit path-dict pickle files; when omitted, use the '
             'historical hard-coded edge-disjoint=True topology set')
    parser.add_argument(
        '--output-prefix', default='tunnel_hop_stats',
        help='CSV basename written under benchmarks/ (default: '
             'tunnel_hop_stats)')
    args = parser.parse_args()

    if args.path_files:
        inputs = [(topology_from_path(fname), load_path_file(fname))
                  for fname in args.path_files]
    else:
        inputs = [(topo, load_path_dict(topo)) for topo in TOPOLOGIES]

    rows = []
    index_rows = []
    for topo, path_dict in inputs:
        hops = hop_stats(path_dict)
        num_pairs = len(path_dict)
        num_tunnels = len(hops)
        row = {
            'topology': topo,
            'num_site_pairs': num_pairs,
            'num_tunnels': num_tunnels,
            'tunnels_per_pair': num_tunnels / num_pairs,
            'min_hops': min(hops),
            'median_hops': statistics.median(hops),
            'mean_hops': statistics.mean(hops),
            'max_hops': max(hops),
        }
        rows.append(row)

        print('=== {} ==='.format(topo))
        print('  site pairs: {}'.format(num_pairs))
        print('  tunnels:    {} ({:.2f} per site pair)'.format(
            num_tunnels, row['tunnels_per_pair']))
        print('  hop counts (all tunnels): {}'.format(fmt_stats(hops)))

        by_index = hop_stats_by_index(path_dict)
        for idx in sorted(by_index):
            h = by_index[idx]
            index_rows.append({
                'topology': topo,
                'tunnel_index': idx + 1,
                'num_tunnels': len(h),
                'min_hops': min(h),
                'median_hops': statistics.median(h),
                'mean_hops': statistics.mean(h),
                'max_hops': max(h),
            })
            print('  hop counts (tunnel #{}): n={} {}'.format(
                idx + 1, len(h), fmt_stats(h)))
        print()

    base_dir = os.path.dirname(os.path.abspath(__file__))

    csv_fname = os.path.join(base_dir, args.output_prefix + '.csv')
    with open(csv_fname, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print('Wrote {}'.format(csv_fname))

    index_csv_fname = os.path.join(
        base_dir, args.output_prefix + '_by_index.csv')
    with open(index_csv_fname, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(index_rows[0].keys()))
        writer.writeheader()
        writer.writerows(index_rows)
    print('Wrote {}'.format(index_csv_fname))


if __name__ == '__main__':
    main()
