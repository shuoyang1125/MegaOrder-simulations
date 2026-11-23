#!/usr/bin/env python
"""
Script to analyze srv-srv pair reordering in Mega algorithm

Reordering definition: A srv-srv pair is "reordered" if it was assigned to one path
in TM1 but assigned to a different path in TM2.

This script:
1. Reads two ssp_solution.pkl files from Mega algorithm
2. Maps solutions to fixed path_nums (using complete path file)
3. Counts reordered srv-srv pairs
"""

import pickle
import sys
import os
sys.path.append('..')

from lib.config import TOPOLOGIES_DIR, edge_disjoint, num_paths


def load_mega_solution(solution_path):
    """Load Mega's SSP solution from pickle file"""
    with open(solution_path, 'rb') as f:
        data = pickle.load(f)

    # MegaOrder solutions wrap the payload as
    # {'ssp_out': {(srv_i, srv_j): path}, 'current_solution': {...}};
    # older Mega solutions store the flat {(srv_i, srv_j): path} dict directly
    if isinstance(data, dict) and 'ssp_out' in data:
        return data['ssp_out']

    return data

            # # Load complete path dict file path (for first TM or when problem changes)
            # complete_path_fname = os.path.join(SITE_PATH_DIR,
            #         '{}-{}-paths_edge-disjoint-{}_dist-metric-{}-dict.pkl'
            #         .format(problem_name, num_paths, edge_disjoint, dist_metric))
def load_complete_path_dict(problem_name, num_paths=4, edge_disjoint=True, dist_metric='inv-cap'):
    """Load complete path dict for fixed path_num mapping"""
    complete_path_fname = os.path.join(
        TOPOLOGIES_DIR, 'paths', 'site-paths',
        f'{problem_name}-{num_paths}-paths_edge-disjoint-{edge_disjoint}_dist-metric-{dist_metric}-dict.pkl'
    )

    with open(complete_path_fname, 'rb') as f:
        return pickle.load(f)


def init_fixed_path_mapping(complete_path_dict):
    """
    Initialize fixed path_num assignment (same logic as SSP_ORDER_MAIN._init_fixed_path_nums)

    Returns:
        path_to_fixed_path_num: dict mapping tuple(path) -> fixed_path_num
        fixed_path_num_to_path: dict mapping fixed_path_num -> tuple(path)
    """
    sorted_site_pairs = sorted(complete_path_dict.keys())

    # Calculate path_num ranges for each site_pair
    site_pair_path_num_start = {}
    current_path_num = 0
    for site_pair in sorted_site_pairs:
        site_pair_path_num_start[site_pair] = current_path_num
        num_paths = len(complete_path_dict[site_pair])
        current_path_num += num_paths

    total_paths = current_path_num

    # Build mapping
    path_to_fixed_path_num = {}
    fixed_path_num_to_path = {}

    for site_pair in sorted_site_pairs:
        base_path_num = site_pair_path_num_start[site_pair]
        complete_paths = complete_path_dict[site_pair]

        for path_idx, path in enumerate(complete_paths):
            fixed_path_num = base_path_num + path_idx
            path_to_fixed_path_num[tuple(path)] = fixed_path_num
            fixed_path_num_to_path[fixed_path_num] = tuple(path)

    return path_to_fixed_path_num, fixed_path_num_to_path


def map_solution_to_fixed_path_nums(ssp_solution, path_to_fixed_path_num):
    """
    Map Mega's SSP solution to fixed path_nums

    Args:
        ssp_solution: Dict of {(srv_i, srv_j): srv_path}
        path_to_fixed_path_num: Dict mapping tuple(path) -> fixed_path_num

    Returns:
        Dict of {(srv_i, srv_j): fixed_path_num}
    """
    mapped_solution = {}

    for srv_pair, srv_path in ssp_solution.items():
        # srv_path format: [srv_i, ..., srv_j] or [srv_i, site1, ..., site_k, srv_j]
        # Extract the site-site path (middle part)
        path_key = tuple(srv_path[1:-1]) if len(srv_path) > 2 else tuple(srv_path)

        if path_key in path_to_fixed_path_num:
            mapped_solution[srv_pair] = path_to_fixed_path_num[path_key]
        else:
            print(f"Warning: Path {path_key} not found in complete path dict")

    return mapped_solution


def count_reordered_pairs(tm1_solution, tm2_solution):
    """
    Count reordered srv-srv pairs between two solutions

    Reordered definition: srv_pair assigned to different paths in TM1 vs TM2

    Args:
        tm1_solution: Dict of {(srv_i, srv_j): fixed_path_num} for TM1
        tm2_solution: Dict of {(srv_i, srv_j): fixed_path_num} for TM2

    Returns:
        Dict with statistics
    """
    # Find all srv_pairs that appear in both solutions
    common_pairs = set(tm1_solution.keys()) & set(tm2_solution.keys())

    reordered_pairs = []
    stable_pairs = []
    tm1_only_pairs = set(tm1_solution.keys()) - set(tm2_solution.keys())
    tm2_only_pairs = set(tm2_solution.keys()) - set(tm1_solution.keys())

    for srv_pair in common_pairs:
        if tm1_solution[srv_pair] != tm2_solution[srv_pair]:
            reordered_pairs.append((srv_pair, tm1_solution[srv_pair], tm2_solution[srv_pair]))
        else:
            stable_pairs.append(srv_pair)

    return {
        'total_pairs_tm1': len(tm1_solution),
        'total_pairs_tm2': len(tm2_solution),
        'common_pairs': len(common_pairs),
        'stable_pairs': len(stable_pairs),
        'reordered_pairs': len(reordered_pairs),
        'tm1_only_pairs': len(tm1_only_pairs),
        'tm2_only_pairs': len(tm2_only_pairs),
    }


def main():
    # ============================================================================
    # CONFIGURATION: Specify the two SSP solution files to compare
    # ============================================================================
    tm1_solution_path = "Mega-logs/Uninett2010.graphml/1000-generic/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl"
    tm2_solution_path = "Mega-logs/Uninett2010.graphml/2000-generic/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl"
    # ============================================================================
    # Edit the paths above, then run: python analyze_mega_reordering.py
    # ============================================================================ 

    print(f"Analyzing Mega reordering between:")
    print(f"  TM1: {tm1_solution_path}")
    print(f"  TM2: {tm2_solution_path}")
    print()

    # Extract problem name from path
    # Expected format: Mega-logs/Uninett2010.graphml/1505250729-uniform/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl
    parts = tm1_solution_path.split('/')
    for part in parts:
        if 'graphml' in part:
            problem_name = part
            break

    print(f"Problem: {problem_name}")
    print()

    # Step 1: Load SSP solutions
    print("Step 1: Loading SSP solutions...")
    tm1_solution = load_mega_solution(tm1_solution_path)
    tm2_solution = load_mega_solution(tm2_solution_path)
    print(f"  TM1: {len(tm1_solution)} srv-srv pairs")
    print(f"  TM2: {len(tm2_solution)} srv-srv pairs")
    print()

    # Step 2: Load complete path dict and initialize fixed path_num mapping
    print("Step 2: Initializing fixed path_num mapping...")
    # edge_disjoint MUST match MEGA_HYPERPARAMS of the run being analyzed
    # (noise-compare branch: 4, False, 'inv-cap')
    complete_path_dict = load_complete_path_dict(problem_name, num_paths=4, edge_disjoint=False, dist_metric='inv-cap')
    path_to_fixed_path_num, fixed_path_num_to_path = init_fixed_path_mapping(complete_path_dict)
    print(f"  Total site_pairs in complete path: {len(complete_path_dict)}")
    print(f"  Total fixed path_nums: {len(fixed_path_num_to_path)}")
    print()

    # Step 3: Map solutions to fixed path_nums
    print("Step 3: Mapping solutions to fixed path_nums...")
    tm1_mapped = map_solution_to_fixed_path_nums(tm1_solution, path_to_fixed_path_num)
    tm2_mapped = map_solution_to_fixed_path_nums(tm2_solution, path_to_fixed_path_num)
    print(f"  TM1 mapped: {len(tm1_mapped)} srv-srv pairs")
    print(f"  TM2 mapped: {len(tm2_mapped)} srv-srv pairs")
    print()

    # Step 4: Count reordered pairs
    print("Step 4: Counting reordered srv-srv pairs...")
    stats = count_reordered_pairs(tm1_mapped, tm2_mapped)

    # Print results
    print(f"Reordered srv-srv pairs: {stats['reordered_pairs']}")


if __name__ == '__main__':
    main()
