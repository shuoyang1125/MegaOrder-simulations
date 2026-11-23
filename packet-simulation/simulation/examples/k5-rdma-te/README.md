# K5 RDMA TE reconfiguration experiment

This directory contains the reproducible K5, 10-endpoints-per-site experiment.
It reads existing MegaTE artifacts without invoking or modifying a TE solver,
generates one shared workload manifest, runs ns-3 for Gurobi, MegaOrder(TSE), and MegaTE
with seeds 1--5, validates the raw flow records, and creates both paper figures.

Run from `simulation/`:

```bash
bash examples/k5-rdma-te/run_all.sh
```

For a separate flow-epoch sensitivity run without overwriting the 500 ms
results, pass the epoch in milliseconds, for example:

```bash
bash examples/k5-rdma-te/run_epoch.sh 200
```

This writes to `outputs_epoch200ms/` and stores its manifest under
`workloads/epoch200ms/`.

For synchronized short-flow transient experiments, provide epoch, TE-update,
and start time in milliseconds. For example, all flows start at 10 ms and TE
updates before their first packet can traverse a 1 ms site path:

```bash
bash examples/k5-rdma-te/run_transient.sh 10 11.5 10 10.1
```

Transient runs use a 0.2 ms Gaussian-kernel smoothed FCT CDF for the paper
figures; the raw per-flow FCT values remain unchanged in the CSV files.

## Fixed experiment semantics

- `generate_manifest.py` reads Old routing from seed 1000 and the three new
  routings plus the srv-srv TM2 from seed 2000 in `/home/zyxl/MegaTE-main`.
- Each of the 1,981 Old-admitted `(src,dst)` pairs gets one constant-rate flow.
- Payload bytes are
  `ceil_to_1024(TM2_demand_mbps * 1e6 / 8 * 0.5)` and QP wire rate is
  `TM2_demand_mbps * 1076 / 1024`.
- The 52 Old-to-MegaTE changed pairs are the common measurement set. The
  expected changed counts within that set are Gurobi 0, MegaOrder(TSE) 24, MegaTE 52.
- Site links are 1 Gbit/s with 1 ms one-way delay. Endpoint links are
  100 Gbit/s with 1 us one-way delay. TE updates once at 100 ms.
- The shared manifest hash, payload equality, 52-flow measurement set, all
  five seeds, completion state, and row counts are checked before aggregation.

`workload.tsv` is the immutable input to all algorithm runs. Its SHA-256 is in
`workload.tsv.sha256`; `run_all.sh` verifies and then passes that exact digest
to every ns-3 run. A missing Gurobi route retains the Old tunnel and is marked
in the per-flow CSV.

## Outputs

Raw and combined flow records, `experiment_summary.csv`, and
`incomplete_flows.csv` are in `outputs/`. `all_flow_fct_summary.csv` reports
mean/median/min/max FCT over all 1,981 flows and all five seeds per algorithm.
The requested figures are:

- `outputs/rdma_retransmissions.pdf` and `.png`
- `outputs/fct_cdf.pdf` and `.png`
- `outputs/fct_cdf_all_flows.pdf` and `.png` (all 1,981 flows)

Run logs and per-run PFC traces are retained under `outputs/logs/`.
