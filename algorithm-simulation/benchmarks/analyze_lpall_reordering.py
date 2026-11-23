#!/usr/bin/env python
"""
Script to analyze srv-srv pair reordering in LP-all algorithm

Reordering definition: A srv-srv pair is "reordered" if it was assigned to one path
in TM1 but assigned to a different path in TM2.

This script:
1. Reads two ssp_dict.pkl files from LP-all algorithm
2. Extracts the path with maximum flow for each srv-srv pair
3. Compares paths between two traffic matrices
4. Counts reordered srv-srv pairs
"""

import pickle
import sys
import os
sys.path.append('..')

from lib.config import TOPOLOGIES_DIR, edge_disjoint, num_paths


def load_lpall_solution(solution_path):
    """Load LP-all's ssp_dict from pickle file"""
    with open(solution_path, 'rb') as f:
        data = pickle.load(f)
    return data


def extract_max_flow_path(ssp_dict):
    """
    Extract the path with maximum flow for each srv-srv pair

    Args:
        ssp_dict: Dict of {(srv_i, srv_j): [(flow, path), ...]}

    Returns:
        Dict of {(srv_i, srv_j): path_with_max_flow}
    """
    max_flow_paths = {}

    for srv_pair, flow_path_list in ssp_dict.items():
        if not flow_path_list:
            continue

        # Find the path with maximum flow
        max_flow_entry = max(flow_path_list, key=lambda x: x[0])
        max_flow = max_flow_entry[0]
        max_flow_path = max_flow_entry[1]

        # Convert path to tuple for comparison
        max_flow_paths[srv_pair] = tuple(max_flow_path)

    return max_flow_paths


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


def map_solution_to_fixed_path_nums(max_flow_paths, path_to_fixed_path_num):
    """
    Map LP-all's solution to fixed path_nums

    Args:
        max_flow_paths: Dict of {(srv_i, srv_j): path_tuple}
        path_to_fixed_path_num: Dict mapping tuple(path) -> fixed_path_num

    Returns:
        Dict of {(srv_i, srv_j): fixed_path_num}
    """
    mapped_solution = {}

    for srv_pair, srv_path in max_flow_paths.items():
        # srv_path format: tuple of nodes
        # For srv-srv paths, extract the site-site path (middle part)
        # srv paths typically: [srv_i, site1, ..., site_k, srv_j]

        path_list = list(srv_path)

        if len(path_list) > 2:
            # Extract middle part (sites only)
            path_key = tuple(path_list[1:-1])
        else:
            # Direct srv-srv connection
            path_key = tuple(path_list)

        if path_key in path_to_fixed_path_num:
            mapped_solution[srv_pair] = path_to_fixed_path_num[path_key]
        else:
            # Try full path as fallback
            if srv_path in path_to_fixed_path_num:
                mapped_solution[srv_pair] = path_to_fixed_path_num[srv_path]
            else:
                print(f"Warning: Path {path_key} (srv_pair {srv_pair}) not found in complete path dict")

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
        'tm2_only_pairs': len(tm2_only_pairs)
    }


def main():
    # ============================================================================
    # CONFIGURATION: Specify the two SSP solution files to compare
    # ============================================================================
    tm1_solution_path = "LP-all-logs/UsCarrier.graphml/524261695-uniform/40-per_site/UsCarrier.graphml-linear-programming_4-paths_edge-disjoint-True_dist-metric-inv-cap_ssp_dict.pkl"
    tm2_solution_path = "LP-all-logs/UsCarrier.graphml/1634997556-uniform/40-per_site/UsCarrier.graphml-linear-programming_4-paths_edge-disjoint-True_dist-metric-inv-cap_ssp_dict.pkl"
    # ============================================================================
    # Edit the paths above, then run: python analyze_lpall_reordering.py
    # ============================================================================

    print(f"Analyzing LP-all reordering between:")
    print(f"  TM1: {tm1_solution_path}")
    print(f"  TM2: {tm2_solution_path}")
    print()

    # Extract problem name from path
    # Expected format: LP-all-logs/Uninett2010.graphml/1342043743-uniform/10-per_site/...
    parts = tm1_solution_path.split('/')
    for part in parts:
        if 'graphml' in part:
            problem_name = part
            break

    print(f"Problem: {problem_name}")
    print()

    # Step 1: Load LP-all solutions
    print("Step 1: Loading LP-all solutions...")
    tm1_ssp_dict = load_lpall_solution(tm1_solution_path)
    tm2_ssp_dict = load_lpall_solution(tm2_solution_path)
    print(f"  TM1: {len(tm1_ssp_dict)} srv-srv pairs")
    print(f"  TM2: {len(tm2_ssp_dict)} srv-srv pairs")
    print()

    # Step 2: Extract maximum flow path for each srv-srv pair
    print("Step 2: Extracting maximum flow paths...")
    tm1_max_flow_paths = extract_max_flow_path(tm1_ssp_dict)
    tm2_max_flow_paths = extract_max_flow_path(tm2_ssp_dict)
    print(f"  TM1: {len(tm1_max_flow_paths)} srv-srv pairs with paths")
    print(f"  TM2: {len(tm2_max_flow_paths)} srv-srv pairs with paths")
    print()

    # Step 3: Load complete path dict and initialize fixed path_num mapping
    print("Step 3: Initializing fixed path_num mapping...")
    complete_path_dict = load_complete_path_dict(problem_name)
    path_to_fixed_path_num, fixed_path_num_to_path = init_fixed_path_mapping(complete_path_dict)
    print(f"  Total site_pairs in complete path: {len(complete_path_dict)}")
    print(f"  Total fixed path_nums: {len(fixed_path_num_to_path)}")
    print()

    # Step 4: Map solutions to fixed path_nums
    print("Step 4: Mapping solutions to fixed path_nums...")
    tm1_mapped = map_solution_to_fixed_path_nums(tm1_max_flow_paths, path_to_fixed_path_num)
    tm2_mapped = map_solution_to_fixed_path_nums(tm2_max_flow_paths, path_to_fixed_path_num)
    print(f"  TM1 mapped: {len(tm1_mapped)} srv-srv pairs")
    print(f"  TM2 mapped: {len(tm2_mapped)} srv-srv pairs")
    print()

    # Step 5: Count reordered pairs
    print("Step 5: Counting reordered srv-srv pairs...")
    stats = count_reordered_pairs(tm1_mapped, tm2_mapped)

    # Print results
    print(f"Reordered srv-srv pairs: {stats['reordered_pairs']}")


if __name__ == '__main__':
    main()
