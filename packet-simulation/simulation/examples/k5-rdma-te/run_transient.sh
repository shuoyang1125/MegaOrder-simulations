#!/bin/bash
set -euo pipefail

if [ "$#" -lt 3 ] || [ "$#" -gt 4 ]; then
  echo "usage: $0 EPOCH_MS TE_UPDATE_MS START_MIN_MS [START_MAX_MS]" >&2
  exit 2
fi

EPOCH_MS=$1
TE_UPDATE_MS=$2
START_MIN_MS=$3
START_MAX_MS=${4:-$START_MIN_MS}
TAG=epoch${EPOCH_MS}ms_update${TE_UPDATE_MS}ms_start${START_MIN_MS}-${START_MAX_MS}ms
TAG=${TAG//./p}
SIM_DIR=/home/zyxl/ns-3-alibabacloud/simulation
EXP_DIR=$SIM_DIR/examples/k5-rdma-te
OUT=$EXP_DIR/outputs_$TAG
WORK_DIR=$EXP_DIR/workloads/$TAG
MANIFEST=$WORK_DIR/workload.tsv
PYTHON=/home/zyxl/miniconda3/envs/megate/bin/python

mkdir -p "$OUT/logs" "$WORK_DIR"
cd "$EXP_DIR"
"$PYTHON" generate_manifest.py --epoch-ms "$EPOCH_MS" \
  --start-ms-min "$START_MIN_MS" --start-ms-max "$START_MAX_MS" \
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
    echo "=== $TAG algorithm=$algorithm seed=$seed ==="
    ./ns3 run "scratch/K5RdmaTeNetwork $EXP_DIR/config_k5.sh --algorithm=$algorithm --seed=$seed --teUpdateMs=$TE_UPDATE_MS --manifest=$MANIFEST --csv=$OUT/flow_stats_${algorithm}.csv --workloadSha=$SHA" \
      2>&1 | tee "$OUT/logs/${algorithm}_seed${seed}.log"
    cp "$EXP_DIR/outputs/common_pfc_k5.txt" "$OUT/logs/pfc_${algorithm}_seed${seed}.txt"
  done
done

"$PYTHON" "$EXP_DIR/aggregate_results.py" --out-dir "$OUT" --manifest "$MANIFEST"
"$PYTHON" "$EXP_DIR/plot_results.py" "$OUT/flow_stats_all.csv" --out-dir "$OUT" \
  --smooth-fct --cdf-bandwidth-ms 0.2
