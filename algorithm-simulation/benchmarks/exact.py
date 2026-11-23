#! /usr/bin/env python

# Exact Gurobi solver benchmark for the ORIGINAL MegaOrder TE optimization
# problem (paper Eqs. (1)-(4)). Solves each TM matrix's 0-1 ILP to global
# optimality (or reports explicitly when optimality is NOT proven within the
# time limit) and records solver statistics to evaluate the scalability of
# exact solving.
#
# Protocol (mirrors mega_order_benchmark / tse.py):
#   - TM matrices are processed in sequence per problem;
#   - for the FIRST TM the deployed configuration b is IMPORTED from
#     mega's ssp_solution.pkl (Mega-logs) instead of being solved: all
#     three methods (mega / tse / exact) then start the chain from the
#     same initial deployment, so TM2-round reordered pairs / throughput
#     are directly comparable across methods;
#   - for subsequent TMs the original problem's 0/1 ILP is solved to
#     global optimality (or explicitly reported when NOT proven within
#     the time limit) against the previous round's deployment;
#   - history resets when the problem (topology) changes.
#
# Usage examples (run from benchmarks/, mega must have run first):
#   python exact.py --server 1 --problem Uninett2010.graphml --slices 0
#   python exact.py --server 1 --problem Uninett2010.graphml --slices 0 1
#   python exact.py --server 10 --problem Uninett2010.graphml --slices 0 1
#   python exact.py --server 10 --problem Uninett2010.graphml --slices 0 1 --lambda 0.5

import argparse
import os
import pickle
import sys
import traceback

sys.path.append('..')

import benchmark_consts
from benchmark_consts import print_, MEGA_HYPERPARAMS
from lib.config import TOPOLOGIES_DIR
from lib.algorithms.exact_solver import EXACT_MAIN

EXACT_DIR = 'Exact-logs'
MEGA_DIR = 'Mega-logs'


HEADERS = [
    'problem', 'num_nodes', 'num_edges', 'traffic_seed', 'scale_factor',
    'tm_model', 'server_per_site', 'num_site_pairs', 'num_tunnels',
    'num_endpoint_pairs', 'total_demand', 'unroutable_demand', 'algo',
    'num_paths', 'edge_disjoint', 'dist_metric', 'epsilon', 'loss_weight',
    'tm_index',
    'is_first_tm', 'status', 'proven_optimal', 'obj_val', 'obj_bound',
    'mip_gap', 'gurobi_runtime', 'build_time', 'total_runtime', 'num_bin_vars',
    'num_constraints', 'satisfied_demand', 'satisfied_demand_pct',
    'loss_value', 'reordered_pairs', 'weight_penalty',
]
PLACEHOLDER = ','.join('{}' for _ in HEADERS)


def _csv_val(v):
    return '' if v is None else v


def get_exact_problems(args):
    # --problem / --tm-model override the benchmark_consts selections
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


def load_mega_prev_assignment(problem_name, traffic_seed, model, size):
    """Load mega's ssp_solution.pkl for (problem, seed) and convert it to
    ExactSolver's prev_assignment format {(srv_i, srv_j): (k, t)}."""
    num_paths, edge_disjoint, dist_metric = MEGA_HYPERPARAMS
    sol_fname = os.path.join(
        MEGA_DIR, problem_name, '{}-{}'.format(traffic_seed, model),
        '{}-per_site'.format(size),
        '{}-{}-ssp_solution.pkl'.format(problem_name, size))
    with open(sol_fname, 'rb') as f:
        sol = pickle.load(f)
    if isinstance(sol, dict) and 'ssp_out' in sol:
        sol = sol['ssp_out']
    paths_fname = os.path.join(
        TOPOLOGIES_DIR, 'paths', 'site-paths',
        '{}-{}-paths_edge-disjoint-{}_dist-metric-{}-dict.pkl'.format(
            problem_name, num_paths, edge_disjoint, dist_metric))
    with open(paths_fname, 'rb') as f:
        tunnels_dict = pickle.load(f)
    ref_fname = os.path.join(
        TOPOLOGIES_DIR, 'server2site-{}'.format(size),
        '{}_server2site.pkl'.format(problem_name))
    with open(ref_fname, 'rb') as f:
        ref_table = pickle.load(f)

    path_to_kt = {}
    for k, paths in tunnels_dict.items():
        for t, p in enumerate(paths):
            path_to_kt[tuple(p)] = (k, t)
    prev = {}
    for (i, j), srv_path in sol.items():
        kt = path_to_kt.get(tuple(srv_path[1:-1]))
        if kt is None:
            raise Exception('mega tunnel for pair ({}, {}) not in the '
                            'candidate tunnel dict'.format(i, j))
        assert kt[0] == (ref_table[i], ref_table[j]), \
            'tunnel endpoints do not match the pair\'s sites'
        prev[(i, j)] = kt
    return prev


def exact_benchmark(problems, args):
    size = args.server
    num_paths, edge_disjoint, dist_metric = MEGA_HYPERPARAMS

    previous_assignment = {}
    previous_problem_name = None
    tm_counter = {}

    with open('exact.csv', 'a') as results:
        print_(','.join(HEADERS), file=results)
        for problem_name, topo_fname, tm_fname in problems:
            # parse the site TM filename (same convention as SSP_ORDER_MAIN)
            vals = os.path.basename(tm_fname)[:-4].split('_')
            model = vals[1]
            traffic_seed = int(vals[2])
            scale_factor = float(vals[3])

            if previous_problem_name != problem_name:
                if previous_problem_name is not None:
                    print("Problem changed from '{}' to '{}', resetting history"
                          .format(previous_problem_name, problem_name))
                previous_assignment = {}
            previous_problem_name = problem_name

            tm_index = tm_counter.get(problem_name, 0)
            tm_counter[problem_name] = tm_index + 1
            is_first_tm = len(previous_assignment) == 0

            if is_first_tm:
                # import mega's first-TM deployment as the initial b so all
                # three methods share the same starting point; no ILP solve
                # and no csv row for TM 0
                previous_assignment = load_mega_prev_assignment(
                    problem_name, traffic_seed, model, size)
                print('TM {}: imported mega deployment ({} pairs) as the '
                      'initial b; skipping exact solve for this TM'.format(
                          tm_index, len(previous_assignment)))
                continue

            print('\n' + '=' * 60)
            print('Exact solver, TM matrix {} for {}: seed {}, model {}, '
                  'scale {}'.format(tm_index, problem_name, traffic_seed,
                                    model, scale_factor))
            print('=' * 60 + '\n')

            run_dir = os.path.join(
                EXACT_DIR, problem_name,
                '{}-{}'.format(traffic_seed, model),
                '{}-per_site'.format(size))
            if not os.path.exists(run_dir):
                os.makedirs(run_dir)

            try:
                em = EXACT_MAIN(
                    size, problem_name, model, traffic_seed, scale_factor,
                    tm_fname,
                    prev_assignment=previous_assignment,
                    epsilon=args.epsilon,
                    loss_weight=args.loss_weight,
                    time_limit=args.time_limit,
                    threads=args.threads,
                    run_dir=run_dir,
                    save_model=args.save_model,
                    num_paths=num_paths,
                    edge_disjoint=edge_disjoint,
                    dist_metric=dist_metric)

                stats = em.stats
                # self-chain: this TM's optimal assignment is the next TM's b
                previous_assignment = em.assignment

                result_line = PLACEHOLDER.format(
                    problem_name,
                    len(em.graph.nodes),
                    len(em.graph.edges),
                    traffic_seed,
                    scale_factor,
                    model,
                    size,
                    stats['num_site_pairs'],
                    stats['num_tunnels'],
                    stats['num_endpoint_pairs'],
                    stats['total_demand'],
                    stats['unroutable_demand'],
                    'exact',
                    num_paths,
                    edge_disjoint,
                    dist_metric,
                    args.epsilon,
                    stats['loss_weight'],
                    tm_index,
                    is_first_tm,
                    stats['status'],
                    stats['proven_optimal'],
                    _csv_val(stats['obj_val']),
                    _csv_val(stats['obj_bound']),
                    _csv_val(stats['mip_gap']),
                    stats['gurobi_runtime'],
                    stats['build_time'],
                    stats['total_runtime'],
                    stats['num_bin_vars'],
                    stats['num_constraints'],
                    stats['satisfied_demand'],
                    _csv_val(stats['satisfied_demand_pct']),
                    stats['loss_value'],
                    stats['reordered_pairs'],
                    stats['weight_penalty'],
                )
                print_(result_line, file=results)

                if not stats['proven_optimal']:
                    print_('NOTE: TM {} (seed {}) NOT proven optimal '
                           '(status {}); incumbent is NOT a certified '
                           'global optimum'.format(
                               tm_index, traffic_seed, stats['status']))

                print('\nCompleted TM matrix {} for {}'.format(
                    tm_index, problem_name))

            except Exception:
                print_(
                    'Exact solver failed, problem {}, traffic seed {}, '
                    'traffic model {}'.format(problem_name, traffic_seed,
                                              model))
                traceback.print_exc(file=sys.stdout)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', type=int, required=True,
                        help='number of servers per site')
    parser.add_argument('--slices', type=int, nargs='+', default=[0],
                        help='which TM matrices (indices into each sorted '
                             'problem group) to solve in order')
    parser.add_argument('--problem', type=str, default=None,
                        help='restrict to a single topology, e.g. '
                             'Uninett2010.graphml')
    parser.add_argument('--tm-model', dest='tm_model', type=str,
                        default=None,
                        help='traffic matrix model (default: uniform via '
                             'benchmark_consts)')
    parser.add_argument('--time-limit', dest='time_limit', type=float,
                        default=3600.0,
                        help='Gurobi time limit per TM in seconds '
                             '(default 3600)')
    parser.add_argument('--epsilon', type=float, default=0.1,
                        help='epsilon in the objective (default 0.1)')
    parser.add_argument('--lambda', dest='loss_weight', type=float,
                        default=0.5,
                        help='lambda: weight of the reordered loss in the '
                             'objective (default 0.5; 1.0 reproduces the '
                             'paper\'s original objective)')
    parser.add_argument('--threads', type=int, default=0,
                        help='Gurobi threads (default 0 = all cores)')
    parser.add_argument('--no-save-model', dest='save_model',
                        action='store_false', default=True,
                        help='do not write the .lp model file')
    parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                        default=False)
    args = parser.parse_args()

    problems = get_exact_problems(args)
    if args.dry_run:
        print('Problems to run:')
        for problem in problems:
            print(problem)
    else:
        if not os.path.exists(EXACT_DIR):
            os.makedirs(EXACT_DIR)
        exact_benchmark(problems, args)
