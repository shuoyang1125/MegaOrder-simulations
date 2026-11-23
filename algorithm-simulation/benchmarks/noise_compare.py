#! /usr/bin/env python

# Aggregate the noise-chain TSE / mega / exact comparison (Route B) into
# noise-compare.csv, one row per method, TM2 round.
#
# Inputs (produced by the three independent scripts, run in order):
#   mega.csv   -- Run_all.py --algo mega --server S --slices 0 1
#   exact.csv  -- exact.py   --server S --problem P --slices 0 1
#   tse.csv    -- tse.py     --server S --problem P --slices 0 1
#   Mega-logs/{P}/{seedA,seedB}-{model}/{S}-per_site/{P}-{S}-ssp_solution.pkl
#
# Metrics:
#   reordered_pairs : mega = pairwise diff of the two ssp_solution.pkl
#                     (same definition as analyze_mega_reordering.py);
#                     exact = exact.csv tm_index=1 reordered_pairs;
#                     tse   = tse.csv   tm_index=1 reordered_after.
#   runtime_s       : each method's own solve time for the TM2 round
#                     (mega: LP_runtime+SSP_runtime of the TM2 row;
#                      exact: total_runtime; tse: mega TM2 + r2r_runtime).
#   satisfied_*     : carried demand of the TM2 round.
#
# Usage (from benchmarks/):
#   python noise_compare.py --problem Uninett2010.graphml --server 10

import argparse
import os
import pickle
import sys

sys.path.append('..')

from benchmark_consts import MEGA_HYPERPARAMS
from lib.config import TM_DIR
from analyze_mega_reordering import (
    load_mega_solution, load_complete_path_dict, init_fixed_path_mapping,
    map_solution_to_fixed_path_nums, count_reordered_pairs)

MEGA_DIR = 'Mega-logs'

OUT_HEADERS = [
    'problem', 'server_per_site', 'method', 'tm2_seed', 'reordered_pairs',
    'runtime_s', 'satisfied_demand', 'total_demand', 'satisfied_pct',
    'proven_optimal', 'mip_gap',
]


def read_csv_rows(fname):
    """Parse an append-mode benchmark csv (header line rewritten on every
    run): drop repeated header lines, return list of dicts keyed by the
    (constant) header."""
    header = None
    rows = []
    with open(fname) as f:
        for line in f:
            parts = [p.strip() for p in line.rstrip('\n').split(',')]
            if not parts or not parts[0]:
                continue
            if parts[0] == 'problem':
                header = parts
                continue
            if header is not None and len(parts) == len(header):
                rows.append(dict(zip(header, parts)))
    return rows


def pick(rows, **match):
    """Last row matching all key=value filters (append mode: latest run)."""
    out = None
    for r in rows:
        if all(r.get(k) == str(v) for k, v in match.items()):
            out = r
    return out


def mega_reorder_and_satisfied(problem, seeds, model, size, srv_tm):
    """Pairwise diff of mega's two ssp_solution.pkl files (the baseline's
    reordered-pair count for the TM1 -> TM2 transition), plus the TM2
    solution's carried demand (sum of tm over assigned pairs -- the same
    口径 as R2RSolver; note SSP's internal total_demand()/csv percentage
    can differ slightly from the saved solution)."""
    num_paths, edge_disjoint, dist_metric = MEGA_HYPERPARAMS
    complete = load_complete_path_dict(
        problem, num_paths, edge_disjoint, dist_metric)
    path_to_num, _ = init_fixed_path_mapping(complete)

    sols = []
    for seed in seeds:
        fname = os.path.join(
            MEGA_DIR, problem, '{}-{}'.format(seed, model),
            '{}-per_site'.format(size),
            '{}-{}-ssp_solution.pkl'.format(problem, size))
        sol = load_mega_solution(fname)
        sols.append(map_solution_to_fixed_path_nums(sol, path_to_num))
    stats = count_reordered_pairs(sols[0], sols[1])
    sat = sum(float(srv_tm[i, j]) for (i, j) in sols[1])
    return stats, sat


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--problem', type=str, default='Uninett2010.graphml')
    parser.add_argument('--server', type=int, default=10)
    parser.add_argument('--seeds', type=int, nargs=2, default=[1000, 2000])
    parser.add_argument('--model', type=str, default='generic')
    parser.add_argument('--out', type=str, default='noise-compare.csv')
    args = parser.parse_args()

    problem, size, model = args.problem, args.server, args.model
    seed1, seed2 = args.seeds

    mega_rows = read_csv_rows('mega.csv')
    exact_rows = read_csv_rows('exact.csv')
    tse_rows = read_csv_rows('tse.csv')

    mega_tm2 = pick(mega_rows, problem=problem, traffic_seed=seed2,
                    tm_model=model, server_per_site=size)
    exact_tm2 = pick(exact_rows, problem=problem, traffic_seed=seed2,
                     tm_model=model, server_per_site=size, tm_index=1)
    tse_tm2 = pick(tse_rows, problem=problem, traffic_seed=seed2,
                   server_per_site=size, tm_index=1)
    if mega_tm2 is None or exact_tm2 is None or tse_tm2 is None:
        raise SystemExit(
            'missing csv rows: mega={} exact={} tse={}'.format(
                mega_tm2 is not None, exact_tm2 is not None,
                tse_tm2 is not None))

    srv_tm_fname = os.path.join(
        TM_DIR, 'srv-traffic-matrices-{}'.format(size), model,
        '{}_{}_{}_1.0_noise_traffic-matrix.pkl'.format(
            problem, model, seed2))
    with open(srv_tm_fname, 'rb') as f:
        srv_tm = pickle.load(f)

    mega_reord, mega_sat = mega_reorder_and_satisfied(
        problem, args.seeds, model, size, srv_tm)
    mega_runtime = float(mega_tm2['LP_runtime']) + \
        float(mega_tm2['SSP_runtime'])
    total_demand = float(mega_tm2['total_demand'])

    tse_runtime = mega_runtime + float(tse_tm2['r2r_runtime'])
    tse_sat = float(tse_tm2['satisfied_demand'])
    tse_reord = int(tse_tm2['reordered_after'])

    exact_runtime = float(exact_tm2['total_runtime'])
    exact_sat = float(exact_tm2['satisfied_demand'])
    exact_reord = int(exact_tm2['reordered_pairs'])

    # cross-checks: tse starts from mega's solution, so its "before" state
    # must match the mega baseline's numbers
    checks = [
        ('tse reordered_before == mega pairwise reordered',
         int(tse_tm2['reordered_before']) == mega_reord['reordered_pairs']),
        ('tse satisfied == mega satisfied', tse_sat == mega_sat),
        ('exact total_demand == mega total_demand',
         abs(float(exact_tm2['total_demand']) - total_demand) <= 1e-6),
    ]
    for name, ok in checks:
        print('[{}] {}'.format('OK' if ok else 'MISMATCH', name))

    with open(args.out, 'w') as w:
        print(','.join(OUT_HEADERS), file=w)
        print(','.join(str(x) for x in [
            problem, size, 'mega', seed2,
            mega_reord['reordered_pairs'],
            '{:.3f}'.format(mega_runtime), mega_sat, total_demand,
            '{:.4f}'.format(100.0 * mega_sat / total_demand), '', '']), file=w)
        print(','.join(str(x) for x in [
            problem, size, 'exact', seed2,
            exact_reord, '{:.3f}'.format(exact_runtime), exact_sat,
            total_demand,
            '{:.4f}'.format(100.0 * exact_sat / total_demand),
            exact_tm2['proven_optimal'], exact_tm2['mip_gap']]), file=w)
        print(','.join(str(x) for x in [
            problem, size, 'tse', seed2,
            tse_reord, '{:.3f}'.format(tse_runtime), tse_sat,
            total_demand,
            '{:.4f}'.format(100.0 * tse_sat / total_demand), '', '']), file=w)
    print('wrote {}'.format(args.out))

    print('\nTM1/TM2 mega pairwise: common={} reordered={} (tm1-only {}, '
          'tm2-only {})'.format(
              mega_reord['common_pairs'], mega_reord['reordered_pairs'],
              mega_reord['tm1_only_pairs'], mega_reord['tm2_only_pairs']))
    print('tse: candidates={} exchanges={} new_violations={}'.format(
        tse_tm2['num_candidates'], tse_tm2['exchanges'],
        tse_tm2['num_new_violations']))


if __name__ == '__main__':
    main()
