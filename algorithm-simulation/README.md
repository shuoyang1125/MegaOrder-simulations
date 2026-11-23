# Algorithm-level simulation

This directory contains the MegaTE algorithm-level simulator,
MegaOrder(TSE), exact and LP formulations, and the utilities used to prepare
their inputs.

Topologies, traffic matrices, solver outputs, CSV results, and logs are not
stored in Git. The following procedure starts with no local topology or traffic
matrix data and prepares the exact inputs needed by the example commands.

## 1. Create the environment

Run these commands from `algorithm-simulation/`:

```bash
conda env create -f environment.yml
conda activate megate
```

The environment file records the original experimental setup, including
Python 3.6 and Gurobi 8.1.1. A valid Gurobi installation and license are
required.

## 2. Download the UsCarrier topology

Create the expected directory and download the GraphML file from the Internet
Topology Zoo long-term data repository:

```bash
mkdir -p topologies/site_topologies
curl -L \
  https://raw.githubusercontent.com/mroughan/InternetTopologyZoo/main/graphml/UsCarrier.graphml \
  -o topologies/site_topologies/UsCarrier.graphml
```

## 3. Download the base traffic matrices and precomputed paths

`download.sh` retrieves the original MegaTE traffic-matrix archive and
precomputed site paths. Run it from `algorithm-simulation/`:

```bash
bash download.sh
```

Before continuing, verify that the topology, the four-path site dictionary,
and at least one uniform UsCarrier site TM exist:

```bash
test -f topologies/site_topologies/UsCarrier.graphml
test -f topologies/paths/site-paths/UsCarrier.graphml-4-paths_edge-disjoint-True_dist-metric-inv-cap-dict.pkl
find traffic-matrices/site-traffic-matrices/uniform \
  -name 'UsCarrier.graphml_uniform_*_traffic-matrix.pkl' -print -quit
```

The final `find` command must print a filename. Do not proceed if any of these
checks fail.

## 4. Generate the 100-endpoints-per-site mapping

The server-path generator creates the server-level topology, expanded paths,
and the `server2site-100` mapping required by MegaTE and MegaOrder(TSE):

```bash
cd scripts
python generate_srv_path.py --topo UsCarrier.graphml --server 100
cd ..

test -f topologies/server2site-100/UsCarrier.graphml_server2site.pkl
```

This step can take a long time and writes large ignored files under
`topologies/`.

## 5. Generate 12 generic traffic matrices

The requested slices are zero-based indices 10 and 11, so a clean setup needs
at least 12 sorted `generic` site TMs and their matching server-level TMs. The
following loop creates six deterministic two-TM chains. Run it from
`algorithm-simulation/benchmarks/`:

```bash
cd benchmarks

for seeds in \
  '1000 2000' \
  '3000 4000' \
  '5000 6000' \
  '7000 8000' \
  '9000 10000' \
  '11000 12000'
do
  set -- $seeds
  python tse_noise_chain.py \
    --problem UsCarrier.graphml \
    --server 100 \
    --tm-model uniform \
    --noise-seed-a "$1" \
    --noise-seed-b "$2" \
    --dump-model generic \
    --dump-only
done
```

The first invocation also creates the four intersecting site paths used by
MegaTE and MegaOrder(TSE). Confirm the final ordering before running an
experiment:

```bash
find ../traffic-matrices/site-traffic-matrices/generic \
  -name 'UsCarrier.graphml_generic_*_traffic-matrix.pkl' \
  -printf '%f\n' | sort | nl -v 0
```

In a clean setup, indices 10 and 11 must correspond to seeds 11000 and 12000.
If the directory already contains other generic TMs, the slice indices may
refer to different files; inspect the listing instead of assuming the order.

## 6. Validate input discovery

Still in `algorithm-simulation/benchmarks/`, verify the two commands resolve
the intended inputs without starting the experiments:

```bash
python Run_all.py --algo mega --server 100 \
  --problem UsCarrier.graphml --slices 10 11 \
  --epsilon 0.1 --lambda 1 --dry-run

python tse.py --server 100 --problem UsCarrier.graphml \
  --slices 10 11 --tm-model generic \
  --epsilon 0.1 --lambda 1 --dry-run
```

## 7. Run MegaTE, then MegaOrder(TSE)

MegaOrder(TSE) loads the MegaTE solutions for the same topology, server count,
TM model, and slices from `Mega-logs`. Therefore, the MegaTE command must finish
successfully before starting MegaOrder(TSE):

```bash
python Run_all.py --algo mega --server 100 \
  --problem UsCarrier.graphml --slices 10 11 \
  --epsilon 0.1 --lambda 1

python tse.py --server 100 --problem UsCarrier.graphml \
  --slices 10 11 --tm-model generic \
  --epsilon 0.1 --lambda 1
```

MegaTE writes its reusable solutions under `benchmarks/Mega-logs/`.
MegaOrder(TSE) writes its solutions under `benchmarks/TSE-logs/`. The summary
files `mega.csv` and `tse.csv`, all solution objects, and all logs are ignored
by Git.

