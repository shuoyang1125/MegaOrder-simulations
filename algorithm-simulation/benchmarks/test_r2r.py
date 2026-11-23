#! /usr/bin/env python

# Correctness tests for the TSE / R2R module (lib/algorithms/r2r_exchange.py).
#
# Part A: unit tests on crafted small instances (hand-computed DeltaZ,
#   capacity revival, no double-exchange, invariants).
# Part B: K5 synthetic chain end-to-end (the acceptance demo): real
#   SiteLP + real SSP over two TMs, R2R halves the reordered pairs.
#
# Run from benchmarks/:
#   python test_r2r.py            # all parts
#   python test_r2r.py --part a   # unit tests only
#   python test_r2r.py --part b   # K5 chain only

import argparse
import io
import os
import sys
import time
from collections import defaultdict

sys.path.append('..')

import numpy as np
import networkx as nx

from lib.algorithms.r2r_exchange import R2RSolver
from lib.algorithms.te_objective import evaluate_assignment_objective

FAILED = []


def check(cond, label):
    tag = 'PASS' if cond else 'FAIL'
    print('  [{}] {}'.format(tag, label))
    if not cond:
        FAILED.append(label)


def make_env(sites, links):
    """Small site graph; links = [(u, v, cap)]"""
    G = nx.DiGraph()
    G.add_nodes_from(range(sites))
    for u, v, c in links:
        G.add_edge(u, v, capacity=c)
    return G


# ======================================================================
# Part A: unit tests
# ======================================================================
def part_a():
    print('\n' + '=' * 60)
    print('Part A: unit tests (crafted instances)')
    print('=' * 60)

    # 4 sites; site pair (0,1) has tunnel U=(0,1) direct, T=(0,2,1) detour.
    G = make_env(4, [(0, 1, 10.0), (0, 2, 10.0), (2, 1, 10.0),
                     (1, 3, 10.0), (3, 0, 10.0)])
    # servers 1,2 at site 0; servers 3,4 at site 1
    ref_table = [-1, 0, 0, 1, 1]
    tm = np.zeros((5, 5))
    # pairs (1,3) and (2,4) both in site pair (0,1) -- reciprocal possible
    tm[1, 3] = 2.0
    tm[2, 4] = 2.0

    U = (0, 1)
    T = (0, 2, 1)

    # ------------------------------------------------------------------
    print('\nA1: DeltaZ formula and exchange effect')
    b = {(1, 3): U, (2, 4): T}
    f = {(1, 3): T, (2, 4): U}      # perfectly reciprocal
    path_to_num = {U: 0, T: 1}
    solver = R2RSolver(b, f, tm, G, ref_table, path_to_num,
                       epsilon=0.1, loss_weight=0.5)
    new_f, stats = solver.solve()
    # w_u = 1/10, w_t = 2/10; dz = 0.5*(2+2) - 0.1*(2-2)*(w_u-w_t) = 2.0
    check(stats['num_candidates'] == 1, 'A1 one reciprocal candidate')
    check(stats['num_dz_positive'] == 1,
          'A1 candidate survives DeltaZ filter (dz=2.0)')
    check(stats['exchanges'] == 1, 'A1 exchange executed')
    check(stats['reordered_before'] == 2 and stats['reordered_after'] == 0,
          'A1 reordered 2 -> 0')
    check(new_f == b, 'A1 both pairs restored to previous tunnels')
    evaluated = evaluate_assignment_objective(
        new_f, b, tm, G, epsilon=0.1, loss_weight=0.5)
    check(abs(stats['obj_val'] - evaluated['obj_val']) < 1e-12,
          'A1 incremental obj_val matches shared exact-objective evaluator')

    # ------------------------------------------------------------------
    print('\nA2: DeltaZ <= 0 filtering')
    tm2 = np.zeros((5, 5))
    tm2[1, 3] = 1.0
    tm2[2, 4] = 9.0
    solver = R2RSolver(b, f, tm2, G, ref_table, path_to_num,
                       epsilon=0.1, loss_weight=0.0)
    _, stats = solver.solve()
    # lam=0: dz = -eps*(di-dj)*(w_u-w_t) = -0.1*(1-9)*(1/10-2/10) = -0.08
    check(stats['num_candidates'] == 1 and stats['num_dz_positive'] == 0,
          'A2 DeltaZ<=0 candidate discarded')
    check(stats['exchanges'] == 0 and stats['reordered_after'] == 2,
          'A2 no exchange, reordered unchanged')

    # ------------------------------------------------------------------
    print('\nA3: capacity-blocked candidate revived by a later exchange')
    # Site pair (0,1), tunnels U=(0,1) [1 hop] and T=(0,2,1) [2 hops].
    # Contended edge (0,2), c=20; initial f-load on it is exactly 20
    # (i1: 9 + i2: 8 + stable: 3), so cap is saturated.
    #   movers: i1=(1,4) d=9  b=U f=T ; j1=(2,5) d=11 b=T f=U
    #           i2=(3,6) d=8  b=U f=T ; j2=(1,5) d=3  b=T f=U
    #   stable: s=(2,4) d=3  b=T f=T (excluded from R2R)
    # DeltaLoad_(0,2) of candidate (i,j) = d_j - d_i:
    #   (i1,j1): +2  -> 22 > 20 BLOCKED (highest DeltaZ)
    #   (i2,j1): +3  -> 23 > 20 BLOCKED (second highest)
    #   (i1,j2): -6  -> feasible, executes first
    #   (i2,j2): -5  -> j2 consumed by (i1,j2) -> dead
    # After (i1,j2): load 14; rescan revives (i2,j1): 14+3=17 <= 20.
    # A single-pass greedy would stop at 1 exchange; the rescanning loop
    # must report 2.
    G3 = make_env(3, [(0, 1, 30.0), (0, 2, 20.0), (2, 1, 20.0)])
    ref3 = [-1, 0, 0, 0, 1, 1, 1]      # srv 1,2,3 @site0; 4,5,6 @site1
    tm3 = np.zeros((7, 7))
    tm3[1, 4] = 9.0
    tm3[2, 5] = 11.0
    tm3[3, 6] = 8.0
    tm3[1, 5] = 3.0
    tm3[2, 4] = 3.0
    b3 = {(1, 4): U, (2, 5): T, (3, 6): U, (1, 5): T, (2, 4): T}
    f3 = {(1, 4): T, (2, 5): U, (3, 6): T, (1, 5): U, (2, 4): T}
    solver = R2RSolver(b3, f3, tm3, G3, ref3, path_to_num)
    new_f3, stats3 = solver.solve()
    check(stats3['num_candidates'] == 4, 'A3 four candidates generated')
    check(stats3['exchanges'] == 2,
          'A3 blocked candidate revived (2 exchanges; single-pass=1)')
    check(stats3['reordered_before'] == 4
          and stats3['reordered_after'] == 0, 'A3 reordered 4 -> 0')
    check(all(new_f3[p] == b3[p] for p in b3),
          'A3 all movers restored to previous tunnels')

    # ------------------------------------------------------------------
    print('\nA4: capacity-blocked candidate stays blocked; overshoot '
          'grandfathered')
    # Same tunnels; edge (0,2) c=10 but initial f-load is 11 (i on T
    # with d=9 + stable 2): the mega overshoot is GRANDFATHERED
    # (cap=11), but the candidate's DeltaLoad +2 would push 13 > 11 --
    # refused. inherited violation must be reported, no new one.
    G4 = make_env(3, [(0, 1, 30.0), (0, 2, 10.0), (2, 1, 10.0)])
    tm4 = np.zeros((7, 7))
    tm4[1, 4] = 9.0     # i=(1,4): b=U f=T
    tm4[2, 5] = 11.0    # j=(2,5): b=T f=U
    tm4[2, 4] = 2.0     # stable on T
    b4 = {(1, 4): U, (2, 5): T, (2, 4): T}
    f4 = {(1, 4): T, (2, 5): U, (2, 4): T}
    solver = R2RSolver(b4, f4, tm4, G4, ref3, path_to_num)
    _, stats4 = solver.solve()
    check(stats4['num_candidates'] == 1,
          'A4 candidate exists (real capacity test, not vacuous)')
    check(stats4['exchanges'] == 0,
          'A4 capacity-blocked candidate not executed')
    check(stats4['reordered_after'] == 2, 'A4 reordered unchanged (2)')
    check(len(stats4['inherited_violations']) == 2,
          'A4 inherited overshoot reported (both detour edges: 11 > c 10)')
    check(not stats4['new_violations'], 'A4 no new violations')

    # ------------------------------------------------------------------
    print('\nA5: one-exchange-per-pair rule')
    # two reciprocal groups sharing an endpoint pair; the shared pair
    # may only be exchanged once.
    G5 = make_env(5, [(0, 1, 100.0), (0, 2, 100.0), (2, 1, 100.0),
                      (0, 3, 100.0), (3, 1, 100.0)])
    ref5 = [-1, 0, 0, 1, 1]     # servers 1,2 at site 0; 3,4 at site 1
    tm5 = np.zeros((5, 5))
    tm5[1, 3] = 2.0
    tm5[2, 4] = 3.0
    tm5[1, 4] = 4.0
    Ua, Ta, Ub, Tb = (0, 1), (0, 2, 1), (0, 1), (0, 3, 1)
    # Ua and Ub are the SAME tunnel (0,1) -- canonical ids differ below
    path5 = {Ua: 0, Ta: 1, Ub: 0, Tb: 2}
    b6 = {(1, 3): Ua, (2, 4): Ta, (1, 4): Tb}
    f6 = {(1, 3): Ta, (2, 4): Ua, (1, 4): Ua}
    # reciprocal groups: k=(0,1): R_{u->t} has (2,4); R_{t->u} has (1,3)
    # pair (1,4): b=Tb, f=Ua: Tb has no reverse group -> no candidate.
    solver = R2RSolver(b6, f6, tm5, G5, ref5, path5)
    new_f, stats = solver.solve()
    check(stats['exchanges'] == 1, 'A5 single exchange for the group')
    check(new_f[(2, 4)] == Ta and new_f[(1, 3)] == Ua,
          'A5 the exchanged pair restored; others untouched')
    check(new_f[(1, 4)] == Ua, 'A5 non-reciprocal mover untouched')

    # ------------------------------------------------------------------
    print('\nA6: unassigned pairs excluded')
    b7 = {(1, 3): U}                  # (2,4) not deployed last round
    f7 = {(1, 3): T, (2, 4): U}       # mega assigned it this round
    solver = R2RSolver(b7, f7, tm, G, ref_table, path_to_num)
    _, stats = solver.solve()
    check(stats['num_candidates'] == 0,
          'A6 pairs absent from b are not exchange candidates')
    check(stats['reordered_after'] == 1,
          'A6 the unassigned pair keeps its mega tunnel')

    # ------------------------------------------------------------------
    print('\nA7: throughput / assignment-set invariants')
    solver = R2RSolver(b, f, tm, G, ref_table, path_to_num)
    new_f, stats = solver.solve()
    check(abs(stats['satisfied_demand'] -
              stats['satisfied_demand_before']) < 1e-9,
          'A7 satisfied demand preserved')

    # ------------------------------------------------------------------
    print('\nA8: encoded assignments and parallel NumPy path')
    prev_encoded = np.full(len(ref_table) ** 2, -1, dtype=np.int32)
    cur_encoded = np.full(len(ref_table) ** 2, -1, dtype=np.int32)
    for pair, tunnel in b.items():
        prev_encoded[pair[0] * len(ref_table) + pair[1]] = \
            path_to_num[tunnel]
    for pair, tunnel in f.items():
        cur_encoded[pair[0] * len(ref_table) + pair[1]] = \
            path_to_num[tunnel]
    solver = R2RSolver(
        b, f, tm, G, ref_table, path_to_num,
        workers=2, parallel_threshold=1,
        prev_encoded=prev_encoded, cur_encoded=cur_encoded)
    encoded_f, encoded_stats = solver.solve()
    check(encoded_f == b, 'A8 encoded/parallel result matches dictionary path')
    check(encoded_stats['reordered_before'] == 2 and
          encoded_stats['reordered_after'] == 0,
          'A8 encoded/parallel reordered 2 -> 0')
    check(solver.encoded_assignment[1 * len(ref_table) + 3] ==
          path_to_num[U], 'A8 returned encoding tracks committed exchange')


# ======================================================================
# Part B: K5 synthetic chain (acceptance demo)
# ======================================================================
K5_SITES = 5
K5_SIZE = 10
K5_SCALE = 0.5
K5_SEEDS = (100, 1000, 2000)      # targets, TM1 noise, TM2 noise


def _k5_ref_table():
    ref = []
    for s in range(K5_SITES):
        ref.append(-1)
        ref.extend([s] * K5_SIZE)
    return ref


def _k5_gen_targets(seed):
    rs = np.random.RandomState(seed)
    pairs = [(a, b) for a in range(K5_SITES)
             for b in range(K5_SITES) if a != b]
    t = {}
    for k in pairs:
        if rs.uniform() < 0.45:
            t[k] = rs.uniform(200.0, 600.0) * K5_SCALE
        else:
            t[k] = rs.uniform(1600.0, 2600.0) * K5_SCALE
    return t


def _k5_gen_tm(seed, targets, ref, site_servers):
    rs = np.random.RandomState(seed)
    n = len(ref)
    tm = np.zeros((n, n))
    for (a, b), tgt in targets.items():
        ia, ib = site_servers[a], site_servers[b]
        noise = rs.uniform(0.1, 1.0, size=(len(ia), len(ib)))
        block = tgt * noise / noise.sum()
        for x, i in enumerate(ia):
            for y, j in enumerate(ib):
                tm[i, j] = block[x, y]
    return tm


def part_b():
    print('\n' + '=' * 60)
    print('Part B: K5 synthetic chain (real SiteLP + real SSP + R2R)')
    print('=' * 60)
    from lib.problem import Problem
    from lib.algorithms import SiteLP_Formulation
    from lib.algorithms.SSP import SSP

    sites = K5_SITES
    ref = _k5_ref_table()
    site_servers = {s: [i for i, r in enumerate(ref) if r == s]
                    for s in range(sites)}
    ordered_pairs = [(a, b) for a in range(sites)
                    for b in range(sites) if a != b]

    G = nx.DiGraph()
    G.add_nodes_from(range(sites))
    for a, b in ordered_pairs:
        G.add_edge(a, b, capacity=1000.0)

    targets = _k5_gen_targets(K5_SEEDS[0])
    tm1 = _k5_gen_tm(K5_SEEDS[1], targets, ref, site_servers)
    tm2 = _k5_gen_tm(K5_SEEDS[2], targets, ref, site_servers)
    print('K5: sites={} servers/site={} | TM1={:.0f} TM2={:.0f} '
          '(identical site totals -> shared LP)'.format(
              sites, K5_SIZE, tm1.sum(), tm2.sum()))

    # canonical tunnel ids for determinism
    path_to_num = {}
    pn = 0
    for a in range(sites):
        for b in range(sites):
            if a == b:
                continue
            # 4 edge-disjoint tunnels: direct + via each intermediate node
            for mid in range(sites):
                if mid != a and mid != b:
                    path_to_num[(a, mid, b)] = pn
                    pn += 1
            path_to_num[(a, b)] = pn
            pn += 1

    def run_lp(srv_tm):
        st = np.zeros((sites, sites))
        for (a, b) in ordered_pairs:
            ia, ib = site_servers[a], site_servers[b]
            st[a, b] = srv_tm[np.ix_(ia, ib)].sum()
        problem = Problem(G=G, traffic_matrix=st, seed=0, scale_factor=1.0)
        problem.name = 'k5sim'
        lp = SiteLP_Formulation.new_max_flow(
            4, True, 'inv-cap', out=io.StringIO())
        lp.solve(problem, top=False)
        return lp.ssp_output(), lp.obj_val

    def run_ssp(srv_tm, ssp_dict):
        ssp = SSP(srv_tm.copy(), [], ssp_dict, ref, delay=0, epsilon=0.1,
                  clas_mode=False, top_mode=True, debug=False)
        ssp.solve()
        ssp.output()
        return {(i, j): tuple(p[1:-1]) for (i, j), p in ssp.out.items()}

    # ---- round 1: mega on TM1 (deployed as b) ---------------------------
    ssp_dict, lp_obj = run_lp(tm1)
    t0 = time.time()
    assign_b = run_ssp(tm1, ssp_dict)
    ssp_runtime = time.time() - t0
    print('TM1: LP obj={:.0f} | mega deployed {} pairs ({:.1f}% of {:.0f})'
          .format(lp_obj, len(assign_b),
                  100 * sum(tm1[p] for p in assign_b) / tm1.sum(),
                  tm1.sum()))

    # ---- round 2: mega on TM2 (f-hat), shared LP products ---------------
    t0 = time.time()
    f_hat = run_ssp(tm2, ssp_dict)
    ssp_runtime2 = time.time() - t0
    mega_reordered = sum(1 for p in set(assign_b) & set(f_hat)
                        if assign_b[p] != f_hat[p])
    print('TM2: mega reordered={} vs deployed b | SSP {:.2f}s'.format(
        mega_reordered, ssp_runtime2))

    # ---- TSE: R2R post-processing ---------------------------------------
    solver = R2RSolver(assign_b, f_hat, tm2, G, ref,
                       path_to_num=path_to_num,
                       epsilon=0.1, loss_weight=0.5)
    deploy, stats = solver.solve()

    print('\n--- TSE (mega + R2R) results ---')
    print('reordered: mega={} -> TSE={} (reduction {}, {:.1f}%)'.format(
        stats['reordered_before'], stats['reordered_after'],
        stats['reorder_reduction'],
        100.0 * stats['reorder_reduction'] /
        max(1, stats['reordered_before'])))
    print('candidates={} (DeltaZ>0: {}) exchanges={}'.format(
        stats['num_candidates'], stats['num_dz_positive'],
        stats['exchanges']))
    print('satisfied {:.2f} == {:.2f} (unchanged)'.format(
        stats['satisfied_demand'], stats['satisfied_demand_before']))
    print('max link util {:.4f} | inherited violations {} | '
          'NEW violations {}'.format(
              stats['max_link_util'], len(stats['inherited_violations']),
              len(stats['new_violations'])))
    print('R2R runtime {:.4f}s | (SSP runtime {:.2f}s)'.format(
        stats['r2r_runtime'], ssp_runtime2))

    # ---- assertions (acceptance) -----------------------------------------
    check(stats['reordered_after'] < stats['reordered_before'],
          'B1 TSE reordered < mega reordered')
    check(stats['reorder_reduction'] >= 2 * stats['exchanges'] - 1,
          'B2 each exchange removes at least (2 movers - 1) reorders')
    check(abs(stats['satisfied_demand'] -
              stats['satisfied_demand_before']) < 1e-6,
          'B3 total carried demand unchanged')
    check(not stats['new_violations'], 'B4 no new capacity violations')
    check(set(deploy) == set(f_hat), 'B5 assigned-pair set unchanged')
    check(stats['exchanges'] > 0, 'B6 at least one exchange executed')
    return stats


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--part', choices=['a', 'b'], default=None)
    args = parser.parse_args()

    t0 = time.time()
    if args.part in (None, 'a'):
        part_a()
    if args.part in (None, 'b'):
        part_b()

    print('\n' + '=' * 60)
    if FAILED:
        print('RESULT: {} check(s) FAILED'.format(len(FAILED)))
        for f in FAILED:
            print('  - {}'.format(f))
        sys.exit(1)
    else:
        print('RESULT: all checks passed ({:.1f}s)'.format(time.time() - t0))


if __name__ == '__main__':
    main()
