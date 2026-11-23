#!/usr/bin/env python3
"""
Plot results from data.csv in SIGCOMM/NSDI style

Generates 3 plots:
1. Reordered srv-srv pairs vs endpoint
2. Satisfied demand vs endpoint
3. Runtime vs endpoint
"""

import pandas as pd
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


# Topology names in order
TOPOLOGY_NAMES = ['Uninett2010', 'Deltacom', 'UsCarrier', 'Cogentco']


def load_data(filename='data1.csv'):
    """Load data from CSV file with 4 topologies

    Format:
    - Line 1: Topology name (e.g., "Uninett2010")
    - Line 2: Column description (skip)
    - Line 3: Column headers (skip)
    - Line 4+: Data rows
    - Then repeat for next topology
    """
    with open(filename, 'r', encoding='utf-8-sig') as f:  # Use utf-8-sig to handle BOM
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


def plot_reordered_pairs(data_by_topo):
    """Plot reordered srv-srv pairs vs endpoint - 2x2 subplots"""
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))

    for idx, (topo_name, ax) in enumerate(zip(TOPOLOGY_NAMES, axes.flat)):
        data = data_by_topo.get(topo_name)
        if data is None:
            continue

        endpoints = data['endpoints']
        reordered = data['reordered']
        x_pos = np.arange(len(endpoints))

        for algo, config in ALGO_CONFIG.items():
            ax.plot(x_pos, reordered[algo],
                    color=config['color'],
                    marker=config['marker'],
                    linestyle=config['linestyle'],
                    label=config['label'])

        ax.set_xlabel('Number of Endpoints')
        ax.set_ylabel('Reordered Endpoint Pairs')
        ax.set_yscale('log')
        ax.set_ylim(bottom=1)
        ax.set_xticks(x_pos)
        ax.set_xticklabels(endpoints, rotation=45, ha='right')
        ax.set_title(topo_name)
        ax.legend(frameon=True, fancybox=False, shadow=False, loc='lower right')
        ax.grid(True, linestyle='--', alpha=0.3)

    plt.tight_layout()
    plt.savefig('reordered_pairs.pdf', format='pdf', bbox_inches='tight')
    plt.savefig('reordered_pairs.png', format='png', bbox_inches='tight')
    print("Saved: reordered_pairs.pdf/png")


def plot_satisfied_demand(data_by_topo):
    """Plot satisfied demand vs endpoint - 2x2 subplots"""
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))

    for idx, (topo_name, ax) in enumerate(zip(TOPOLOGY_NAMES, axes.flat)):
        data = data_by_topo.get(topo_name)
        if data is None:
            continue

        endpoints = data['endpoints']
        satisfied = data['satisfied']
        x_pos = np.arange(len(endpoints))

        for algo, config in ALGO_CONFIG.items():
            ax.plot(x_pos, satisfied[algo],
                    color=config['color'],
                    marker=config['marker'],
                    linestyle=config['linestyle'],
                    label=config['label'])

        ax.set_xlabel('Number of Endpoints')
        ax.set_ylabel('Satisfied Demand (%)')
        ax.set_ylim([40, 110])  # Focus on the relevant range
        ax.set_yticks(np.arange(40, 101, 10))  # Only show ticks up to 100
        ax.set_xticks(x_pos)
        ax.set_xticklabels(endpoints, rotation=45, ha='right')
        ax.set_title(topo_name)
        ax.legend(frameon=True, fancybox=False, shadow=False)
        ax.grid(True, linestyle='--', alpha=0.3)

    plt.tight_layout()
    plt.savefig('satisfied_demand.pdf', format='pdf', bbox_inches='tight')
    plt.savefig('satisfied_demand.png', format='png', bbox_inches='tight')
    print("Saved: satisfied_demand.pdf/png")


def plot_runtime(data_by_topo):
    """Plot runtime vs endpoint - 2x2 subplots"""
    fig, axes = plt.subplots(2, 2, figsize=(10, 8))

    for idx, (topo_name, ax) in enumerate(zip(TOPOLOGY_NAMES, axes.flat)):
        data = data_by_topo.get(topo_name)
        if data is None:
            continue

        endpoints = data['endpoints']
        runtime = data['runtime']
        x_pos = np.arange(len(endpoints))

        for algo, config in ALGO_CONFIG.items():
            ax.plot(x_pos, runtime[algo],
                    color=config['color'],
                    marker=config['marker'],
                    linestyle=config['linestyle'],
                    label=config['label'])

        ax.set_xlabel('Number of Endpoints')
        ax.set_ylabel('Runtime (seconds)')
        ax.set_yscale('log')  # Use logarithmic scale for y-axis
        ax.set_ylim(top=1e4)  # Extend upper range for legend space
        ax.set_xticks(x_pos)
        ax.set_xticklabels(endpoints, rotation=45, ha='right')
        ax.set_title(topo_name)
        ax.legend(frameon=True, fancybox=False, shadow=False, loc='upper left')
        ax.grid(True, linestyle='--', alpha=0.3)

    plt.tight_layout()
    plt.savefig('runtime.pdf', format='pdf', bbox_inches='tight')
    plt.savefig('runtime.png', format='png', bbox_inches='tight')
    print("Saved: runtime.pdf/png")


def main():
    # Load data
    print("Loading data from data1.csv...")
    data_by_topo = load_data('data1.csv')

    print(f"Found {len(data_by_topo)} topologies")
    for topo, data in data_by_topo.items():
        print(f"  {topo}: {len(data['endpoints'])} data points")
    print()

    # Generate plots
    print("Generating plots...")
    plot_reordered_pairs(data_by_topo)
    plot_satisfied_demand(data_by_topo)
    plot_runtime(data_by_topo)

    print("\nAll plots generated successfully!")
    print("\nFiles generated:")
    print("  - reordered_pairs.pdf/png (2x2 subplots)")
    print("  - satisfied_demand.pdf/png (2x2 subplots)")
    print("  - runtime.pdf/png (2x2 subplots)")


if __name__ == '__main__':
    main()
