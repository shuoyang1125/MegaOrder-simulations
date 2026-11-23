#!/usr/bin/env python3
"""Plot 13 topology/metric figures from TSE-data-withstd.csv.

Each figure shows algorithm means with one-standard-deviation error bars.
The input has four topology sections and a K5 objective section, all with
paired Avg/STD rows.
"""

import argparse
import csv
import math
import os

import matplotlib
matplotlib.use('Agg')
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
    'reordered': {
        'label': 'Reordered Endpoint Pairs',
        'filename': 'reordered_endpoint_pairs',
        'offset': 2,
        'scale': 1.0,
    },
    'runtime': {
        'label': 'Runtime (seconds)',
        'filename': 'runtime',
        'offset': 8,
        'scale': 1.0,
    },
    'satisfied': {
        'label': 'Satisfied Demand (%)',
        'filename': 'satisfied_demand',
        'offset': 5,
        'scale': 100.0,
    },
}


plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman', 'DejaVu Serif'],
    'font.size': 10,
    'axes.labelsize': 14,
    'axes.titlesize': 14,
    'xtick.labelsize': 11,
    'ytick.labelsize': 12,
    'legend.fontsize': 10,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'axes.linewidth': 1.0,
    'lines.linewidth': 2.0,
    'lines.markersize': 7,
})


def _number(value):
    """Parse a numeric cell, returning NaN for an empty cell."""
    value = value.strip()
    return float(value) if value else math.nan


def _empty_record():
    return {
        stat: {
            metric: {algo: math.nan for algo in ALGORITHMS}
            for metric in METRICS
        }
        for stat in ('avg', 'std')
    }


def load_tse_with_std(filename):
    """Load topology sections containing paired Avg and STD rows."""
    records = {topology: {} for topology in TOPOLOGIES}
    endpoint_order = {topology: [] for topology in TOPOLOGIES}
    objective_records = {}
    objective_endpoint_order = []
    current_topology = None
    section = None

    with open(filename, 'r', encoding='utf-8-sig', newline='') as stream:
        for line_number, raw_row in enumerate(csv.reader(stream), start=1):
            row = [cell.strip() for cell in raw_row]
            if not row or not any(row):
                continue

            if row[0] in TOPOLOGIES:
                current_topology = row[0]
                section = 'metrics'
                continue
            if row[0].lower() == 'k5obj':
                current_topology = None
                section = 'objective'
                continue

            row_type = row[0].lower()
            if row_type not in ('avg', 'std'):
                continue
            if section is None:
                raise ValueError(
                    'data row before section at line {}'.format(line_number))

            endpoint = int(row[1])
            if section == 'objective':
                if len(row) < 5:
                    raise ValueError(
                        'expected 5 objective columns at line {}, got {}'
                        .format(line_number, len(row)))
                if endpoint not in objective_records:
                    objective_records[endpoint] = {
                        stat: {algo: math.nan for algo in ALGORITHMS}
                        for stat in ('avg', 'std')
                    }
                    objective_endpoint_order.append(endpoint)
                for algo_index, algo in enumerate(ALGORITHMS):
                    objective_records[endpoint][row_type][algo] = _number(
                        row[2 + algo_index])
                continue

            if current_topology is None or len(row) < 11:
                raise ValueError(
                    'expected 11 columns at line {}, got {}'.format(
                        line_number, len(row)))

            topology_records = records[current_topology]
            if endpoint not in topology_records:
                topology_records[endpoint] = _empty_record()
                endpoint_order[current_topology].append(endpoint)

            for metric, config in METRICS.items():
                offset = config['offset']
                scale = config['scale']
                for algo_index, algo in enumerate(ALGORITHMS):
                    value = _number(row[offset + algo_index])
                    topology_records[endpoint][row_type][metric][algo] = (
                        value * scale)

    output = {}
    for topology in TOPOLOGIES:
        endpoints = endpoint_order[topology]
        if not endpoints:
            raise ValueError('missing data for topology {}'.format(topology))

        means = {
            metric: {algo: [] for algo in ALGORITHMS}
            for metric in METRICS
        }
        stds = {
            metric: {algo: [] for algo in ALGORITHMS}
            for metric in METRICS
        }
        for endpoint in endpoints:
            record = records[topology][endpoint]
            for metric in METRICS:
                for algo in ALGORITHMS:
                    mean = record['avg'][metric][algo]
                    std = record['std'][metric][algo]
                    if math.isnan(mean) != math.isnan(std):
                        raise ValueError(
                            '{} endpoint {} {} {} has unmatched Avg/STD'
                            .format(topology, endpoint, metric, algo))
                    means[metric][algo].append(mean)
                    stds[metric][algo].append(std)

        output[topology] = {
            'endpoints': endpoints,
            'mean': means,
            'std': stds,
        }

    if not objective_endpoint_order:
        raise ValueError('missing K5obj section')
    objective_data = {
        'endpoints': objective_endpoint_order,
        'mean': {algo: [] for algo in ALGORITHMS},
        'std': {algo: [] for algo in ALGORITHMS},
    }
    for endpoint in objective_endpoint_order:
        record = objective_records[endpoint]
        for algo in ALGORITHMS:
            mean = record['avg'][algo]
            std = record['std'][algo]
            if math.isnan(mean) != math.isnan(std):
                raise ValueError(
                    'K5obj endpoint {} {} has unmatched Avg/STD'.format(
                        endpoint, algo))
            objective_data['mean'][algo].append(mean)
            objective_data['std'][algo].append(std)

    return output, objective_data


def _finite_bounds(means, stds):
    lower = []
    upper = []
    for algo in ALGORITHMS:
        mean = np.asarray(means[algo], dtype=float)
        std = np.asarray(stds[algo], dtype=float)
        valid = np.isfinite(mean) & np.isfinite(std)
        lower.extend((mean[valid] - std[valid]).tolist())
        upper.extend((mean[valid] + std[valid]).tolist())
    if not lower:
        raise ValueError('metric has no finite Avg/STD pairs')
    return min(lower), max(upper)


def plot_metric(topology, metric, data, output_dir):
    endpoints = data['endpoints']
    x_positions = np.arange(len(endpoints))
    means = data['mean'][metric]
    stds = data['std'][metric]

    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    for algo in ALGORITHMS:
        style = ALGORITHM_STYLE[algo]
        ax.errorbar(
            x_positions,
            np.asarray(means[algo], dtype=float),
            yerr=np.asarray(stds[algo], dtype=float),
            color=style['color'],
            marker=style['marker'],
            linestyle=style['linestyle'],
            label=style['label'],
            capsize=3,
            capthick=1.0,
            elinewidth=1.1,
        )

    ax.set_title(topology)
    ax.set_xlabel('Number of Endpoints')
    ax.set_ylabel(METRICS[metric]['label'])
    ax.set_xticks(x_positions)
    ax.set_xticklabels(endpoints)
    ax.grid(True, which='both', linestyle='--', alpha=0.3)

    lower, upper = _finite_bounds(means, stds)
    span = max(upper - lower, 1.0)
    if metric == 'runtime':
        ax.set_yscale('log')
        positive_lower = [
            mean - std
            for algo in ALGORITHMS
            for mean, std in zip(means[algo], stds[algo])
            if math.isfinite(mean) and math.isfinite(std) and mean - std > 0
        ]
        if positive_lower:
            ax.set_ylim(bottom=min(positive_lower) * 0.75)
        legend_location = 'upper left'
    elif metric == 'satisfied':
        ax.set_ylim(max(0.0, lower - span * 0.10),
                    min(101.0, upper + span * 0.10))
        legend_location = 'lower right'
    else:
        ax.set_ylim(min(0.0, lower - span * 0.05), upper + span * 0.10)
        legend_location = 'upper left'

    ax.legend(frameon=True, fancybox=False, shadow=False,
              loc=legend_location)
    fig.tight_layout()

    filename_stem = '{}_{}'.format(
        topology, METRICS[metric]['filename'])
    output_paths = []
    for extension in ('png', 'pdf'):
        output_path = os.path.join(
            output_dir, '{}.{}'.format(filename_stem, extension))
        fig.savefig(output_path, bbox_inches='tight')
        output_paths.append(output_path)
    plt.close(fig)
    print('saved {}'.format(', '.join(output_paths)))


def plot_normalized_objective(objective_data, output_dir):
    """Plot K5 objective averages normalized by the maximum Gurobi Avg."""
    gurobi_values = np.asarray(
        objective_data['mean']['gurobi'], dtype=float)
    finite_gurobi = gurobi_values[np.isfinite(gurobi_values)]
    if finite_gurobi.size == 0:
        raise ValueError('K5obj section has no finite Gurobi Avg values')
    gurobi_max = float(finite_gurobi.max())

    normalized_mean = {
        algo: np.asarray(objective_data['mean'][algo], dtype=float) /
        gurobi_max
        for algo in ALGORITHMS
    }
    endpoints = objective_data['endpoints']
    x_positions = np.arange(len(endpoints))
    fig, ax = plt.subplots(figsize=(5.4, 3.8))
    for algo in ALGORITHMS:
        style = ALGORITHM_STYLE[algo]
        ax.plot(
            x_positions,
            normalized_mean[algo],
            color=style['color'],
            marker=style['marker'],
            linestyle=style['linestyle'],
            label=style['label'],
        )

    ax.set_title('K5')
    ax.set_xlabel('Number of Endpoints')
    ax.set_ylabel('Normalized Objective Value')
    ax.set_xticks(x_positions)
    ax.set_xticklabels(endpoints)
    ax.grid(True, linestyle='--', alpha=0.3)
    finite_values = np.concatenate([
        normalized_mean[algo][np.isfinite(normalized_mean[algo])]
        for algo in ALGORITHMS
    ])
    lower = float(finite_values.min())
    upper = float(finite_values.max())
    span = max(upper - lower, 0.01)
    ax.set_ylim(max(0.0, lower - span * 0.10), upper + span * 0.10)
    ax.legend(frameon=True, fancybox=False, shadow=False,
              loc='lower right')
    fig.tight_layout()

    output_paths = []
    for extension in ('png', 'pdf'):
        output_path = os.path.join(
            output_dir, 'K5_normalized_objective.{}'.format(extension))
        fig.savefig(output_path, bbox_inches='tight')
        output_paths.append(output_path)
    plt.close(fig)
    print('saved {}'.format(', '.join(output_paths)))
    return gurobi_max


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', default='TSE-data-withstd.csv')
    parser.add_argument(
        '--output-dir', default='TSE-withstd-individual-plots')
    args = parser.parse_args()

    data, objective_data = load_tse_with_std(args.input)
    os.makedirs(args.output_dir, exist_ok=True)

    for topology in TOPOLOGIES:
        for metric in ('reordered', 'runtime', 'satisfied'):
            plot_metric(topology, metric, data[topology], args.output_dir)

    gurobi_max = plot_normalized_objective(objective_data, args.output_dir)
    print('Gurobi objective normalization denominator: {:.8f}'.format(
        gurobi_max))
    print('Generated 13 figures in PNG and PDF formats in {}'.format(
        args.output_dir))


if __name__ == '__main__':
    main()
