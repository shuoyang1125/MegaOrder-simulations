# Packet-level simulation

This directory is a source-only snapshot of the Alibaba Cloud ns-3 simulator
with the RDMA and traffic-engineering extensions used by MegaTE. The original
licenses are retained in this directory and under `simulation/`.

The custom work includes changes to the point-to-point RDMA model and the
following packet-level experiment programs:

- `simulation/scratch/K5RdmaTeNetwork.cc`
- `simulation/scratch/TeReorderNetwork.cc`
- `simulation/examples/k5-rdma-te/`
- `simulation/examples/te-reorder/`

## Build

Install the normal ns-3 build dependencies, then run:

```bash
cd simulation
./ns3 configure --disable-examples
./ns3 build
```

The Alibaba RDMA extensions define an `ns3::Event` type that conflicts with a
Wi-Fi header used by some unrelated stock examples. For that reason, the
default instructions do not enable every upstream example at once. The custom
scratch programs are included in the normal build.

## Experiment inputs

Topology descriptions, flow lists, generated workload manifests, packet
traces, and experiment outputs are not included in this repository. Before
running an experiment, create the files referenced by its configuration script
or generate them with the supplied Python utilities.

The K5 workflow uses `examples/k5-rdma-te/generate_manifest.py` to translate
algorithm-level routing/traffic results into packet-level inputs. The resulting
topology and workload files must remain untracked.

Some experiment scripts preserve paths from the original research environment.
Set their simulator directory, Python interpreter, and local input paths for
your machine before running them.

## Running

After preparing local inputs and building ns-3, use the scripts in the relevant
example directory, or invoke a scratch program directly, for example:

```bash
cd simulation
./ns3 run "K5RdmaTeNetwork --help"
./ns3 run "TeReorderNetwork --help"
```

Generated `outputs/`, logs, CSV files, traces, figures, and build products are
ignored and must not be committed.

