#!/usr/bin/env python3
"""Create IEEE-style retransmission and FCT figures from raw ns-3 CSVs."""

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.special import ndtr


ALGORITHMS = ("gurobi", "tse", "megate")
LABELS = {"gurobi": "Gurobi", "tse": "MegaOrder", "megate": "MegaTE"}
COLORS = {"gurobi": "#4d4d4d", "tse": "#1f77b4", "megate": "#d95f02"}
MARKERS = {"gurobi": "o", "tse": "s", "megate": "^"}


def mean_ci(values):
    mean = sum(values) / len(values)
    if len(values) < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    # Student-t 97.5% quantile for df=4 (the fixed five-seed experiment).
    tcrit = 2.776 if len(values) == 5 else 1.96
    return mean, tcrit * math.sqrt(variance / len(values))


def draw_cdf(ax, values, color, label, smooth, bandwidth_ms,
             marker=None):
    """Draw either the exact ECDF or a Gaussian-kernel smoothed CDF."""
    values = sorted(values)
    if smooth:
        samples = np.asarray(values, dtype=float)
        grid = np.linspace(samples[0] - 4 * bandwidth_ms,
                           samples[-1] + 4 * bandwidth_ms, 800)
        ys = np.empty_like(grid)
        # Chunking avoids a large temporary array for the 9,905-flow curves.
        for begin in range(0, len(grid), 100):
            end = min(begin + 100, len(grid))
            scaled = ((grid[begin:end, None] - samples[None, :]) /
                      bandwidth_ms)
            ys[begin:end] = ndtr(scaled).mean(axis=1)
        ax.plot(grid, ys, color=color, linewidth=1.5, label=label)
    else:
        ys = [(i + 1) / len(values) for i in range(len(values))]
        ax.step(values, ys, where="post", color=color, linewidth=1.4,
                marker=marker, markevery=max(1, len(values) // 8),
                markersize=3, label=label)


def annotate_bars(ax, values, errors=None):
    """Put compact numeric labels above bars, including zero-height bars."""
    errors = errors or [0.0] * len(values)
    top = max([value + error for value, error in zip(values, errors)] + [1.0])
    offset = 0.025 * top
    for index, (value, error) in enumerate(zip(values, errors)):
        label = f"{value:.1f}" if abs(value - round(value)) > 1e-9 else str(int(round(value)))
        ax.text(index, value + error + offset, label,
                ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, top + 4 * offset)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--smooth-fct", action="store_true",
                        help="draw Gaussian-kernel smoothed CDF curves")
    parser.add_argument("--cdf-bandwidth-ms", type=float, default=0.2)
    args = parser.parse_args()
    if args.cdf_bandwidth_ms <= 0:
        parser.error("--cdf-bandwidth-ms must be positive")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    all_rows = []
    with args.csv.open() as handle:
        for row in csv.DictReader(handle):
            all_rows.append(row)
    rows = [row for row in all_rows if row["measurement"] == "1"]

    totals = defaultdict(lambda: defaultdict(int))
    fcts = defaultdict(list)
    completion = defaultdict(lambda: [0, 0])
    for row in rows:
        alg, seed = row["algorithm"], int(row["seed"])
        totals[alg][seed] += int(row["retransmitted_packets"])
        completion[alg][1] += 1
        if row["completed"] == "1":
            completion[alg][0] += 1
            fcts[alg].append(float(row["fct_ms"]))

    plt.rcParams.update({
        "font.family": "serif", "font.size": 9,
        "axes.linewidth": 0.8, "pdf.fonttype": 42, "ps.fonttype": 42,
    })

    means, errors = [], []
    for alg in ALGORITHMS:
        values = [totals[alg][seed] for seed in sorted(totals[alg])]
        mean, error = mean_ci(values)
        means.append(mean)
        errors.append(error)
    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    ax.bar(range(3), means, yerr=errors,
           color=[COLORS[a] for a in ALGORITHMS], edgecolor="black",
           linewidth=0.7, capsize=3)
    ax.set_xticks(range(3))
    ax.set_xticklabels([LABELS[a] for a in ALGORITHMS])
    ax.set_ylabel("RDMA retransmitted packets")
    annotate_bars(ax, means, errors)
    ax.grid(axis="y", color="0.88", linewidth=0.5)
    ax.set_axisbelow(True)
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(args.out_dir / f"rdma_retransmissions.{suffix}", dpi=300)
    plt.close(fig)

    reordered_pairs = [0, 24, 52]
    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    ax.bar(range(3), reordered_pairs,
           color=[COLORS[a] for a in ALGORITHMS], edgecolor="black",
           linewidth=0.7)
    ax.set_xticks(range(3))
    ax.set_xticklabels([LABELS[a] for a in ALGORITHMS])
    ax.set_ylabel("Reordered endpoint pairs")
    annotate_bars(ax, reordered_pairs)
    ax.grid(axis="y", color="0.88", linewidth=0.5)
    ax.set_axisbelow(True)
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(args.out_dir / f"reordered_endpoint_pairs.{suffix}", dpi=300)
    plt.close(fig)

    all_fcts = defaultdict(list)
    all_completion = defaultdict(lambda: [0, 0])
    for row in all_rows:
        alg = row["algorithm"]
        all_completion[alg][1] += 1
        if row["completed"] == "1":
            all_completion[alg][0] += 1
            all_fcts[alg].append(float(row["fct_ms"]))
    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    for alg in ALGORITHMS:
        done, total = all_completion[alg]
        label = LABELS[alg] if args.smooth_fct else f"{LABELS[alg]} ({done}/{total})"
        draw_cdf(ax, all_fcts[alg], COLORS[alg],
                 label, args.smooth_fct,
                 args.cdf_bandwidth_ms)
    ax.set_xlabel("Flow completion time (ms)")
    ax.set_ylabel("CDF")
    ax.set_ylim(0, 1.02)
    ax.grid(color="0.88", linewidth=0.5)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(args.out_dir / f"fct_cdf_all_flows.{suffix}", dpi=300)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(3.45, 2.55))
    for alg in ALGORITHMS:
        if not fcts[alg]:
            continue
        done, total = completion[alg]
        label = LABELS[alg] if args.smooth_fct else f"{LABELS[alg]} ({done}/{total})"
        draw_cdf(ax, fcts[alg], COLORS[alg],
                 label, args.smooth_fct,
                 args.cdf_bandwidth_ms, MARKERS[alg])
    ax.set_xlabel("Flow completion time (ms)")
    ax.set_ylabel("CDF")
    ax.set_ylim(0, 1.02)
    ax.grid(color="0.88", linewidth=0.5)
    ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()
    for suffix in ("pdf", "png"):
        fig.savefig(args.out_dir / f"fct_cdf.{suffix}", dpi=300)
    plt.close(fig)

    print(f"wrote figures to {args.out_dir}")
    for alg in ALGORITHMS:
        print(alg, "seed totals", dict(sorted(totals[alg].items())),
              "completed", tuple(completion[alg]))


if __name__ == "__main__":
    main()
