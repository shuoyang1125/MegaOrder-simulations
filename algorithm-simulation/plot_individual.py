#!/usr/bin/env python3
"""
Plot individual figures for each topology and metric

Generates 12 individual plots:
- 4 topologies x 3 metrics = 12 plots
Output format: {topology}_{metric}.pdf/png
"""

import matplotlib.pyplot as plt
import numpy as np

# Set SIGCOMM/NSDI style parameters
plt.rcParams.update({
    'font.family': 'serif',
    'font.serif': ['Times New Roman'],
    'font.size': 10,
    'axes.labelsize': 14,
    'axes.titlesize': 14,
    'xtick.labelsize': 14,
    'ytick.labelsize': 14,
    'legend.fontsize': 10,
    'figure.dpi': 300,
    'savefig.dpi': 300,
    'axes.linewidth': 1.0,
    'lines.linewidth': 2.0,
    'lines.markersize': 8,
    'grid.alpha': 0.3,
})

# Algorithm colors and markers
ALGO_CONFIG = {
    'megaorder': {
        'color': '#1f77b4',  # Blue
        'marker': 'o',
        'linestyle': '-',
        'label': 'MegaOrder'
    },
    'LP-all': {
        'color': '#ff7f0e',  # Orange
        'marker': 's',
        'linestyle': '--',
        'label': 'LP-all'
    },
    'megate': {
        'color': '#2ca02c',  # Green
        'marker': '^',
        'linestyle': '-.',
        'label': 'MegaTE'
    }
}

# Topology names
TOPOLOGY_NAMES = ['Uninett2010', 'Deltacom', 'UsCarrier', 'Cogentco']

# Metric names for file naming
METRIC_NAMES = {
    'reordered': 'reordered_pairs',
    'satisfied': 'satisfied_demand',
    'runtime': 'runtime'
}


def load_data(filename='data1.csv'):
    """Load data from CSV file with 4 topologies"""
    with open(filename, 'r', encoding='utf-8-sig') as f:
        lines = f.readlines()

    data_by_topo = {}
    current_topo = None
    data_start = False

    for line in lines:
        line = line.strip()

        # Detect topology name (single word line)
        if line in TOPOLOGY_NAMES:
            current_topo = line
            data_by_topo[current_topo] = {
                'endpoints': [],
                'reordered': {'megaorder': [], 'LP-all': [], 'megate': []},
                'satisfied': {'megaorder': [], 'LP-all': [], 'megate': []},
                'runtime': {'megaorder': [], 'LP-all': [], 'megate': []}
            }
            data_start = False
            continue

        # Skip header lines
        if '乱序srv-srv pairs' in line or 'endpoint' in line:
            data_start = True
            continue

        # Parse data lines (start after headers)
        if data_start and current_topo and line:
            cols = line.split(',')
            if len(cols) >= 10 and cols[0]:  # Valid data row
                try:
                    data_by_topo[current_topo]['endpoints'].append(int(cols[0]))
                    data_by_topo[current_topo]['reordered']['megaorder'].append(int(cols[1]))
                    data_by_topo[current_topo]['reordered']['LP-all'].append(int(cols[2]))
                    data_by_topo[current_topo]['reordered']['megate'].append(int(cols[3]))
                    data_by_topo[current_topo]['satisfied']['megaorder'].append(float(cols[4]) * 100)
                    data_by_topo[current_topo]['satisfied']['LP-all'].append(float(cols[5]) * 100)
                    data_by_topo[current_topo]['satisfied']['megate'].append(float(cols[6]) * 100)
                    data_by_topo[current_topo]['runtime']['megaorder'].append(float(cols[7]))
                    data_by_topo[current_topo]['runtime']['LP-all'].append(float(cols[8]))
                    data_by_topo[current_topo]['runtime']['megate'].append(float(cols[9]))
                except (ValueError, IndexError):
                    continue

    return data_by_topo


def plot_single_metric(topo_name, metric, data, output_dir='individual_plots'):
    """Plot a single metric for one topology

    Args:
        topo_name: Topology name (e.g., 'Uninett2010')
        metric: Metric type ('reordered', 'satisfied', or 'runtime')
        data: Dictionary containing the metric data
        output_dir: Directory to save plots
    """
    endpoints = data['endpoints']
    metric_data = data[metric]
    x_pos = np.arange(len(endpoints))

    # Create figure
    fig, ax = plt.subplots(1, 1, figsize=(5, 3.5))

    # Plot each algorithm
    for algo, config in ALGO_CONFIG.items():
        ax.plot(x_pos, metric_data[algo],
                color=config['color'],
                marker=config['marker'],
                linestyle=config['linestyle'],
                label=config['label'])

    # Set metric-specific properties
    if metric == 'reordered':
        ax.set_ylabel('Reordered Endpoint Pairs')
        ax.set_yscale('log')
        ax.set_ylim(bottom=1)
        legend_loc = 'lower right'
    elif metric == 'satisfied':
        ax.set_ylabel('Satisfied Demand (%)')
        ax.set_ylim([40, 110])
        ax.set_yticks(np.arange(40, 101, 10))
        legend_loc = 'best'
    else:  # runtime
        ax.set_ylabel('Runtime (seconds)')
        ax.set_yscale('log')
        ax.set_ylim(top=1e4)
        legend_loc = 'upper left'

    # Common settings
    ax.set_xlabel('Number of Endpoints')
    ax.set_xticks(x_pos)
    ax.set_xticklabels(endpoints)
    ax.legend(frameon=True, fancybox=False, shadow=False, loc=legend_loc)
    ax.grid(True, linestyle='--', alpha=0.3)

    # Generate filename
    metric_name = METRIC_NAMES[metric]
    filename_base = f"{topo_name}_{metric_name}"

    # Save figure
    import os
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    plt.tight_layout()
    plt.savefig(f'{output_dir}/{filename_base}.pdf', format='pdf', bbox_inches='tight')
    plt.savefig(f'{output_dir}/{filename_base}.png', format='png', bbox_inches='tight')
    plt.close()

    print(f"  Saved: {filename_base}.pdf/png")


def main():
    # Load data
    print("Loading data from data1.csv...")
    data_by_topo = load_data('data1.csv')

    print(f"Found {len(data_by_topo)} topologies")
    for topo, data in data_by_topo.items():
        print(f"  {topo}: {len(data['endpoints'])} data points")
    print()

    # Generate individual plots
    print("Generating individual plots...")
    print()

    for topo_name in TOPOLOGY_NAMES:
        if topo_name not in data_by_topo:
            print(f"Warning: {topo_name} not found in data")
            continue

        data = data_by_topo[topo_name]
        print(f"{topo_name}:")

        for metric in ['reordered', 'satisfied', 'runtime']:
            plot_single_metric(topo_name, metric, data)

    print()
    print("All individual plots generated successfully!")
    print()
    print("Output directory: individual_plots/")
    print("Files generated:")
    for topo in TOPOLOGY_NAMES:
        for metric in METRIC_NAMES.values():
            print(f"  - {topo}_{metric}.pdf/png")


if __name__ == '__main__':
    main()
