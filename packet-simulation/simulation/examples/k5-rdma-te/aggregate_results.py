#!/usr/bin/env python3
"""Validate raw algorithm CSVs and create combined/summary tables."""

import csv
import argparse
import hashlib
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ALGORITHMS = ("gurobi", "tse", "megate")
SEEDS = (1, 2, 3, 4, 5)

parser = argparse.ArgumentParser()
parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs")
parser.add_argument("--manifest", type=Path, default=ROOT / "workload.tsv")
args = parser.parse_args()
OUT = args.out_dir
with args.manifest.open() as handle:
    manifest_rows = list(csv.DictReader(handle, delimiter="\t"))
EXPECTED_FLOWS = len(manifest_rows)
EXPECTED_MEASURED = sum(row["measurement"] == "1" for row in manifest_rows)
EXPECTED_TOTAL_PAYLOAD = sum(int(row["payload_size_bytes"]) for row in manifest_rows)
EXPECTED_SHA = hashlib.sha256(args.manifest.read_bytes()).hexdigest()


all_rows = []
workload_reference_by_seed = {}
for algorithm in ALGORITHMS:
    path = OUT / f"flow_stats_{algorithm}.csv"
    with path.open() as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == EXPECTED_FLOWS * len(SEEDS), (algorithm, len(rows))
    for seed in SEEDS:
        run = [r for r in rows if int(r["seed"]) == seed]
        assert len(run) == EXPECTED_FLOWS
        assert sum(r["measurement"] == "1" for r in run) == EXPECTED_MEASURED
        assert {r["workload_sha256"] for r in run} == {EXPECTED_SHA}
        workload = {
            int(r["flow_id"]): (
                int(r["pair_id"]), int(r["src"]), int(r["dst"]),
                r["demand_mbps"], int(r["payload_size_bytes"]),
                r["start_time_ms"],
            )
            for r in run
        }
        assert sum(value[4] for value in workload.values()) == EXPECTED_TOTAL_PAYLOAD
        if seed not in workload_reference_by_seed:
            workload_reference_by_seed[seed] = workload
        else:
            assert workload == workload_reference_by_seed[seed], (algorithm, seed)
    all_rows.extend(rows)

fieldnames = list(all_rows[0])
with (OUT / "flow_stats_all.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(all_rows)

summary_fields = [
    "algorithm", "seed", "measurement_flows", "completed_flows",
    "incomplete_flows", "measurement_payload_bytes",
    "total_reordered_packets", "total_retransmitted_packets",
    "mean_fct_ms", "max_fct_ms", "all_flows", "all_completed_flows",
    "all_incomplete_flows", "all_payload_bytes", "all_mean_fct_ms",
    "all_median_fct_ms", "all_max_fct_ms", "workload_sha256",
]
summaries = []
payload_reference = None
for algorithm in ALGORITHMS:
    for seed in SEEDS:
        measured = [
            row for row in all_rows
            if row["algorithm"] == algorithm and int(row["seed"]) == seed
            and row["measurement"] == "1"
        ]
        completed = [row for row in measured if row["completed"] == "1"]
        run = [
            row for row in all_rows
            if row["algorithm"] == algorithm and int(row["seed"]) == seed
        ]
        all_completed = [row for row in run if row["completed"] == "1"]
        payload = sum(int(row["payload_size_bytes"]) for row in measured)
        payload_reference = payload if payload_reference is None else payload_reference
        assert payload == payload_reference
        fcts = [float(row["fct_ms"]) for row in completed]
        all_fcts = [float(row["fct_ms"]) for row in all_completed]
        summaries.append({
            "algorithm": algorithm,
            "seed": seed,
            "measurement_flows": len(measured),
            "completed_flows": len(completed),
            "incomplete_flows": len(measured) - len(completed),
            "measurement_payload_bytes": payload,
            "total_reordered_packets": sum(int(r["reordered_packets"]) for r in measured),
            "total_retransmitted_packets": sum(int(r["retransmitted_packets"]) for r in measured),
            "mean_fct_ms": f"{sum(fcts) / len(fcts):.9f}" if fcts else "",
            "max_fct_ms": f"{max(fcts):.9f}" if fcts else "",
            "all_flows": len(run),
            "all_completed_flows": len(all_completed),
            "all_incomplete_flows": len(run) - len(all_completed),
            "all_payload_bytes": sum(int(row["payload_size_bytes"]) for row in run),
            "all_mean_fct_ms": f"{statistics.mean(all_fcts):.9f}" if all_fcts else "",
            "all_median_fct_ms": f"{statistics.median(all_fcts):.9f}" if all_fcts else "",
            "all_max_fct_ms": f"{max(all_fcts):.9f}" if all_fcts else "",
            "workload_sha256": EXPECTED_SHA,
        })

with (OUT / "experiment_summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=summary_fields)
    writer.writeheader()
    writer.writerows(summaries)

incomplete = [r for r in all_rows if r["completed"] != "1"]
with (OUT / "incomplete_flows.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(incomplete)

algorithm_summary_fields = [
    "algorithm", "flows", "completed_flows", "incomplete_flows",
    "mean_fct_ms", "median_fct_ms", "min_fct_ms", "max_fct_ms",
]
algorithm_summaries = []
for algorithm in ALGORITHMS:
    rows = [row for row in all_rows if row["algorithm"] == algorithm]
    completed = [row for row in rows if row["completed"] == "1"]
    fcts = [float(row["fct_ms"]) for row in completed]
    algorithm_summaries.append({
        "algorithm": algorithm,
        "flows": len(rows),
        "completed_flows": len(completed),
        "incomplete_flows": len(rows) - len(completed),
        "mean_fct_ms": f"{statistics.mean(fcts):.9f}" if fcts else "",
        "median_fct_ms": f"{statistics.median(fcts):.9f}" if fcts else "",
        "min_fct_ms": f"{min(fcts):.9f}" if fcts else "",
        "max_fct_ms": f"{max(fcts):.9f}" if fcts else "",
    })
with (OUT / "all_flow_fct_summary.csv").open("w", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=algorithm_summary_fields)
    writer.writeheader()
    writer.writerows(algorithm_summaries)

print(f"validated {len(all_rows)} rows; measurement payload/run={payload_reference}")
print(f"incomplete all-flow rows={len(incomplete)}")
print(f"wrote {OUT / 'flow_stats_all.csv'}")
print(f"wrote {OUT / 'experiment_summary.csv'}")
print(f"wrote {OUT / 'all_flow_fct_summary.csv'}")
