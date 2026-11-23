#!/bin/bash
set -euo pipefail

SIM_DIR=/home/zyxl/ns-3-alibabacloud/simulation
EXP_DIR=$SIM_DIR/examples/k5-rdma-te
OUT=$EXP_DIR/outputs
PYTHON=/home/zyxl/miniconda3/envs/megate/bin/python

mkdir -p "$OUT/logs"
cd "$EXP_DIR"
"$PYTHON" generate_manifest.py
sha256sum -c workload.tsv.sha256
read -r SHA _ < workload.tsv.sha256
test "${#SHA}" -eq 64

cd "$SIM_DIR"
./ns3 build K5RdmaTeNetwork

# These are generated outputs owned by this experiment.
rm -f "$OUT"/flow_stats_gurobi.csv "$OUT"/flow_stats_tse.csv \
      "$OUT"/flow_stats_megate.csv "$OUT"/flow_stats_all.csv \
      "$OUT"/experiment_summary.csv "$OUT"/all_flow_fct_summary.csv \
      "$OUT"/incomplete_flows.csv

for algorithm in gurobi tse megate; do
  for seed in 1 2 3 4 5; do
    echo "=== algorithm=$algorithm seed=$seed ==="
    ./ns3 run "scratch/K5RdmaTeNetwork $EXP_DIR/config_k5.sh --algorithm=$algorithm --seed=$seed --manifest=$EXP_DIR/workload.tsv --csv=$OUT/flow_stats_${algorithm}.csv --workloadSha=$SHA" \
      2>&1 | tee "$OUT/logs/${algorithm}_seed${seed}.log"
    cp "$OUT/common_pfc_k5.txt" "$OUT/logs/pfc_${algorithm}_seed${seed}.txt"
  done
done

"$PYTHON" "$EXP_DIR/aggregate_results.py"
"$PYTHON" "$EXP_DIR/plot_results.py" "$OUT/flow_stats_all.csv" --out-dir "$OUT"
