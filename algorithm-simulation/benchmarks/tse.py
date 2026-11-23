#! /usr/bin/env python

# TSE (Two-Stage Exchange) benchmark: Algorithm 1 of the paper.
#
# Stage 1 (mega): reuse the saved mega artifacts (site-LP + SSP
# ssp_solution.pkl) of each TM as the initial configuration f-hat.
# Stage 2 (R2R): apply the reciprocal-exchange post-processor
# (lib/algorithms/r2r_exchange.py) against the previous round's
# actually-deployed configuration b.
#
# Chain protocol (mirrors mega_order_benchmark / exact.py):
#   - TM matrices are processed in sequence per problem;
#   - TM0 has no history: its f-hat is deployed as-is (R2R no-op);
#   - TM_r>0 uses the previous TM's post-R2R deployment as b;
#   - history resets when the problem (topology) changes.
# Reusing mega artifacts pins the LP/SSP products so TSE-vs-mega
# differences are attributable to R2R alone (the site LP is degenerate;
# its F-split varies run-to-run -- the --lp-source protocol).
#
# Usage (run from benchmarks/):
#   python tse.py --server 10 --problem Uninett2010.graphml --slices 0 5

import argparse
import os
import pickle
import sys
import traceback

import numpy as np

sys.path.append('..')

import benchmark_consts
from benchmark_consts import print_, MEGA_HYPERPARAMS
from lib.algorithms.r2r_exchange import R2RSolver
from lib.config import TOPOLOGIES_DIR, TM_DIR
from lib.problem import Problem

TSE_DIR = 'TSE-logs'
SOURCE_DIR = 'Mega-logs'

HEADERS = [
    'problem', 'tm_index', 'traffic_seed', 'server_per_site', 'algo',
    'epsilon', 'loss_weight', 'obj_val',
    'num_common_pairs', 'reordered_before', 'reordered_after',
    'reorder_reduction', 'num_reordered_groups', 'num_candidates',
    'num_dz_positive', 'exchanges',
    'satisfied_demand', 'satisfied_demand_before', 'satisfied_demand_pct',
    'max_link_util', 'num_inherited_violations', 'num_new_violations',
    'r2r_runtime',
]
PLACEHOLDER = ','.join('{}' for _ in HEADERS)


def load_mega_solution(problem_name, seed, model, size, source_dir):
    fname = os.path.join(
        source_dir, problem_name, '{}-{}'.format(seed, model),
        '{}-per_site'.format(size),
        '{}-{}-ssp_solution.pkl'.format(problem_name, size))
    with open(fname, 'rb') as f:
        return pickle.load(f)


def load_srv_tm(problem_name, model, seed, scale_factor, size, param):
    tm_fname = os.path.join(
        TM_DIR, 'srv-traffic-matrices-{}'.format(size), model,
        '{}_{}_{}_{}_{}_traffic-matrix.pkl'.format(
            problem_name, model, seed, scale_factor, param))
    with open(tm_fname, 'rb') as f:
        return pickle.load(f)


def to_tunnel_assign(ssp_out, path_to_num=None, num_endpoints=None):
    """Convert mega paths and optionally encode them in the same pass."""
    assign = {}
    encoded = None
    if path_to_num is not None and num_endpoints is not None:
        encoded = np.full(num_endpoints * num_endpoints, -1,
                          dtype=np.int32)
    for (i, j), path in ssp_out.items():
        tunnel = tuple(path[1:-1])
        assign[(i, j)] = tunnel
        if encoded is not None:
            tunnel_id = path_to_num.get(tunnel)
            if tunnel_id is None:
                # Let R2RSolver's general encoder handle unusual artifacts
                # that are absent from the canonical tunnel dictionary.
                encoded = None
            else:
                encoded[i * num_endpoints + j] = tunnel_id
    return assign, encoded


def to_ssp_out(assign):
    """{(i,j): (site,...)} -> {(i,j): [i, site..., j]} (mega format)."""
    return {(i, j): [i] + list(p) + [j] for (i, j), p in assign.items()}


def tse_chain(problems, args):
    size = args.server
    num_paths, edge_disjoint, dist_metric = MEGA_HYPERPARAMS
    epsilon, loss_weight = args.epsilon, args.loss_weight

    deploy_b = {}          # previous round's actually-deployed config
    deploy_encoded = None  # compact form reused by the next TM
    prev_problem = None
    tm_counter = {}

    with open('tse.csv', 'a') as results:
        print_(','.join(HEADERS), file=results)
        for problem_name, _topo, tm_fname in problems:
            vals = os.path.basename(tm_fname)[:-4].split('_')
            model = vals[1]
            traffic_seed = int(vals[2])
            scale_factor = float(vals[3])
            param = vals[4]

            if prev_problem is not None and prev_problem != problem_name:
                print('Problem changed, resetting history')
                deploy_b = {}
                deploy_encoded = None
            prev_problem = problem_name

            tm_index = tm_counter.get(problem_name, 0)
            tm_counter[problem_name] = tm_index + 1
            is_first_tm = len(deploy_b) == 0

            run_dir = os.path.join(
                TSE_DIR, problem_name,
                '{}-{}'.format(traffic_seed, model),
                '{}-per_site'.format(size))
            if not os.path.exists(run_dir):
                os.makedirs(run_dir)

            try:
                print('\n' + '=' * 60)
                print('TSE, TM {} for {}: seed {} model {} scale {}'.format(
                    tm_index, problem_name, traffic_seed, model,
                    scale_factor))
                print('=' * 60)

                # ---- Stage 1 (mega): load the saved mega solution ------
                ssp_out = load_mega_solution(
                    problem_name, traffic_seed, model, size,
                    args.source_dir)

                # ---- inputs for R2R ------------------------------------
                ref_table_fname = os.path.join(
                    TOPOLOGIES_DIR, 'server2site-{}'.format(size),
                    '{}_server2site.pkl'.format(problem_name))
                with open(ref_table_fname, 'rb') as f:
                    ref_table = pickle.load(f)
                tm = load_srv_tm(
                    problem_name, model, traffic_seed, scale_factor,
                    size, param)
                site_topo_fname = os.path.join(
                    TOPOLOGIES_DIR, 'site_topologies', problem_name)
                G = Problem._read_graph_graphml(site_topo_fname, False)
                complete_path_fname = os.path.join(
                    TOPOLOGIES_DIR, 'paths', 'site-paths',
                    '{}-{}-paths_edge-disjoint-{}_dist-metric-{}-dict.pkl'
                    .format(problem_name, num_paths, edge_disjoint,
                            dist_metric))
                with open(complete_path_fname, 'rb') as f:
                    complete_path_dict = pickle.load(f)
                # canonical tunnel id (fixed_path_num): sorted site pairs
                # -> contiguous ranges, same convention as SSP_ORDER_MAIN
                path_to_num = {}
                pn = 0
                for sp in sorted(complete_path_dict.keys()):
                    for p in complete_path_dict[sp]:
                        path_to_num[tuple(p)] = pn
                        pn += 1

                # Convert the mega artifact and build its compact integer
                # assignment in the same pass, avoiding a second traversal
                # over millions of endpoint pairs inside R2RSolver.
                f_hat, f_hat_encoded = to_tunnel_assign(
                    ssp_out, path_to_num, len(ref_table))

                # ---- Stage 2 (R2R) --------------------------------------
                solver = R2RSolver(
                    deploy_b, f_hat, tm, G, ref_table,
                    path_to_num=path_to_num,
                    epsilon=epsilon, loss_weight=loss_weight,
                    tol=args.tol,
                    workers=args.r2r_workers,
                    parallel_threshold=args.parallel_threshold,
                    prev_encoded=deploy_encoded,
                    cur_encoded=f_hat_encoded)
                deploy, stats = solver.solve()

                assert not stats['new_violations'], \
                    'R2R created a new link-capacity violation'
                ssp_out_final = to_ssp_out(deploy)
                sol_fname = os.path.join(
                    run_dir, '{}-{}-tse_solution.pkl'.format(
                        problem_name, size))
                with open(sol_fname, 'wb') as w:
                    pickle.dump({'ssp_out': ssp_out_final,
                                 'r2r_stats': stats,
                                 'tm_index': tm_index}, w)
                print('Saved TSE solution to {}'.format(sol_fname))

                # this round's actual deployment is next round's b
                deploy_b = deploy
                deploy_encoded = solver.encoded_assignment

                print('TM {}: mega reordered={} -> TSE reordered={} '
                      '(exchanges={}, candidates={})'.format(
                          tm_index, stats['reordered_before'],
                          stats['reordered_after'], stats['exchanges'],
                          stats['num_candidates']))
                total_demand = float(tm.sum())
                print('satisfied {:.2f} ({:.4f}% of {:.2f}, unchanged: {}) | '
                      'max util {:.4f} | inherited viol {} new viol {} | '
                      'R2R {:.3f}s'.format(
                          stats['satisfied_demand'],
                          100.0 * stats['satisfied_demand'] / total_demand,
                          total_demand,
                          stats['satisfied_demand'] ==
                          stats['satisfied_demand_before'],
                          stats['max_link_util'],
                          len(stats['inherited_violations']),
                          len(stats['new_violations']),
                          stats['r2r_runtime']))

                result_line = PLACEHOLDER.format(
                    problem_name, tm_index, traffic_seed, size, 'tse',
                    epsilon, loss_weight, stats['obj_val'],
                    stats['num_common_pairs'],
                    stats['reordered_before'], stats['reordered_after'],
                    stats['reorder_reduction'],
                    stats['num_reordered_groups'],
                    stats['num_candidates'],
                    stats['num_dz_positive'],
                    stats['exchanges'],
                    stats['satisfied_demand'],
                    stats['satisfied_demand_before'],
                    '{:.4f}'.format(
                        100.0 * stats['satisfied_demand'] / total_demand),
                    stats['max_link_util'],
                    len(stats['inherited_violations']),
                    len(stats['new_violations']),
                    stats['r2r_runtime'],
                )
                print_(result_line, file=results)

            except Exception:
                print_('TSE failed for problem {} TM seed {} model {}'
                       .format(problem_name, traffic_seed, model))
                traceback.print_exc(file=sys.stdout)


def get_tse_problems(args):
    if args.problem:
        benchmark_consts.PROBLEM_NAMES = [args.problem]
    if args.tm_model:
        benchmark_consts.TM_MODELS = [args.tm_model]
    grouped = benchmark_consts.formulate('site', args.server)
    problems = []
    for (problem_name, _model, _scale), topo_and_tm_fnames in grouped.items():
        for slice_idx in args.slices:
            if slice_idx < len(topo_and_tm_fnames):
                topo_fname, tm_fname = topo_and_tm_fnames[slice_idx]
                problems.append((problem_name, topo_fname, tm_fname))
    return problems


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', type=int, required=True)
    parser.add_argument('--slices', type=int, nargs='+', default=[0],
                        help='which TM matrices to process, in order')
    parser.add_argument('--problem', type=str, default=None)
    parser.add_argument('--tm-model', dest='tm_model', type=str,
                        default=None)
    parser.add_argument('--epsilon', type=float, default=0.1)
    parser.add_argument('--lambda', dest='loss_weight', type=float,
                        default=0.5)
    parser.add_argument('--tol', type=float, default=1e-6)
    parser.add_argument('--r2r-workers', dest='r2r_workers', type=int,
                        default=0,
                        help='NumPy worker threads for large R2R reductions '
                             '(default 0 = auto, capped at 8)')
    parser.add_argument('--parallel-threshold', dest='parallel_threshold',
                        type=int, default=1000000,
                        help='minimum array elements per R2R worker chunk '
                             '(default 1000000)')
    parser.add_argument('--source-dir', dest='source_dir', type=str,
                        default=SOURCE_DIR,
                        help='run directory holding mega ssp_solution.pkl '
                             'artifacts (default Mega-logs)')
    parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                        default=False)
    args = parser.parse_args()

    problems = get_tse_problems(args)
    if args.dry_run:
        print('Problems to run:')
        for p in problems:
            print(p)
    else:
        if not os.path.exists(TSE_DIR):
            os.makedirs(TSE_DIR)
        tse_chain(problems, args)
