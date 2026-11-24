# Packet-level simulation

This directory contains the Alibaba Cloud ns-3.36.1 simulator and the K5 RDMA
packet-level experiment. Algorithm-level results, generated workloads, and
experiment outputs are not stored in Git.

Run the following steps for the K5 experiment with 10 endpoints per site.

## 1. Prepare the algorithm-level inputs

First follow [`../algorithm-simulation/README.md`](../algorithm-simulation/README.md)
to create the `megate` environment and generate the K5 Old, MegaTE, MegaOrder,
and Gurobi routes, the server-to-site mapping, and the endpoint-level TM2.

The packet simulator only reads these saved files; it does not rerun a TE
solver. In
`simulation/examples/k5-rdma-te/generate_manifest.py`, set `--megate-root` to
the directory that contains `benchmarks/`, `traffic-matrices/`, and
`topologies/`:

```python
parser.add_argument("--megate-root", type=Path,
                    default=Path("/root/MegaTE-main"))
```

For a self-contained packaged setup, replace the value with the absolute path
to `../algorithm-simulation/` after generating its input and result files.

## 2. Configure local paths

In `simulation/examples/k5-rdma-te/run_transient.sh`, set:

```bash
SIM_DIR=/root/ns-3-alibabacloud/simulation
PYTHON=/root/miniconda3/envs/megate/bin/python
```

`run_transient.sh` passes `$EXP_DIR/config_k5.sh` to `K5RdmaTeNetwork` for every
algorithm and seed. The program reads this file through `ReadConf(...)`; it
provides the topology path, output paths, simulation timeout, buffer settings,
and RDMA parameters. Therefore, its absolute paths must use the same
`$SIM_DIR/examples/k5-rdma-te` directory.

To reproduce the historical synchronized-run directory name, use the following
tag assignments in `run_transient.sh`:

```bash
TAG=epoch${EPOCH_MS}ms_update${TE_UPDATE_MS}ms_start${START_MIN_MS}ms
TAG=${TAG//./p}
```

## 3. Build with MTP support

```bash
cd /root/ns-3-alibabacloud/simulation
./ns3 configure -d default --enable-mtp --disable-examples
./ns3 build K5RdmaTeNetwork
```

## 4. Run the experiment

```bash
conda activate megate
cd /root/ns-3-alibabacloud/simulation
bash examples/k5-rdma-te/run_transient.sh 10 11.5 10
```

This configuration uses a 10-ms payload epoch, performs one TE update at
11.5 ms, and starts every flow at exactly 10 ms. The script runs Gurobi,
MegaOrder (internal key `tse`) and MegaTE, then aggregates the
CSV files and generates the figures.

## 5. Check the outputs

Results are written to:

```text
/root/ns-3-alibabacloud/simulation/examples/k5-rdma-te/
  outputs_epoch10ms_update11p5ms_start10ms/
```

The directory contains the per-flow CSV files, `experiment_summary.csv`,
`all_flow_fct_summary.csv`, logs, and the retransmission, reordered-pair, and
FCT figures in PDF and PNG formats. The shared workload manifest and checksum
are stored under `workloads/epoch10ms_update11p5ms_start10ms/`.
