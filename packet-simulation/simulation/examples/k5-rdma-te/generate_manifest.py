#!/usr/bin/env python3
"""Build the immutable K5/10-endpoint RDMA workload from saved MegaTE output.

This script is deliberately a converter only: it never invokes a TE solver and
never writes into MegaTE-main.  All three ns-3 algorithms consume the same TSV.
"""

import argparse
import csv
import hashlib
import math
import pickle
import random
from pathlib import Path


MTU = 1024
WIRE_BYTES = 1076
DEFAULT_EPOCH_SECONDS = 0.5
N_ENDPOINT_IDS = 55
SEEDS = (1, 2, 3, 4, 5)


def load_pickle(path):
    with path.open("rb") as handle:
        return pickle.load(handle)


def tunnel(path):
    """Return the site-only tunnel as a comma-separated string."""
    return ",".join(str(node) for node in path[1:-1])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--megate-root", type=Path,
                        default=Path("/home/zyxl/MegaTE-main"))
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).resolve().parent / "workload.tsv")
    parser.add_argument("--topology", type=Path,
                        default=Path(__file__).resolve().parent / "topology.txt")
    parser.add_argument("--epoch-seconds", type=float,
                        default=DEFAULT_EPOCH_SECONDS,
                        help="nominal payload transmission duration")
    parser.add_argument("--epoch-ms", type=int,
                        help="duration in milliseconds; overrides --epoch-seconds")
    parser.add_argument("--start-ms-min", type=float, default=10.0)
    parser.add_argument("--start-ms-max", type=float, default=15.0)
    args = parser.parse_args()
    if args.epoch_ms is not None:
        args.epoch_seconds = args.epoch_ms / 1000.0
    if args.epoch_seconds <= 0:
        parser.error("--epoch-seconds must be positive")
    if args.start_ms_min < 0 or args.start_ms_max < args.start_ms_min:
        parser.error("invalid start-time interval")
    root = args.megate_root

    old_path = root / "benchmarks/Mega-logs/K5.graphml/1000-generic/10-per_site/K5.graphml-10-ssp_solution.pkl"
    mega_path = root / "benchmarks/Mega-logs/K5.graphml/2000-generic/10-per_site/K5.graphml-10-ssp_solution.pkl"
    tse_path = root / "benchmarks/TSE-logs/K5.graphml/2000-generic/10-per_site/K5.graphml-10-tse_solution.pkl"
    exact_path = root / "benchmarks/Exact-logs/K5.graphml/2000-generic/10-per_site/K5.graphml-10-exact_solution.pkl"
    tm_path = root / "traffic-matrices/srv-traffic-matrices-10/generic/K5.graphml_generic_2000_1.0_noise_traffic-matrix.pkl"
    ref_path = root / "topologies/server2site-10/K5.graphml_server2site.pkl"

    old = load_pickle(old_path)
    mega = load_pickle(mega_path)
    tse = load_pickle(tse_path)["ssp_out"]
    exact = load_pickle(exact_path)["ssp_out"]
    tm2 = load_pickle(tm_path)
    ref = load_pickle(ref_path)

    assert tm2.shape == (N_ENDPOINT_IDS, N_ENDPOINT_IDS)
    assert len(ref) == N_ENDPOINT_IDS
    assert len(old) == 1981
    assert set(mega) == set(tse)

    measured = {
        pair for pair in old
        if pair in mega and tuple(old[pair][1:-1]) != tuple(mega[pair][1:-1])
    }
    assert len(measured) == 52

    changed = {}
    for name, routes in (("megate", mega), ("tse", tse), ("gurobi", exact)):
        changed[name] = sum(
            pair in routes and tuple(old[pair][1:-1]) != tuple(routes[pair][1:-1])
            for pair in measured
        )
    assert changed == {"megate": 52, "tse": 24, "gurobi": 0}, changed

    gateways = [index for index, site in enumerate(ref) if site == -1]
    assert gateways == [0, 11, 22, 33, 44]
    links = []
    for endpoint, site in enumerate(ref):
        if site != -1:
            links.append((endpoint, gateways[int(site)], "100Gbps", "1us", 0))
    for left in range(len(gateways)):
        for right in range(left + 1, len(gateways)):
            links.append((gateways[left], gateways[right], "1Gbps", "1ms", 0))
    args.topology.parent.mkdir(parents=True, exist_ok=True)
    with args.topology.open("w") as handle:
        print(f"55 1 0 5 {len(links)} X000 8", file=handle)
        print(" ".join(str(node) for node in gateways), file=handle)
        for link in links:
            print(*link, file=handle)

    # One deterministic start-time vector per seed, reused by every algorithm.
    starts = {}
    ordered_pairs = sorted(old)
    for seed in SEEDS:
        rng = random.Random(seed)
        width = args.start_ms_max - args.start_ms_min
        starts[seed] = [
            args.start_ms_min + width * rng.random() for _ in ordered_pairs
        ]

    fields = [
        "flow_id", "pair_id", "src", "dst", "measurement",
        "demand_mbps", "wire_rate_bps", "payload_size_bytes",
        "old_tunnel", "gurobi_tunnel", "gurobi_missing",
        "tse_tunnel", "tse_missing", "megate_tunnel", "megate_missing",
    ] + [f"start_ms_seed{seed}" for seed in SEEDS]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        for flow_id, pair in enumerate(ordered_pairs):
            src, dst = pair
            demand = float(tm2[src, dst])
            assert demand > 0.0
            payload = int(math.ceil(
                (demand * 1e6 / 8 * args.epoch_seconds) / MTU) * MTU)
            wire_rate = int(round(demand * 1e6 * WIRE_BYTES / MTU))
            row = {
                "flow_id": flow_id,
                "pair_id": src * N_ENDPOINT_IDS + dst,
                "src": src,
                "dst": dst,
                "measurement": int(pair in measured),
                "demand_mbps": f"{demand:.12f}",
                "wire_rate_bps": wire_rate,
                "payload_size_bytes": payload,
                "old_tunnel": tunnel(old[pair]),
            }
            for name, routes in (("gurobi", exact), ("tse", tse), ("megate", mega)):
                missing = pair not in routes
                chosen = old[pair] if missing else routes[pair]
                row[f"{name}_tunnel"] = tunnel(chosen)
                row[f"{name}_missing"] = int(missing)
            for seed in SEEDS:
                row[f"start_ms_seed{seed}"] = f"{starts[seed][flow_id]:.9f}"
            writer.writerow(row)

    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    checksum_path = args.output.with_suffix(args.output.suffix + ".sha256")
    checksum_path.write_text(f"{digest}  {args.output.name}\n")

    total_payload = 0
    measured_payload = 0
    with args.output.open() as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            size = int(row["payload_size_bytes"])
            total_payload += size
            if row["measurement"] == "1":
                measured_payload += size
    print(f"wrote {args.output}")
    print(f"wrote {args.topology}")
    print(f"sha256={digest}")
    print(f"epoch_seconds={args.epoch_seconds}")
    print(f"start_ms=[{args.start_ms_min}, {args.start_ms_max}]")
    print(f"flows={len(old)} measured={len(measured)} changes={changed}")
    print(f"payload_bytes total={total_payload} measured={measured_payload}")


if __name__ == "__main__":
    main()
