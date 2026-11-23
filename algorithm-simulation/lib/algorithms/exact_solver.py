# Exact Gurobi solver for the MegaOrder TE optimization problem
# (paper Eqs. (1)-(4), with a tunable weight on the reordered loss):
#
#   max  sum_{k,i,t} d_k^i f_{k,t}^i
#        - eps * sum_{k,i,t} w_t d_k^i f_{k,t}^i
#        - lambda * L(f, b)
#   s.t. sum_{k,i,t} d_k^i f_{k,t}^i L(t,e) <= c_e     for all e in E
#        sum_t f_{k,t}^i <= 1                          for all k, i
#        f_{k,t}^i in {0, 1}
#
# Reordered loss linearization (b is a FIXED historical input, not a variable):
#   gamma_{k,t}^i = 1  iff  b_{k,t}^i = 0 and sum_{j != t} b_{k,j}^i = 1
#                      (pair i was previously assigned to some tunnel != t)
#   gamma_{k,t}^i = 0  otherwise
#   L(f, b) = sum_{k,i,t} d_k^i gamma_{k,t}^i f_{k,t}^i
#
# lambda scales the reordered loss term (named loss_weight in the code,
# since "lambda" is a Python keyword). loss_weight=1.0 reproduces the
# paper's original objective (implicit coefficient 1 on L(f, b));
# loss_weight < 1 makes reordering cheaper than dropping demand.
#
# For the first TM matrix there is no history (b = 0), hence L = 0; this
# mirrors the MegaOrder convention "for first TM matrix, use standard SSP".
#
# This module is standalone: it does not modify or call the SSP heuristics.
# It only reuses the same input data files as SSP_ORDER_MAIN.

import os
import time
import pickle

import numpy as np
from gurobipy import GRB, Model, LinExpr, quicksum

from ..config import TL_DIR, TOPOLOGIES_DIR, TM_DIR
from ..graph_utils import path_to_edge_list
from ..problem import Problem


_STATUS_NAMES = [
    'LOADED', 'OPTIMAL', 'INFEASIBLE', 'INF_OR_UNBD', 'UNBOUNDED', 'CUTOFF',
    'ITERATION_LIMIT', 'NODE_LIMIT', 'TIME_LIMIT', 'SOLUTION_LIMIT',
    'INTERRUPTED', 'SUBOPTIMAL', 'INPROGRESS', 'USER_OBJ_LIMIT',
    'WORK_LIMIT', 'NUMERIC',
]


def _status_name(code):
    for name in _STATUS_NAMES:
        if getattr(GRB, name, None) == code:
            return name
    return 'STATUS_{}'.format(code)


class ExactSolver(object):
    """0-1 ILP that exactly reproduces the paper's original problem.

    Only GRB.OPTIMAL is reported as a proven global optimum; any other
    status (e.g. TIME_LIMIT) is explicitly marked as not proven optimal,
    even when an incumbent solution exists.
    """

    def __init__(self, G, tunnels_dict, tm, ref_table, prev_assignment=None,
                 epsilon=0.1, loss_weight=0.5, time_limit=3600.0, threads=0,
                 log_fname=None, model_fname=None):
        self.G = G
        self.tunnels_dict = tunnels_dict
        self.tm = np.asarray(tm, dtype=np.float64)
        self.ref_table = list(ref_table)
        self.prev_assignment = dict(prev_assignment) if prev_assignment else {}
        self.epsilon = float(epsilon)
        self.loss_weight = float(loss_weight)
        self.time_limit = float(time_limit)
        self.threads = int(threads)
        self.log_fname = log_fname
        self.model_fname = model_fname

        self.model = None
        self.stats = {}
        self.assignment = {}
        self.ssp_out = {}

    def _tunnel_weight(self, path):
        # w_t = W(p) = sum_{e in p} 1/c_e (inv-cap metric; equals hops/1000
        # for homogeneous 1000 Mbps links), as used for tunnel construction
        w = 0.0
        for u, v in path_to_edge_list(path):
            w += 1.0 / self.G[u][v]['capacity']
        return w

    def solve(self):
        G = self.G
        tm = self.tm
        ref = self.ref_table
        tunnels = self.tunnels_dict
        n = len(ref)

        build_start = time.time()

        # ---- tunnel weights w_t (fixed parameters) ----
        tunnel_weight = {}
        for k, paths in tunnels.items():
            for t, path in enumerate(paths):
                tunnel_weight[(k, t)] = self._tunnel_weight(path)

        # ---- enumerate endpoint pairs and binary variables ----
        # var index -> (k, t, i, j, d, w_t, gamma)
        var_k = []
        var_t = []
        var_i = []
        var_j = []
        var_d = []
        var_w = []
        var_gamma = []
        edge_var_idx = {}   # edge -> [var indices]
        edge_coeff = {}     # edge -> [demand coefficients]
        pair_var_idx = {}   # (i, j) -> [var indices]
        unroutable_demand = 0.0
        intra_site_demand = 0.0

        for i in range(n):
            si = ref[i]
            if si == -1:
                continue
            for j in range(n):
                if i == j:
                    continue
                sj = ref[j]
                if sj == -1:
                    continue
                d = tm[i, j]
                if d <= 0.0:
                    continue
                if sj == si:
                    # intra-site demand cannot use inter-site tunnels
                    intra_site_demand += d
                    continue
                k = (si, sj)
                paths = tunnels.get(k)
                if not paths:
                    # no tunnel provisioned for this site pair
                    unroutable_demand += d
                    continue
                prev = self.prev_assignment.get((i, j))
                prev_t = prev[1] if (prev is not None and prev[0] == k) else None
                plist = pair_var_idx.setdefault((i, j), [])
                for t, path in enumerate(paths):
                    gamma = 1.0 if (prev_t is not None and t != prev_t) else 0.0
                    idx = len(var_d)
                    var_k.append(k)
                    var_t.append(t)
                    var_i.append(i)
                    var_j.append(j)
                    var_d.append(float(d))
                    var_w.append(tunnel_weight[(k, t)])
                    var_gamma.append(gamma)
                    plist.append(idx)
                    for e in path_to_edge_list(path):
                        if e not in edge_var_idx:
                            edge_var_idx[e] = []
                            edge_coeff[e] = []
                        edge_var_idx[e].append(idx)
                        edge_coeff[e].append(float(d))

        num_vars = len(var_d)
        num_pairs = len(pair_var_idx)

        # ---- build the Gurobi model ----
        m = Model('megaorder-exact')
        f = m.addVars(range(num_vars), vtype=GRB.BINARY)
        var_list = [f[x] for x in range(num_vars)]

        # objective: d * (1 - eps*w_t - loss_weight*gamma) per variable
        obj_coeffs = [var_d[x] * (1.0 - self.epsilon * var_w[x]
                                  - self.loss_weight * var_gamma[x])
                      for x in range(num_vars)]
        m.setObjective(LinExpr(obj_coeffs, var_list), GRB.MAXIMIZE)

        # capacity constraints: sum d*f*L(t,e) <= c_e
        for e, idxs in edge_var_idx.items():
            u, v = e
            cap = G[u][v]['capacity']
            m.addConstr(
                LinExpr(edge_coeff[e], [f[x] for x in idxs]) <= cap,
                name='cap_{}_{}'.format(u, v))

        # tunnel allocation constraints: sum_t f_{k,t}^i <= 1
        # (pairs with a single tunnel satisfy this trivially)
        multi_pairs = [pair for pair, idxs in pair_var_idx.items()
                       if len(idxs) > 1]
        num_assign_constrs = len(multi_pairs)
        m.addConstrs(
            (quicksum(f[x] for x in pair_var_idx[pair]) <= 1
             for pair in multi_pairs),
            name='assign')

        build_time = time.time() - build_start

        # ---- solver parameters ----
        m.Params.MIPGap = 0.0        # require proof of global optimality
        m.Params.MIPGapAbs = 0.0
        m.Params.TimeLimit = self.time_limit
        if self.threads > 0:
            m.Params.Threads = self.threads
        if self.log_fname:
            m.Params.LogFile = self.log_fname

        if self.model_fname:
            print('Writing LP model file to', self.model_fname)
            m.write(self.model_fname)

        self.model = m

        # ---- solve ----
        print('Solving exact ILP: {} binary vars, {} constraints '
              '({} capacity, {} assignment)'.format(
                  num_vars, len(edge_var_idx) + num_assign_constrs,
                  len(edge_var_idx), num_assign_constrs))
        m.optimize()

        # ---- status and solver statistics ----
        status_code = m.Status
        status_name = _status_name(status_code)
        proven_optimal = (status_code == GRB.OPTIMAL)
        sol_count = m.SolCount
        obj_val = m.ObjVal if sol_count > 0 else None
        obj_bound = None
        mip_gap = None
        try:
            obj_bound = m.ObjBound
        except Exception:
            pass
        try:
            if sol_count > 0:
                mip_gap = m.MIPGap
        except Exception:
            pass

        # ---- extract solution ----
        assignment = {}
        ssp_out = {}
        throughput = 0.0
        weight_penalty = 0.0
        loss_value = 0.0
        reordered_pairs = 0
        if sol_count > 0:
            xs = m.getAttr('X', var_list)
            for x in range(num_vars):
                if xs[x] > 0.5:
                    k = var_k[x]
                    t = var_t[x]
                    i = var_i[x]
                    j = var_j[x]
                    d = var_d[x]
                    assignment[(i, j)] = (k, t)
                    ssp_out[(i, j)] = [i] + tunnels[k][t] + [j]
                    throughput += d
                    weight_penalty += self.epsilon * var_w[x] * d
                    if var_gamma[x] > 0.5:
                        loss_value += d
                        reordered_pairs += 1

            self._check_solution(assignment, obj_val, throughput,
                                 weight_penalty, loss_value)

        total_demand = float(tm.sum())
        self.assignment = assignment
        self.ssp_out = ssp_out
        self.stats = {
            'status': status_name,
            'status_code': status_code,
            'proven_optimal': proven_optimal,
            'obj_val': obj_val,
            'obj_bound': obj_bound,
            'mip_gap': mip_gap,
            'gurobi_runtime': m.Runtime,
            'build_time': build_time,
            # end-to-end time to produce the TE config (Python model build +
            # Gurobi solve); reported separately from gurobi_runtime, which
            # is the number directly comparable to the baselines' LP runtime
            # (their Python-side model build time is excluded too)
            'total_runtime': m.Runtime + build_time,
            'num_vars': m.NumVars,
            'num_bin_vars': m.NumBinVars,
            'num_constraints': m.NumConstrs,
            'num_capacity_constraints': len(edge_var_idx),
            'num_assign_constraints': num_assign_constrs,
            'num_site_pairs': len(tunnels),
            'num_tunnels': sum(len(p) for p in tunnels.values()),
            'num_endpoint_pairs': num_pairs,
            'total_demand': total_demand,
            'unroutable_demand': unroutable_demand,
            'intra_site_demand': intra_site_demand,
            'satisfied_demand': throughput,
            'satisfied_demand_pct': (throughput / total_demand
                                     if total_demand > 0.0 else None),
            'loss_value': loss_value,
            'reordered_pairs': reordered_pairs,
            'weight_penalty': weight_penalty,
            'epsilon': self.epsilon,
            'loss_weight': self.loss_weight,
            'time_limit': self.time_limit,
            'is_first_tm': len(self.prev_assignment) == 0,
        }

        print('------------ Exact solver results ------------')
        print('Status: {} (proven optimal: {})'.format(status_name,
                                                       proven_optimal))
        if not proven_optimal:
            print('WARNING: solution NOT proven optimal within time limit; '
                  'any incumbent is NOT a certified global optimum')
        if obj_val is not None:
            print('Objective: {}'.format(obj_val))
        if obj_bound is not None:
            print('ObjBound: {}'.format(obj_bound))
        if mip_gap is not None:
            print('MIPGap: {}'.format(mip_gap))
        print('Gurobi runtime: {} s (build time: {} s, total: {} s)'.format(
            m.Runtime, build_time, m.Runtime + build_time))
        print('Epsilon: {}, loss weight (lambda): {}'.format(
            self.epsilon, self.loss_weight))
        print('Satisfied demand: {} / {} ({})'.format(
            throughput, total_demand,
            self.stats['satisfied_demand_pct']))
        print('Reordered pairs: {}, loss: {}, weight penalty: {}'.format(
            reordered_pairs, loss_value, weight_penalty))

        return self.stats

    def _check_solution(self, assignment, obj_val, throughput,
                        weight_penalty, loss_value):
        """Verify feasibility and objective of the extracted solution."""
        tm = self.tm
        G = self.G
        tunnels = self.tunnels_dict

        # capacity feasibility
        edge_load = {}
        for (i, j), (k, t) in assignment.items():
            d = tm[i, j]
            for e in path_to_edge_list(tunnels[k][t]):
                edge_load[e] = edge_load.get(e, 0.0) + d
        for e, load in edge_load.items():
            u, v = e
            cap = G[u][v]['capacity']
            # Gurobi incumbents can violate constraints by ~1e-5 (its own
            # "max constraint violation exceeds tolerance" warning); only
            # reject real violations, not solver numerical noise
            assert load <= cap + 1e-4, \
                'capacity violated on edge {}: {} > {}'.format(e, load, cap)

        # each endpoint pair assigned at most once (dict keys are unique)

        # objective recomputation
        obj_recomputed = throughput - weight_penalty - self.loss_weight * loss_value
        if obj_val is not None:
            assert abs(obj_recomputed - obj_val) <= 1e-6 * max(1.0, abs(obj_val)), \
                'objective mismatch: recomputed {} vs gurobi {}'.format(
                    obj_recomputed, obj_val)


class EXACT_MAIN(object):
    """Data-loading wrapper around ExactSolver.

    Mirrors SSP_ORDER_MAIN's input conventions: same ref_table / server TM /
    tunnel dict files, same site TM filename parsing. The site-level LP used
    by MegaOrder is NOT needed here: the original problem is solved directly.
    """

    def __init__(self, size, problem_name, model, traffic_seed, scale_factor,
                 tmuse, prev_assignment=None, epsilon=0.1, loss_weight=0.5,
                 time_limit=3600.0, threads=0, run_dir=None, save_model=True,
                 num_paths=4, edge_disjoint=True, dist_metric='inv-cap'):
        self.size = size
        self.problem_name = problem_name
        self.model = model
        self.traffic_seed = traffic_seed
        self.scale_factor = scale_factor
        self.tmuse = tmuse
        self.epsilon = epsilon
        self.loss_weight = loss_weight
        self.time_limit = time_limit
        self.threads = threads
        self.num_paths = num_paths
        self.edge_disjoint = edge_disjoint
        self.dist_metric = dist_metric

        self.stats = {}
        self.assignment = {}
        self.ssp_out = {}
        self.graph = None
        self.total_demand = None

        self.exact_main(size, problem_name, model, traffic_seed,
                        scale_factor, tmuse, prev_assignment, run_dir,
                        save_model)

    def exact_main(self, size, problem_name, model, traffic_seed,
                   scale_factor, tmuse, prev_assignment, run_dir, save_model):
        # parse the site TM filename to locate the matching server-level TM,
        # exactly like SSP_ORDER_MAIN
        vals = os.path.basename(tmuse)[:-4].split('_')
        param = vals[4]

        ref_table_fname = os.path.join(
            TOPOLOGIES_DIR, 'server2site-{}'.format(size),
            problem_name + '_server2site.pkl')
        tm_fname = os.path.join(
            TM_DIR, 'srv-traffic-matrices-{}'.format(size), model,
            '{}_{}_{}_{}_{}_traffic-matrix.pkl'.format(
                problem_name, model, traffic_seed, scale_factor, param))
        site_topo_fname = os.path.join(TOPOLOGIES_DIR, 'site_topologies',
                                       problem_name)
        paths_fname = os.path.join(
            TOPOLOGIES_DIR, 'paths', 'site-paths',
            '{}-{}-paths_edge-disjoint-{}_dist-metric-{}-dict.pkl'.format(
                problem_name, self.num_paths, self.edge_disjoint,
                self.dist_metric))

        with open(ref_table_fname, 'rb') as f:
            ref_table = pickle.load(f)
        with open(tm_fname, 'rb') as f:
            tm = pickle.load(f)
        with open(paths_fname, 'rb') as f:
            tunnels_dict = pickle.load(f)

        # site graph: largest SCC, integer node labels, 1000 Mbps links;
        # same id space as the pre-computed tunnel dict
        G = Problem._read_graph_graphml(site_topo_fname, False)

        # consistency checks between tunnels, ref_table and the site graph
        site_ids = set(s for s in ref_table if s != -1)
        assert site_ids <= set(G.nodes), \
            'ref_table contains site ids outside the site graph'
        for k, paths in tunnels_dict.items():
            assert k[0] in G and k[1] in G, \
                'tunnel site pair {} not in site graph'.format(k)
            for path in paths:
                for u, v in path_to_edge_list(path):
                    assert G.has_edge(u, v), \
                        'tunnel edge ({}, {}) not in site graph'.format(u, v)

        log_fname = None
        model_fname = None
        if run_dir:
            log_fname = os.path.join(
                run_dir, 'gurobi-{}.log'.format(traffic_seed))
            if save_model:
                model_fname = os.path.join(
                    run_dir, 'model-{}.lp'.format(traffic_seed))

        solver = ExactSolver(
            G, tunnels_dict, tm, ref_table,
            prev_assignment=prev_assignment,
            epsilon=self.epsilon,
            loss_weight=self.loss_weight,
            time_limit=self.time_limit,
            threads=self.threads,
            log_fname=log_fname,
            model_fname=model_fname)
        solver.solve()

        self.stats = solver.stats
        self.assignment = solver.assignment
        self.ssp_out = solver.ssp_out
        self.graph = G
        self.total_demand = solver.stats['total_demand']

        # persist the optimal assignment for the next TM (self-chained b)
        # and for comparison with MegaOrder solutions
        if run_dir:
            sol_fname = os.path.join(
                run_dir, '{}-{}-exact_solution.pkl'.format(problem_name, size))
            with open(sol_fname, 'wb') as w:
                pickle.dump({
                    'assignment': self.assignment,
                    'ssp_out': self.ssp_out,
                    'stats': self.stats,
                }, w)
            print('Saved exact solution to', sol_fname)
