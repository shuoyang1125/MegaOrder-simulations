#!/bin/bash
set -euo pipefail

if [ "$#" -ne 1 ]; then
  echo "usage: $0 EPOCH_MS" >&2
  exit 2
fi

EPOCH_MS=$1
case "$EPOCH_MS" in
  ''|*[!0-9]*) echo "EPOCH_MS must be a positive integer" >&2; exit 2 ;;
esac
if [ "$EPOCH_MS" -le 0 ]; then
  echo "EPOCH_MS must be positive" >&2
  exit 2
fi

SIM_DIR=/home/zyxl/ns-3-alibabacloud/simulation
EXP_DIR=$SIM_DIR/examples/k5-rdma-te
OUT=$EXP_DIR/outputs_epoch${EPOCH_MS}ms
WORK_DIR=$EXP_DIR/workloads/epoch${EPOCH_MS}ms
MANIFEST=$WORK_DIR/workload.tsv
PYTHON=/home/zyxl/miniconda3/envs/megate/bin/python

mkdir -p "$OUT/logs" "$WORK_DIR"
cd "$EXP_DIR"
"$PYTHON" generate_manifest.py --epoch-ms "$EPOCH_MS" \
  --output "$MANIFEST" --topology "$EXP_DIR/topology.txt"
cd "$WORK_DIR"
sha256sum -c workload.tsv.sha256
read -r SHA _ < workload.tsv.sha256
test "${#SHA}" -eq 64

cd "$SIM_DIR"
./ns3 build K5RdmaTeNetwork
rm -f "$OUT"/flow_stats_gurobi.csv "$OUT"/flow_stats_tse.csv \
      "$OUT"/flow_stats_megate.csv "$OUT"/flow_stats_all.csv \
      "$OUT"/experiment_summary.csv "$OUT"/all_flow_fct_summary.csv \
      "$OUT"/incomplete_flows.csv

for algorithm in gurobi tse megate; do
  for seed in 1 2 3 4 5; do
    echo "=== epoch_ms=$EPOCH_MS algorithm=$algorithm seed=$seed ==="
    ./ns3 run "scratch/K5RdmaTeNetwork $EXP_DIR/config_k5.sh --algorithm=$algorithm --seed=$seed --manifest=$MANIFEST --csv=$OUT/flow_stats_${algorithm}.csv --workloadSha=$SHA" \
      2>&1 | tee "$OUT/logs/${algorithm}_seed${seed}.log"
    cp "$EXP_DIR/outputs/common_pfc_k5.txt" "$OUT/logs/pfc_${algorithm}_seed${seed}.txt"
  done
done

"$PYTHON" "$EXP_DIR/aggregate_results.py" --out-dir "$OUT" --manifest "$MANIFEST"
"$PYTHON" "$EXP_DIR/plot_results.py" "$OUT/flow_stats_all.csv" --out-dir "$OUT"
