# Algorithm-level simulation

This directory contains the MegaTE algorithm-level simulator and
MegaOrder(TSE). Topologies, traffic matrices, logs, and generated results are
not stored in Git.

Run the following commands from `algorithm-simulation/`.

## 1. Create the environment

```bash
conda env create -f environment.yml
conda activate megate
```

A valid Gurobi installation and license are required.

## 2. Download site-level inputs

Run [`download.sh`](download.sh) to download the site-level traffic matrices,
topologies, and precomputed paths:

```bash
bash download.sh
```

## 3. Generate server-level inputs

Configure [`generate_server_data.sh`](generate_server_data.sh) for the required
topology and server count, then generate the server-level topology, paths,
mapping, and traffic matrices. After that, run
[`gen_noise_tms.sh`](benchmarks/gen_noise_tms.sh) to generate the `generic`
noise-chain traffic matrices:

```bash
bash generate_server_data.sh
bash benchmarks/gen_noise_tms.sh 10 Uninett2010.graphml
```

## 4. Run the experiments

### MegaTE

```bash
cd benchmarks

python Run_all.py --algo mega --server 10 \
  --problem Uninett2010.graphml --slices 0 1 \
  --epsilon 0.1 --lambda 1
```

### MegaOrder

```bash
python tse.py --server 10 \
  --problem Uninett2010.graphml --slices 0 1 \
  --tm-model generic --epsilon 0.1 --lambda 1
```

### Gurobi

```bash
python exact.py --server 10 \
  --problem Uninett2010.graphml --slices 0 1 \
  --tm-model generic --epsilon 0.1 --lambda 1
```

