# Two-Stage Exchange (TSE): R2R reciprocal-exchange post-processing module.
#
# Stage 1 (mega) is NOT re-implemented here: TSE consumes the mega
# solution (site LP + server-level SSP artifacts) as the initial TE
# configuration f-hat for the current round, and the previous round's
# actually-deployed configuration b. Stage 2 (R2R, Algorithm 2 of the
# paper) then looks for Reordered-to-Reordered exchanges:
#
#   R_{k,u->t} = { i : b_i = u, f_i = t, u != t }        (reordered sets)
#   candidates = U_k U_{u<t}  R_{k,u->t} x R_{k,t->u}   (reciprocal pairs)
#
# Exchanging (i, j) moves BOTH endpoint pairs back to their previous
# tunnels (i: t -> u, j: u -> t), which:
#   - removes both reordered losses         (gain:  lambda*(d_i + d_j))
#   - changes the path-weight penalty by   (delta: eps*(d_i - d_j)*(w_u - w_t))
#   - leaves total carried demand and the set of assigned pairs unchanged.
#
# Objective gain (computed once per candidate):
#   DeltaZ_{k,i,j} = lambda*(d_i + d_j) - eps*(d_i - d_j)*(w_u - w_t)
# Candidates with DeltaZ <= 0 are discarded.
#
# Link-load change (computed once per candidate, sparse):
#   DeltaLoad_e = (d_i - d_j) * (L(u,e) - L(t,e))
#
# Capacity feasibility uses the LATEST global loads and grandfathers the
# epsilon-overshoot inherited from the mega solution (SSP's knapsack may
# exceed each tunnel budget by up to eps, so mega deployments can sit a
# few percent above c_e on some links):
#   cap_e = max(c_e, initial Load_e)
# Exchanges may not create any NEW violation and may not worsen an
# inherited one. A candidate that is infeasible right now is NOT deleted:
# later exchanges can free capacity and revive it (single-pass greedy
# measurably under-exchanges; the loop rescans after every exchange).
#
# One exchange per iteration; an endpoint pair is exchanged at most once
# per invocation (all candidates touching a consumed pair are dropped).
#
# Parallelization note: large endpoint-pair scans are encoded as compact
# NumPy arrays.  Tunnel-load reduction and previous/current comparisons use
# deterministic contiguous chunks and worker threads (NumPy releases the GIL).
# Candidate volume is tiny on measured chains, so candidate scoring remains
# serial.  Exchange COMMITMENT must stay globally coordinated (sorted list,
# global capacity check, one exchange at a time) because site pairs share
# physical links.

import os
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import numpy as np


def _edges_of(tunnel):
    return list(zip(tunnel[:-1], tunnel[1:]))


class R2RSolver(object):
    """Algorithm 2 (R2R Exchange) as a standalone post-processor.

    Parameters
    ----------
    assign_prev : {(srv_i, srv_j): tunnel_tuple}
        Previous round's actually-deployed configuration b.
    assign_cur : {(srv_i, srv_j): tunnel_tuple}
        Current round's mega solution f-hat.
    tm : 2D numpy array
        Current round's server-level traffic matrix; tm[i, j] = d_k^i.
    G : networkx DiGraph (site level)
        Link capacities G[u][v]['capacity'].
    ref_table : list, server id -> site id (-1 for pad rows)
    path_to_num : {tunnel_tuple: int}
        Canonical tunnel id (e.g. fixed_path_num from the complete path
        dict); used only as an ordering key for the u < t convention and
        for deterministic tie-breaks. Tunnels missing from the map fall
        back to tuple ordering.
    epsilon, loss_weight : float
        Objective weights (w_t = sum_{e in t} 1/c_e, inv-cap metric).
    tol : float
        Floating-point tolerance for capacity and DeltaZ comparisons.
    workers : int
        NumPy worker threads; 0 selects up to eight available CPU cores.
    parallel_threshold : int
        Minimum number of array elements per worker chunk.
    prev_encoded, cur_encoded : int32 arrays or None
        Optional dense tunnel-id assignments, reused across TSE rounds.
    """

    def __init__(self, assign_prev, assign_cur, tm, G, ref_table,
                 path_to_num=None, epsilon=0.1, loss_weight=0.5, tol=1e-6,
                 workers=0, parallel_threshold=1000000,
                 prev_encoded=None, cur_encoded=None):
        self.assign_prev = dict(assign_prev)
        self.assign_cur = dict(assign_cur)
        self.tm = tm
        self.G = G
        self.ref_table = ref_table
        self.path_to_num = path_to_num or {}
        self.epsilon = float(epsilon)
        self.loss_weight = float(loss_weight)
        self.tol = float(tol)
        requested_workers = int(workers)
        if requested_workers > 0:
            self.workers = requested_workers
        else:
            self.workers = min(8, os.cpu_count() or 1)
        self.parallel_threshold = int(parallel_threshold)
        self.prev_encoded = prev_encoded
        self.cur_encoded = cur_encoded
        self.encoded_assignment = None

        self._tweight_cache = {}
        self._tunnel_to_id = dict(self.path_to_num)
        self._id_to_tunnel = {}
        for tunnel, tunnel_id in self._tunnel_to_id.items():
            self._id_to_tunnel[int(tunnel_id)] = tunnel
        self._next_tunnel_id = (max(self._id_to_tunnel) + 1
                                if self._id_to_tunnel else 0)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _tunnel_weight(self, tunnel):
        w = self._tweight_cache.get(tunnel)
        if w is None:
            w = 0.0
            for u, v in _edges_of(tunnel):
                w += 1.0 / self.G[u][v]['capacity']
            self._tweight_cache[tunnel] = w
        return w

    def _tnum(self, tunnel):
        n = self.path_to_num.get(tunnel)
        return n if n is not None else tunnel

    def _tunnel_id(self, tunnel):
        """Return a stable integer id, including for an unmapped tunnel."""
        tunnel_id = self._tunnel_to_id.get(tunnel)
        if tunnel_id is None:
            tunnel_id = self._next_tunnel_id
            self._next_tunnel_id += 1
            self._tunnel_to_id[tunnel] = tunnel_id
            self._id_to_tunnel[tunnel_id] = tunnel
        return int(tunnel_id)

    def _encode_assignment(self, assignment, num_endpoints):
        """Encode {(i,j): tunnel} as compact (pair_id, tunnel_id) records."""
        record_dtype = np.dtype([('pair', np.int64),
                                 ('tunnel', np.int32)])

        def records():
            for (i, j), tunnel in assignment.items():
                yield (i * num_endpoints + j, self._tunnel_id(tunnel))

        return np.fromiter(records(), dtype=record_dtype,
                           count=len(assignment))

    def _chunk_bounds(self, size):
        """Deterministic contiguous chunks for NumPy worker operations."""
        if self.workers <= 1 or size < self.parallel_threshold:
            return [(0, size)]
        num_chunks = min(self.workers, max(1, size // self.parallel_threshold))
        chunk_size = (size + num_chunks - 1) // num_chunks
        return [(start, min(size, start + chunk_size))
                for start in range(0, size, chunk_size)]

    def _aggregate_tunnel_loads(self, tunnel_ids, demands, num_tunnels):
        """Parallel NumPy reduction from endpoint-pair to tunnel loads."""
        bounds = self._chunk_bounds(len(tunnel_ids))

        def aggregate(bound):
            start, end = bound
            return np.bincount(
                tunnel_ids[start:end], weights=demands[start:end],
                minlength=num_tunnels)

        if len(bounds) == 1:
            return aggregate(bounds[0])
        with ThreadPoolExecutor(max_workers=len(bounds)) as executor:
            partials = list(executor.map(aggregate, bounds))
        # Fixed chunk order makes the floating-point reduction deterministic.
        total = partials[0]
        for partial in partials[1:]:
            total += partial
        return total

    def _analyze_encoded_assignments(self, prev_dense, cur_dense,
                                     num_endpoints, tm_flat):
        """Build reordered sets using parallel NumPy comparisons."""
        size = len(cur_dense)
        bounds = self._chunk_bounds(size)

        def analyze_chunk(bound):
            start, end = bound
            prev = prev_dense[start:end]
            cur = cur_dense[start:end]
            common = (prev >= 0) & (cur >= 0)
            reordered_local = np.flatnonzero(common & (prev != cur))
            return (int(np.count_nonzero(common)),
                    reordered_local.astype(np.int64, copy=False) + start)

        if len(bounds) == 1:
            analyzed = [analyze_chunk(bounds[0])]
        else:
            with ThreadPoolExecutor(max_workers=len(bounds)) as executor:
                analyzed = list(executor.map(analyze_chunk, bounds))

        num_common = sum(item[0] for item in analyzed)
        reordered_ids = [item[1] for item in analyzed if len(item[1])]
        if reordered_ids:
            reordered_ids = np.concatenate(reordered_ids)
        else:
            reordered_ids = np.empty(0, dtype=np.int64)

        R = defaultdict(list)
        reordered_demand = {}
        ref = self.ref_table
        for pair_id in reordered_ids:
            pair_id = int(pair_id)
            pair = (pair_id // num_endpoints, pair_id % num_endpoints)
            u = self._id_to_tunnel[int(prev_dense[pair_id])]
            t = self._id_to_tunnel[int(cur_dense[pair_id])]
            k = (ref[pair[0]], ref[pair[1]])
            R[(k, u, t)].append(pair)
            reordered_demand[pair] = float(tm_flat[pair_id])
        return R, reordered_demand, num_common, len(reordered_ids)

    def _score_site_pair_candidates(self, k, R_k, dcache):
        """Generate, score and filter candidates for one site pair.

        Candidate order is identical to the former generate-then-score
        implementation.  Fusing the passes avoids materializing a second
        full candidate list while preserving deterministic tie-breaking.
        """
        eps = self.epsilon
        lam = self.loss_weight
        tol = self.tol
        num_candidates = 0
        scored = []
        for (k1, u, t), pairs in sorted(R_k.items()):
            rev = R_k.get((k1, t, u))
            if not rev:
                continue
            if not self._tkey_less(u, t):
                continue
            for i in pairs:
                di = dcache[i]
                for j in rev:
                    num_candidates += 1
                    dj = dcache[j]
                    dz = lam * (di + dj) - eps * (di - dj) * \
                        (self._tunnel_weight(u) - self._tunnel_weight(t))
                    if dz <= tol:
                        continue

                    # Sparse DeltaLoad over the symmetric edge difference
                    # of u and t.
                    dl = defaultdict(float)
                    dd = di - dj
                    for e in _edges_of(u):
                        dl[e] += dd
                    for e in _edges_of(t):
                        dl[e] -= dd
                    dl = {e: v for e, v in dl.items() if v != 0.0}
                    tiebreak = (self._tnum(u), self._tnum(t), i, j)
                    scored.append((dz, tiebreak, (k, u, t, i, j), dl))
        return num_candidates, scored

    def _tkey_less(self, u, t):
        """Canonical ordering of two distinct tunnels."""
        nu, nt = self._tnum(u), self._tnum(t)
        if nu != nt:
            return nu < nt
        return u < t

    # ------------------------------------------------------------------
    # main entry
    # ------------------------------------------------------------------
    def solve(self):
        t_start = time.time()
        tol = self.tol
        # __init__ already copied the caller's mapping, so this private copy
        # can be updated in place without mutating the mega artifact.
        assign = self.assign_cur
        num_endpoints = len(self.ref_table)
        tm_flat = np.asarray(self.tm).reshape(-1)

        # ---- Step 1: compact integer encoding ----------------------------
        # pair_id = i*n+j and tunnel_id is the canonical path number.  The
        # compact arrays let NumPy perform the large reductions outside the
        # Python interpreter and release the GIL in worker threads.
        encode_start = time.time()
        if self.cur_encoded is None:
            cur_records = self._encode_assignment(assign, num_endpoints)
            cur_pairs = cur_records['pair']
            cur_tunnels = cur_records['tunnel']
            cur_dense = np.full(num_endpoints * num_endpoints, -1,
                                dtype=np.int32)
            cur_dense[cur_pairs] = cur_tunnels
        else:
            cur_dense = np.asarray(self.cur_encoded, dtype=np.int32).copy()
            cur_pairs = np.flatnonzero(cur_dense >= 0)
            cur_tunnels = cur_dense[cur_pairs]
            cur_records = None
        encode_current_time = time.time() - encode_start

        # ---- Step 2: vectorized tunnel and link loads --------------------
        load_start = time.time()
        demands = tm_flat[cur_pairs]
        # Preserve the original satisfied-demand accumulation order and
        # Python-float behavior used in CSV output.
        satisfied_demand = sum(map(float, demands))
        positive_demands = np.where(demands > 0.0, demands, 0.0)
        num_tunnels = max(self._next_tunnel_id,
                          int(cur_tunnels.max()) + 1 if len(cur_tunnels) else 0)
        tunnel_loads = self._aggregate_tunnel_loads(
            cur_tunnels, positive_demands, num_tunnels)

        loads = defaultdict(float)
        weight_penalty = 0.0
        for tunnel_id in np.flatnonzero(tunnel_loads):
            flow = float(tunnel_loads[tunnel_id])
            tunnel = self._id_to_tunnel[int(tunnel_id)]
            weight_penalty += self.epsilon * self._tunnel_weight(tunnel) * flow
            for e in _edges_of(tunnel):
                loads[e] += flow
        initial_loads = dict(loads)
        cap = {}
        for e in initial_loads:
            c_e = self.G[e[0]][e[1]]['capacity']
            # grandfather the mega solution's epsilon-overshoot
            cap[e] = c_e if c_e > initial_loads[e] else initial_loads[e]
        load_build_time = time.time() - load_start

        # Current records/demands are no longer needed; release their large
        # buffers before encoding the previous deployment.
        del cur_records, cur_pairs, cur_tunnels, demands, positive_demands
        del tunnel_loads

        # ---- Step 3: reordered sets (per site pair; parallelizable) ----
        analyze_start = time.time()
        if self.prev_encoded is None:
            prev_records = self._encode_assignment(
                self.assign_prev, num_endpoints)
            prev_dense = np.full(num_endpoints * num_endpoints, -1,
                                 dtype=np.int32)
            prev_dense[prev_records['pair']] = prev_records['tunnel']
        else:
            prev_records = None
            prev_dense = np.asarray(self.prev_encoded, dtype=np.int32)
        encode_previous_time = time.time() - analyze_start
        R, dcache, num_common, reordered_before = \
            self._analyze_encoded_assignments(
                prev_dense, cur_dense, num_endpoints, tm_flat)
        loss_value = sum(dcache.values())
        assignment_analysis_time = time.time() - analyze_start
        del prev_records, prev_dense
        R_by_k = defaultdict(dict)
        for (k, u, t), pairs in R.items():
            R_by_k[k][(k, u, t)] = pairs

        # ---- Steps 1-4: candidates, DeltaZ, DeltaLoad, one sort --------
        # Generate, score and DeltaZ-filter in one pass.  Work remains
        # grouped by site pair so this phase can be parallelized later.
        num_candidates = 0
        scored = []
        for k in sorted(R_by_k):
            count, site_scored = self._score_site_pair_candidates(
                k, R_by_k[k], dcache)
            num_candidates += count
            scored.extend(site_scored)
        # deterministic sort: DeltaZ desc, then canonical tunnel ids
        scored.sort(key=lambda x: (-x[0], x[1]))
        num_dz_positive = len(scored)

        # ---- Steps 5-8: commit exchanges one at a time -----------------
        # Rescan after every exchange: capacity-blocked candidates are
        # NOT deleted -- a later exchange may free the link they need.
        consumed = set()
        protected = defaultdict(set)   # H[(k, tunnel)] -> {pair}
        exchanges = 0

        while True:
            picked = None
            for _, _, c, dl in scored:
                i, j = c[3], c[4]
                if i in consumed or j in consumed:
                    continue
                if any(loads[e] + v > cap[e] + tol
                       for e, v in dl.items() if v > 0.0):
                    continue
                picked = (c, dl)
                break
            if picked is None:
                break
            (k, u, t, i, j), dl = picked
            # Step 6: both pairs restore their previous tunnels
            assign[i] = u
            assign[j] = t
            cur_dense[i[0] * num_endpoints + i[1]] = self._tunnel_id(u)
            cur_dense[j[0] * num_endpoints + j[1]] = self._tunnel_id(t)
            di = dcache[i]
            dj = dcache[j]
            weight_penalty += self.epsilon * (di - dj) * \
                (self._tunnel_weight(u) - self._tunnel_weight(t))
            loss_value -= di + dj
            for e, v in dl.items():
                loads[e] += v
            # Step 7: consumed makes every candidate touching i or j
            # ineligible; no mutable copy of the reordered sets is needed.
            consumed.update((i, j))
            protected[(k, u)].add(i)
            protected[(k, t)].add(j)
            exchanges += 1

        # ---- verification & stats --------------------------------------
        # Every mutation above only replaces the value of an existing key
        # drawn from assign_cur.  A full set equality check would allocate
        # two enormous temporary sets on large deployments.
        assert len(assign) == len(self.assign_cur), \
            'R2R must not change the number of assigned pairs'
        # R2R changes only tunnel values, never assignment keys, so carried
        # demand is invariant.  Every committed reciprocal exchange restores
        # exactly two distinct reordered pairs to their previous tunnels.
        sat_before = satisfied_demand
        sat_after = satisfied_demand
        reordered_after = reordered_before - 2 * exchanges
        assert reordered_after >= 0, 'reordered pair count became negative'
        if abs(loss_value) <= tol:
            loss_value = 0.0
        obj_val = (sat_after - weight_penalty -
                   self.loss_weight * loss_value)

        max_util = 0.0
        new_violations = []
        inherited_violations = []
        for e in initial_loads:
            c_e = self.G[e[0]][e[1]]['capacity']
            util = loads[e] / c_e
            if util > max_util:
                max_util = util
            if loads[e] > c_e + tol:
                if initial_loads[e] > c_e + tol:
                    inherited_violations.append(
                        (e, initial_loads[e], loads[e], c_e))
                else:
                    new_violations.append((e, initial_loads[e], loads[e], c_e))

        stats = {
            'reordered_before': reordered_before,
            'reordered_after': reordered_after,
            'reorder_reduction': reordered_before - reordered_after,
            'num_common_pairs': num_common,
            'num_reordered_groups': len(R),
            'num_candidates': num_candidates,
            'num_dz_positive': num_dz_positive,
            'exchanges': exchanges,
            'protected_pairs': sum(len(v) for v in protected.values()),
            'satisfied_demand': sat_after,
            'satisfied_demand_before': sat_before,
            'obj_val': obj_val,
            'weight_penalty': weight_penalty,
            'loss_value': loss_value,
            'max_link_util': max_util,
            'inherited_violations': inherited_violations,
            'new_violations': new_violations,
            'workers': self.workers,
            'encode_current_time': encode_current_time,
            'encode_previous_time': encode_previous_time,
            'load_build_time': load_build_time,
            'assignment_analysis_time': assignment_analysis_time,
            'r2r_runtime': time.time() - t_start,
        }
        self.encoded_assignment = cur_dense
        return assign, stats
