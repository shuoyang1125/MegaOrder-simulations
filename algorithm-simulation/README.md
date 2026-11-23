# Algorithm-level simulation

This directory contains the MegaTE algorithm-level simulator, TSE baselines,
exact and LP formulations, input-generation utilities, plotting scripts, and
batch experiment drivers.

Large topologies, traffic matrices, solver outputs, CSV results, plots, and
logs are deliberately not included.

## Environment

Create the Conda environment from the tracked environment definition:

```bash
conda env create -f environment.yml
conda activate megate
```

The environment definition reflects the original experimental setup, including
Python 3.6 and Gurobi 8.1.1. A valid Gurobi installation and license are required
for the exact and Gurobi-backed formulations.

## Local input layout

Place locally obtained or generated inputs in the following ignored paths:

```text
algorithm-simulation/
|-- topologies/
`-- traffic-matrices/
```

The benchmark programs are normally launched from `benchmarks/` and resolve
those directories through relative paths. Input generators are available under
`scripts/`, and `download.sh` documents the original data-download workflow.
Do not commit the resulting data archives or extracted datasets.

## Running experiments

From `algorithm-simulation/benchmarks`:

```bash
python Run_all.py --algo mega --server 100 \
  --problem UsCarrier.graphml --slices 10 11 --epsilon 0.1 --lambda 1

python tse.py --server 100 --problem UsCarrier.graphml \
  --slices 10 11 --tm-model generic --epsilon 0.1 --lambda 1
```

`run_mega_batch.sh` and `run_tse_batch.sh` are experiment-specific batch
drivers. Review their local paths and environment settings before reuse on a
different machine.

## Outputs

Benchmark CSV files, solution dictionaries, logs, generated plots, and other
runtime artifacts are ignored by Git. Keep reproducibility metadata in prose or
scripts rather than committing generated result files.

