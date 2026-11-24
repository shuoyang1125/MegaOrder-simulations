# MegaOrder Simulations

This repository contains the source code for two complementary evaluation
layers used by MegaTE:

- [`algorithm-simulation`](algorithm-simulation/README.md) contains the
  algorithm-level MegaTE, MegaOrder(TSE), exact-solver, and analysis code.
- [`packet-simulation`](packet-simulation/README.md) contains the packet-level
  ns-3 simulation source, including the RDMA and traffic-engineering changes.

The repository intentionally contains source code only. Topologies, traffic
matrices, generated workloads, packet traces, solver outputs, experiment logs,
plots, and build products are excluded. Follow the README in each subdirectory
to prepare the required local inputs.

Maintainer: [Shuo Yang (@shuoyang1125)](https://github.com/shuoyang1125)

## Repository layout

```text
.
|-- algorithm-simulation/   # Algorithm-level simulation and Conda environment
`-- packet-simulation/      # Complete ns-3 source snapshot and TE extensions
```

## Data policy

Large and generated artifacts must remain outside Git. In particular, do not
commit files under `topologies/`, `traffic-matrices/`, `outputs/`, `build/`, or
experiment log directories. The root `.gitignore` enforces this policy.

## Licensing

The packet-level simulator retains the licenses and notices distributed with
the Alibaba Cloud/ns-3 source. No additional license is granted for the
algorithm-level code by this repository. Review ownership and select a license
before making the repository public.

