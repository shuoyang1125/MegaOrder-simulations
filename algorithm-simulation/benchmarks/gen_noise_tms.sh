#!/bin/bash
# Generate noise-chain generic TMs for every topology that has stock
# uniform site TMs in ../traffic-matrices/site-traffic-matrices/uniform.
#
# Per stock TM (sorted), one noise pair is generated via
# tse_noise_chain.py --dump-only:
#   pair i (i = 0, 1, 2, ...) uses noise seeds a = 1000+2000i and
#   b = 2000+2000i  (i.e. seeds run 1000, 2000, 3000, ... in steps of
#   1000), both derived from the SAME stock TM so site-pair totals are
#   identical (noise-chain property: shared site LP).
# Each pair writes 2 identical-content site TMs (generic dir) and 2 srv
# TMs (srv-traffic-matrices-<server>/generic dir).
#
# Usage (run directory is forced to benchmarks/):
#   ./gen_noise_tms.sh [server_per_site] [topology]
#     server_per_site  default 10 (needs topologies/server2site-<server>/)
#     topology         optional filter, e.g. Uninett2010.graphml
#
# Existing pairs (both site TMs already on disk) are skipped, so the
# script is idempotent. NOTE: --slices indices into the generic group
# follow LEXICOGRAPHIC filename order; the summary printed at the end of
# each topology maps every pair to its current slice indices.

set -u
PYTHON=/home/zyxl/miniconda3/envs/megate/bin/python
SERVER="${1:-10}"
TOPO_FILTER="${2:-}"
cd "$(dirname "$0")"

UNIFORM_DIR=../traffic-matrices/site-traffic-matrices/uniform
GENERIC_SITE_DIR=../traffic-matrices/site-traffic-matrices/generic

[ -d "$UNIFORM_DIR" ] || { echo "uniform site TM dir not found: $UNIFORM_DIR"; exit 1; }

topos=$(ls "$UNIFORM_DIR" | grep '_traffic-matrix\.pkl$' \
    | sed -E 's/_uniform_.*$//' | sort -u)

for topo in $topos; do
    if [ -n "$TOPO_FILTER" ] && [ "$topo" != "$TOPO_FILTER" ]; then
        continue
    fi
    if [ ! -f "../topologies/site_topologies/${topo}" ]; then
        echo "=== SKIP ${topo}: no site topology file ==="
        continue
    fi
    if [ ! -f "../topologies/server2site-${SERVER}/${topo}_server2site.pkl" ]; then
        echo "=== SKIP ${topo}: no server2site-${SERVER} table ==="
        continue
    fi

    stocks=($(ls "$UNIFORM_DIR" | grep "^${topo}_uniform_" | sort))
    n=${#stocks[@]}
    echo "=== ${topo}: ${n} stock uniform TMs -> ${n} noise pairs (seeds 1000 .. $((1000 * 2 * n))) ==="

    i=0
    for stock in "${stocks[@]}"; do
        # filename: {topo}_uniform_{seed}_{scale}_{param}_traffic-matrix.pkl
        base_seed=$(echo "$stock" | cut -d'_' -f3)
        a=$((1000 + 2000 * i))
        b=$((2000 + 2000 * i))
        # site TM seeds are zero-padded (6 digits) so the generic group's
        # lexicographic sort equals numeric order; srv TM seeds are NOT
        # padded (SSP_MAIN/EXACT_MAIN/tse.py rebuild the name via str(int))
        site_a="${GENERIC_SITE_DIR}/${topo}_generic_$(printf '%06d' $a)_1.0_noise_traffic-matrix.pkl"
        site_b="${GENERIC_SITE_DIR}/${topo}_generic_$(printf '%06d' $b)_1.0_noise_traffic-matrix.pkl"
        srv_a="../traffic-matrices/srv-traffic-matrices-${SERVER}/generic/${topo}_generic_${a}_1.0_noise_traffic-matrix.pkl"
        srv_b="../traffic-matrices/srv-traffic-matrices-${SERVER}/generic/${topo}_generic_${b}_1.0_noise_traffic-matrix.pkl"
        if [ -f "$site_a" ] && [ -f "$site_b" ] && [ -f "$srv_a" ] && [ -f "$srv_b" ]; then
            echo "  pair ${i} (seeds ${a}/${b}): already exists, skip"
            i=$((i + 1))
            continue
        fi
        echo "  pair ${i}: base=${stock} -> noise seeds ${a}, ${b}"
        $PYTHON tse_noise_chain.py --problem "$topo" --server "$SERVER" \
            --dump-only --tm-seed "$base_seed" \
            --noise-seed-a "$a" --noise-seed-b "$b" \
            > /dev/null 2>&1 \
            || echo "  FAILED pair ${i} (seeds ${a}/${b}) for ${topo}"
        i=$((i + 1))
    done

    # slice-index map of the generic group (lexicographic filename order)
    files=($(ls "$GENERIC_SITE_DIR" 2>/dev/null | grep "^${topo}_generic_" | sort))
    if [ ${#files[@]} -gt 0 ]; then
        echo "  --- ${topo}: generic group slice map (run --dry-run to confirm) ---"
        idx_of() {
            local want
            want=$(printf '%06d' "$1")
            for idx in "${!files[@]}"; do
                if [ "${files[$idx]}" = "${topo}_generic_${want}_1.0_noise_traffic-matrix.pkl" ]; then
                    echo "$idx"
                    return
                fi
            done
            echo "?"
        }
        for p in $(seq 0 $((n - 1))); do
            a=$((1000 + 2000 * p))
            b=$((2000 + 2000 * p))
            echo "    pair ${p} (base #${p}, seeds ${a}/${b}) -> slices $(idx_of $a) $(idx_of $b)"
        done
    fi
done
