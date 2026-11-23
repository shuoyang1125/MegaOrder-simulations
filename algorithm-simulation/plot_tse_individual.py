#!/usr/bin/env python3
"""Generate the 13 individual figures stored in TSE-data.csv.

The first twelve figures are four topologies times three metrics.  The last
figure compares the K5 objective values, with every value divided by the
largest Gurobi objective in the objective section.
"""

import argparse
import csv
import math
import os

import matplotlib.pyplot as plt
import numpy as np


TOPOLOGIES = ('Uninett2010', 'Deltacom', 'UsCarrier', 'K5')
ALGORITHMS = ('megaorder', 'gurobi', 'megate')
ALGORITHM_STYLE = {
    'megaorder': {
        'color': '#1f77b4', 'marker': 'o', 'linestyle': '-',
        'label': 'MegaOrder',
    },
    'gurobi': {
        'color': '#ff7f0e', 'marker': 's', 'linestyle': '--',
        'label': 'Gurobi',
    },
    'megate': {
        'color': '#2ca02c', 'marker': '^', 'linestyle': '-.',
        'label': 'MegaTE',
    },
}
METRICS = {
    'reordered': ('Reordered Endpoint Pairs', 'reordered_endpoint_pairs'),
    'runtime': ('Runtime (seconds)', 'runtime'),
    'satisfied': ('Satisfied Demand (%)', 'satisfied_demand'),
}


plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'DejaVu Serif'],
    'font.size': 10,
    'axes.labelsize': 14,
    'axes.titlesize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 10,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'axes.linewidth': 1.0,
    'lines.linewidth': 2.0,
    'lines.markersize': 7,
})


def _number(value):
    """Parse an optional numeric CSV cell, returning NaN when it is empty."""
    value = value.strip()
    return float(value) if value else math.nan


def _empty_topology_data():
    return {
        'endpoints': [],
        'reordered': {algo: [] for algo in ALGORITHMS},
        'satisfied': {algo: [] for algo in ALGORITHMS},
        'runtime': {algo: [] for algo in ALGORITHMS},
    }


def load_tse_data(filename):
    """Read the section-based layout used by TSE-data.csv."""
    topology_data = {}
    objective_data = {
        'endpoints': [],
        'obj': {algo: [] for algo in ALGORITHMS},
    }
    current_topology = None
    section = None
    awaiting_section_type = False
    reading_rows = False

    with open(filename, 'r', encoding='utf-8-sig', newline='') as stream:
        for raw_row in csv.reader(stream):
            row = [cell.strip() for cell in raw_row]
            if not row or not any(row):
                continue
            first = row[0]

            if first in TOPOLOGIES:
                current_topology = first
                section = None
                awaiting_section_type = True
                reading_rows = False
                continue

            if awaiting_section_type:
                section = 'objective' if first.lower() == 'obj' else 'metrics'
                awaiting_section_type = False
                reading_rows = False
                if section == 'metrics':
                    topology_data[current_topology] = _empty_topology_data()
                continue

            if first.lower() == 'endpoint':
                reading_rows = True
                continue
            if not reading_rows or current_topology is None:
                continue

            try:
                endpoint = int(first)
            except ValueError:
                continue

            if section == 'metrics' and len(row) >= 10:
                data = topology_data[current_topology]
                data['endpoints'].append(endpoint)
                for offset, algo in enumerate(ALGORITHMS, start=1):
                    data['reordered'][algo].append(_number(row[offset]))
                    satisfied = _number(row[offset + 3])
                    data['satisfied'][algo].append(satisfied * 100.0)
                    data['runtime'][algo].append(_number(row[offset + 6]))
            elif section == 'objective' and len(row) >= 4:
                objective_data['endpoints'].append(endpoint)
                for offset, algo in enumerate(ALGORITHMS, start=1):
                    objective_data['obj'][algo].append(_number(row[offset]))

    return topology_data, objective_data


def _plot_algorithms(ax, x_positions, values):
    for algo in ALGORITHMS:
        style = ALGORITHM_STYLE[algo]
        ax.plot(x_positions, values[algo], color=style['color'],
                marker=style['marker'], linestyle=style['linestyle'],
                label=style['label'])


def _finish_and_save(fig, output_dir, filename):
    fig.tight_layout()
    for extension in ('pdf', 'png'):
        fig.savefig(os.path.join(output_dir, '{}.{}'.format(
            filename, extension)), bbox_inches='tight')
    plt.close(fig)
    print('  saved {}.pdf/png'.format(filename))


def plot_metric(topology, metric, data, output_dir):
    endpoints = data['endpoints']
    x_positions = np.arange(len(endpoints))
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    _plot_algorithms(ax, x_positions, data[metric])

    ylabel, filename_metric = METRICS[metric]
    ax.set_xlabel('Number of Endpoints')
    ax.set_ylabel(ylabel)
    ax.set_xticks(x_positions)
    ax.set_xticklabels(endpoints)
    ax.grid(True, which='both', linestyle='--', alpha=0.3)

    if metric == 'reordered':
        finite = np.concatenate([
            np.asarray(data[metric][algo], dtype=float)
            for algo in ALGORITHMS
        ])
        finite = finite[np.isfinite(finite)]
        largest = max(1.0, float(finite.max()))
        # Use a linear axis, keeping zero away from the lower frame and
        # leaving visible headroom above the largest value.
        ax.set_ylim(-largest * 0.05, largest * 1.10)
        legend_location = 'best'
    elif metric == 'runtime':
        ax.set_yscale('log')
        if topology in ('Deltacom', 'UsCarrier'):
            # Their measured runtimes lie mostly within one decade. Extend
            # the axis so both 10^1 and 10^2 are explicitly labeled.
            ax.set_ylim(top=1.2e2)
            ax.set_yticks([1e1, 1e2])
        legend_location = 'upper left'
    else:
        finite = np.concatenate([
            np.asarray(data[metric][algo], dtype=float)
            for algo in ALGORITHMS
        ])
        finite = finite[np.isfinite(finite)]
        lower = max(0.0, math.floor((finite.min() - 1.0) / 5.0) * 5.0)
        ax.set_ylim(lower, 101.0)
        legend_location = 'lower right'

    ax.legend(frameon=True, fancybox=False, shadow=False,
              loc=legend_location)
    _finish_and_save(
        fig, output_dir, '{}_{}'.format(topology, filename_metric))


def plot_normalized_objective(objective_data, output_dir):
    gurobi_values = np.asarray(objective_data['obj']['gurobi'], dtype=float)
    finite_gurobi = gurobi_values[np.isfinite(gurobi_values)]
    if finite_gurobi.size == 0:
        raise ValueError('objective section has no finite Gurobi values')
    gurobi_max = float(finite_gurobi.max())

    normalized = {
        algo: np.asarray(objective_data['obj'][algo], dtype=float) / gurobi_max
        for algo in ALGORITHMS
    }
    endpoints = objective_data['endpoints']
    x_positions = np.arange(len(endpoints))
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    _plot_algorithms(ax, x_positions, normalized)
    ax.set_xlabel('Number of Endpoints')
    ax.set_ylabel('Normalized Objective Value')
    ax.set_xticks(x_positions)
    ax.set_xticklabels(endpoints)
    ax.set_ylim(0.85, 1.01)
    ax.grid(True, linestyle='--', alpha=0.3)
    ax.legend(frameon=True, fancybox=False, shadow=False, loc='lower right')
    _finish_and_save(fig, output_dir, 'K5_normalized_objective')
    return gurobi_max


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='TSE-data.csv')
    parser.add_argument('--output-dir', default='TSE-individual-plots')
    args = parser.parse_args()

    topology_data, objective_data = load_tse_data(args.input)
    missing = [topology for topology in TOPOLOGIES
               if topology not in topology_data]
    if missing:
        raise ValueError('missing metric sections: {}'.format(', '.join(missing)))
    if not objective_data['endpoints']:
        raise ValueError('missing objective section')

    os.makedirs(args.output_dir, exist_ok=True)
    print('Generating 12 topology/metric figures...')
    for topology in TOPOLOGIES:
        for metric in ('reordered', 'runtime', 'satisfied'):
            plot_metric(topology, metric, topology_data[topology],
                        args.output_dir)

    print('Generating normalized objective figure...')
    gurobi_max = plot_normalized_objective(objective_data, args.output_dir)
    print('Gurobi normalization denominator: {:.8f}'.format(gurobi_max))
    print('Generated 13 figures in {}'.format(args.output_dir))


if __name__ == '__main__':
    main()
