#!/bin/bash
# Full TE-reconfiguration reordering experiment:
# run the simulation for N in {10, 30, 50, 70, 90} and append one CSV row per run.
set -e

SIM_DIR=/home/zyxl/ns-3-alibabacloud/simulation
EXP_DIR=$SIM_DIR/examples/te-reorder
OUT=$EXP_DIR/outputs
CSV=$OUT/experiment_summary.csv

mkdir -p "$OUT"
rm -f "$CSV"

cd "$SIM_DIR"
for N in 10 30 50 70 90; do
  echo "=== N_reassigned = $N ==="
  ./ns3 run "scratch/TeReorderNetwork $EXP_DIR/config_te_reorder.sh --Nreassigned=$N --seed=1 --csv=$CSV"
done

echo
echo "=== experiment_summary.csv ==="
cat "$CSV"
