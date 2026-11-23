#! /usr/bin/env python

from benchmark_consts import get_args_and_problems, print_, MEGA_HYPERPARAMS, TOP_HYPERPARAMS

import os
import pickle
import traceback

import sys
sys.path.append('..')

from lib.algorithms import SiteLP_Formulation
from lib.algorithms.te_objective import evaluate_assignment_objective
from lib.problem import Problem
import time
# from pyomo.environ import *
from lib.algorithms.SSP import SSP_TOP_MAIN, SSP_MAIN, SSP_PART_MAIN, SSP_ORDER_MAIN
from lib.algorithms.lp_top import TOP_MAIN
from lib.config import TL_DIR, TOPOLOGIES_DIR, PART


MEGA_DIR = 'Mega-logs'
MEGA_ORDER_DIR = 'Mega-order-logs'
TOP_MEGA_DIR = 'Top-Mega-logs'
SITE_PATH_DIR = os.path.join(TOPOLOGIES_DIR, 'paths', 'site-paths')


HEADERS = [
    'problem', 'num_nodes', 'num_edges', 'traffic_seed', 'scale_factor',
    'tm_model', 'num_commodities', 'total_demand', 'algo', 'num_paths',
    'edge_disjoint', 'dist_metric', 'server_per_site', 'total_flow',
    'SSP_satisfied_demand(%)', 'Site_LP_satisfied_demand(%)','top_runtime',
    'LP_runtime', 'SSP_runtime', 'SSP_runtime_per_path', 'total_runtime',
    'epsilon', 'loss_weight', 'obj_val'
]
PLACEHOLDER = ','.join('{}' for _ in HEADERS)


def _ssp_out_to_assignment(ssp_out):
    """Mega path format -> objective evaluator's site-tunnel format."""
    return {(i, j): tuple(path[1:-1])
            for (i, j), path in ssp_out.items()}


# Sweep topos and traffic matrices for that topo. For each combo, record the
# runtime and total flow for each algorithm
def mega_top_benchmark(problems, size, top=True, epsilon=0.1,
                       loss_weight=0.5):
    num_paths, edge_disjoint, dist_metric = MEGA_HYPERPARAMS  
    SD_list = {}
    runtime_list = {}
    with open('mega-top.csv', 'a') as results:
        print_(','.join(HEADERS), file=results)
        for problem_name, topo_fname, tm_fname in problems:

            #get original total demand
            orig_problem = Problem.from_file(topo_fname, tm_fname, top=True)
            #print_(problem.name, tm_fname)
            orig_total_demand = orig_problem.total_demand
            print('original total demand:', orig_total_demand)
            
            
            #top operation
            path_fname = os.path.join(SITE_PATH_DIR, '{}-{}-paths_edge-disjoint-{}_dist-metric-{}-dict.pkl'.format(problem_name, num_paths, edge_disjoint, dist_metric))
            print(topo_fname, tm_fname, path_fname)
            top = TOP_MAIN(topo_fname, tm_fname, path_fname)
            
            sub_list = topo_fname.split('/')
            new_path = '/'.join(sub_list[:-1] + ['Top_version'] + sub_list[-1:])
            topo_fname = new_path
            sub_list = tm_fname.split('/')
            new_path = '/'.join(sub_list[:-1] + ['Top_version'] + sub_list[-1:])
            tm_fname = new_path
            print('top operation time:', top.runtime)
            
                
            #get top problem
            problem = Problem.from_file(topo_fname, tm_fname, top=True)
            print_(problem.name, tm_fname)
            traffic_seed = problem.traffic_matrix.seed
            total_demand = problem.total_demand
            print_('traffic seed: {}'.format(traffic_seed))
            print_('traffic scale factor: {}'.format(
                problem.traffic_matrix.scale_factor))
            print_('traffic matrix model: {}'.format(
                problem.traffic_matrix.model))
            print_('total demand: {}'.format(total_demand))
            
            run_dir = os.path.join(
                TOP_MEGA_DIR, problem.name,
                '{}-{}'.format(traffic_seed, problem.traffic_matrix.model), '{}-per_site'.format(size))
            if not os.path.exists(run_dir):
                os.makedirs(run_dir)            
            

            try:
                print_(
                    '\nSite level Linear programming in mega, {} paths, edge disjoint {}, dist metric {}'
                    .format(num_paths, edge_disjoint, dist_metric))
                with open(
                        os.path.join(
                            run_dir, 
                            '{}-LP-in-mega_{}-paths_edge-disjoint-{}_dist-metric-{}.txt'
                            .format(problem.name, num_paths, edge_disjoint,
                                    dist_metric)), 'w') as log:
                    lp = SiteLP_Formulation.new_max_flow(  
                        num_paths,
                        edge_disjoint=edge_disjoint,
                        dist_metric=dist_metric,
                        out=log)
                    lp.solve(problem, top=True)
                    lp_sol_dict = lp.extract_sol_as_dict()
                    ssp_dict = lp.ssp_output()
                    with open(
                            os.path.join(
                                run_dir,
                                '{}-LP-in-mega_{}-paths_edge-disjoint-{}_dist-metric-{}_sol-dict.pkl'
                                .format(problem.name, num_paths, edge_disjoint,
                                        dist_metric)), 'wb') as w:
                        pickle.dump(lp_sol_dict, w)
                    
                    with open(
                            os.path.join(
                                run_dir, 
                                '{}-{}-LP-in-mega_ssp_input.pkl'
                                .format(problem.name, size)), 'wb') as w:
                        pickle.dump(ssp_dict, w)
                
                
                if size != 1:
                    if PART:
                        ssp_top = SSP_PART_MAIN(size,problem_name, 
                        problem.traffic_matrix.model,traffic_seed,problem.traffic_matrix.scale_factor,tm_fname)
                    else:
                        ssp_top = SSP_TOP_MAIN(size,problem_name, problem.traffic_matrix.model,
                        traffic_seed,problem.traffic_matrix.scale_factor,tm_fname)
                    
                    LP_satisfied_flow = ssp_top.LP_satisfied_flow
                    SSP_satisfied_flow = ssp_top.SSP_satisfied_flow
                    SSP_runtime = ssp_top.ssp_runtime
                    SSP_runtime_per_path = ssp_top.ssp_run_time_per_path
                    print_('LP flow:', LP_satisfied_flow, 'SSP flow:', SSP_satisfied_flow)
                    print_('SSP Satisfied Demand(%):', (SSP_satisfied_flow + orig_total_demand - total_demand) / orig_total_demand)
                    print_('LP Satisfied Demand(%):', (LP_satisfied_flow + orig_total_demand - total_demand) / orig_total_demand)
                    print_('LP runtime:', lp.runtime)  
                    print_('LP obj:', lp.obj_val)  
                    print_('total time:', top.runtime + lp.runtime + ssp_top.ssp_runtime) 
                else:
                    LP_satisfied_flow = lp.obj_val
                    SSP_satisfied_flow = lp.obj_val
                    SSP_runtime = 0.0
                    SSP_runtime_per_path = 0.0
                    print_('LP flow:', LP_satisfied_flow)
                    print_('SSP/LP Satisfied Demand(%):', (LP_satisfied_flow + orig_total_demand - total_demand) / orig_total_demand)
                    print_('LP runtime:', lp.runtime)  
                    print_('LP obj:', lp.obj_val)  
                    print_('total time:', top.runtime + lp.runtime) 
                
                result_line = PLACEHOLDER.format(
                    problem.name,
                    len(problem.G.nodes),
                    len(problem.G.edges),
                    traffic_seed,
                    problem.traffic_matrix.scale_factor,
                    problem.traffic_matrix.model,
                    len(problem.commodity_list),
                    total_demand,
                    'mega-top',
                    num_paths,
                    edge_disjoint,
                    dist_metric,
                    size,
                    lp.obj_val,
                    (SSP_satisfied_flow + orig_total_demand - total_demand) / orig_total_demand,
                    (LP_satisfied_flow + orig_total_demand - total_demand) / orig_total_demand,
                    top.runtime,                    
                    lp.runtime,
                    SSP_runtime,
                    SSP_runtime_per_path,
                    top.runtime + lp.runtime + SSP_runtime,
                    epsilon,
                    loss_weight,
                    '',
                )
                print_(result_line, file=results)
                
                if size != 1:
                    SD = (SSP_satisfied_flow+orig_total_demand-total_demand)/orig_total_demand
                    time = top.runtime+lp.runtime+ssp_top.ssp_runtime
                else:
                    SD = (LP_satisfied_flow+orig_total_demand-total_demand)/orig_total_demand
                    time = top.runtime+lp.runtime
                
                if problem.name not in SD_list:
                    SD_list[problem.name] = 0.0
                SD_list[problem.name] = SD
                
                if problem.name not in runtime_list:
                    runtime_list[problem.name] = 0.0
                runtime_list[problem.name] = time
                #print(SD, time)


            except Exception:
                print_(
                    'Site level Linear programming in Mega {} paths, edge disjoint {}, dist metric {}, Problem {}, traffic seed {}, traffic model {} failed'
                    .format(num_paths, edge_disjoint, dist_metric,
                            problem.name, traffic_seed,
                            problem.traffic_matrix.model))
                traceback.print_exc(file=sys.stdout)
            
    return (SD_list, runtime_list)             



def mega_benchmark(problems, size, top=False, epsilon=0.1,
                   loss_weight=0.5):
    num_paths, edge_disjoint, dist_metric = MEGA_HYPERPARAMS
    previous_assignment = {}
    previous_problem_name = None
    #with open('path-form.csv', 'a') as results:    
    with open('mega.csv', 'a') as results:
        print_(','.join(HEADERS), file=results)
        for problem_name, topo_fname, tm_fname in problems:               
            print(problem_name, topo_fname, tm_fname)

            if (previous_problem_name is not None and
                    previous_problem_name != problem_name):
                previous_assignment = {}
            previous_problem_name = problem_name
            
            problem = Problem.from_file(topo_fname, tm_fname, top=False)
            print_(problem.name, tm_fname)
            traffic_seed = problem.traffic_matrix.seed
            total_demand = problem.total_demand
            print_('traffic seed: {}'.format(traffic_seed))
            print_('traffic scale factor: {}'.format(
                problem.traffic_matrix.scale_factor))
            print_('traffic matrix model: {}'.format(
                problem.traffic_matrix.model))
            print_('total demand: {}'.format(total_demand))
            
            run_dir = os.path.join(
                MEGA_DIR, problem.name,
                '{}-{}'.format(traffic_seed, problem.traffic_matrix.model), '{}-per_site'.format(size))
                
            if not os.path.exists(run_dir):
                os.makedirs(run_dir)            
            

            try:
                print_(
                    '\nSite level Linear programming in mega, {} paths, edge disjoint {}, dist metric {}'
                    .format(num_paths, edge_disjoint, dist_metric))
                with open(
                        os.path.join(
                            run_dir, 
                            '{}-LP-in-mega_{}-paths_edge-disjoint-{}_dist-metric-{}.txt'
                            .format(problem.name, num_paths, edge_disjoint,
                                    dist_metric)), 'w') as log:
                    lp = SiteLP_Formulation.new_max_flow(  
                        num_paths,
                        edge_disjoint=edge_disjoint,
                        dist_metric=dist_metric,
                        out=log)
                    lp.solve(problem, top=False)
                    lp_sol_dict = lp.extract_sol_as_dict()
                    ssp_dict = lp.ssp_output()
                    with open(
                            os.path.join(
                                run_dir,
                                '{}-LP-in-mega_{}-paths_edge-disjoint-{}_dist-metric-{}_sol-dict.pkl'
                                .format(problem.name, num_paths, edge_disjoint,
                                        dist_metric)), 'wb') as w:
                        pickle.dump(lp_sol_dict, w)
                    
                    with open(
                            os.path.join(
                                run_dir, 
                                '{}-{}-LP-in-mega_ssp_input.pkl'
                                .format(problem.name, size)), 'wb') as w:
                        pickle.dump(ssp_dict, w)
                
                # print(ssp_dict)
                ssp = SSP_MAIN(size,problem_name, problem.traffic_matrix.model,traffic_seed,problem.traffic_matrix.scale_factor,tm_fname)
                
                LP_satisfied_flow = ssp.LP_satisfied_flow
                SSP_satisfied_flow = ssp.SSP_satisfied_flow
                print_('LP flow:', LP_satisfied_flow, 'SSP flow:', SSP_satisfied_flow)
                print_('SSP Satisfied Demand(%):', SSP_satisfied_flow / total_demand)
                print_('LP Satisfied Demand(%):', LP_satisfied_flow / total_demand)
                print_('LP runtime:', lp.runtime)  
                print_('LP obj:', lp.obj_val)  
                print_('total time:', lp.runtime + ssp.ssp_runtime) 

                current_assignment = _ssp_out_to_assignment(ssp.out)
                objective = evaluate_assignment_objective(
                    current_assignment, previous_assignment, ssp.tm,
                    problem.G, epsilon=epsilon,
                    loss_weight=loss_weight)
                print_('Exact-objective value:', objective['obj_val'])
                
                result_line = PLACEHOLDER.format(
                    problem.name,
                    len(problem.G.nodes),
                    len(problem.G.edges),
                    traffic_seed,
                    problem.traffic_matrix.scale_factor,
                    problem.traffic_matrix.model,
                    len(problem.commodity_list),
                    total_demand,
                    'mega',
                    num_paths,
                    edge_disjoint,
                    dist_metric,
                    size,
                    lp.obj_val,
                    SSP_satisfied_flow / total_demand,
                    LP_satisfied_flow / total_demand,
                    0.0,                    
                    lp.runtime,
                    ssp.ssp_runtime,
                    ssp.ssp_run_time_per_path,
                    lp.runtime + ssp.ssp_runtime,
                    epsilon,
                    loss_weight,
                    objective['obj_val'],
                )
                print_(result_line, file=results)
                previous_assignment = current_assignment
                

            except Exception:
                print_(
                    'Site level Linear programming in Mega {} paths, edge disjoint {}, dist metric {}, Problem {}, traffic seed {}, traffic model {} failed'
                    .format(num_paths, edge_disjoint, dist_metric,
                            problem.name, traffic_seed,
                            problem.traffic_matrix.model))
                traceback.print_exc(file=sys.stdout)


def mega_order_benchmark(problems, size, top=False, lp_source_dir=None,
                         epsilon=0.1, loss_weight=0.5):
    """
    Mega with order-preserving SSP to minimize reordering across TM matrices

    Args:
        problems: List of (problem_name, topo_fname, tm_fname) tuples
        size: Number of servers per site
        top: Whether to use TOP preprocessing (always False for mega-order)
        lp_source_dir: if set (e.g. 'Mega-logs'), reuse the site-level LP
            products saved by a previous run instead of solving a fresh LP.
            This pins the per-tunnel budget F_{k,t} so reordering comparisons
            across algorithms are not confounded by the LP solver's
            (degenerate, run-varying) choice of F split. No LP is solved in
            this run: LP runtime is reported as 0.0 and the LP objective is
            recomputed as the total allocated flow. Run the source algorithm
            first with the same problem/slices/size (e.g.
            Run_all.py --algo mega --slices 0 5 --server 10).
    """
    num_paths, edge_disjoint, dist_metric = MEGA_HYPERPARAMS

    # Initialize previous_solution to track state across TM matrices
    previous_solution = {}
    previous_objective_assignment = {}
    previous_problem_name = None

    with open('mega-order.csv', 'a') as results:
        print_(','.join(HEADERS), file=results)

        for idx, (problem_name, topo_fname, tm_fname) in enumerate(problems):
            print(f"\n{'='*60}")
            print(f"Processing TM matrix {idx+1}/{len(problems)}: {problem_name}")
            print(f"{'='*60}\n")

            # Reset previous_solution when problem changes
            if previous_problem_name is not None and previous_problem_name != problem_name:
                print(f"Problem changed from '{previous_problem_name}' to '{problem_name}', resetting history")
                previous_solution = {}
                previous_objective_assignment = {}


            previous_problem_name = problem_name

            # Load problem (no TOP preprocessing)
            problem = Problem.from_file(topo_fname, tm_fname, top=False)
            print_(problem.name, tm_fname)

            traffic_seed = problem.traffic_matrix.seed
            total_demand = problem.total_demand

            print_('traffic seed: {}'.format(traffic_seed))
            print_('traffic scale factor: {}'.format(problem.traffic_matrix.scale_factor))
            print_('traffic model: {}'.format(problem.traffic_matrix.model))
            print_('total demand: {}'.format(total_demand))

            # Load complete path dict file path (for first TM or when problem changes)
            complete_path_fname = os.path.join(SITE_PATH_DIR,
                    '{}-{}-paths_edge-disjoint-{}_dist-metric-{}-dict.pkl'
                    .format(problem_name, num_paths, edge_disjoint, dist_metric))


            # Create run directory
            run_dir = os.path.join(
                MEGA_ORDER_DIR,
                problem.name,
                '{}-{}'.format(traffic_seed, problem.traffic_matrix.model),
                '{}-per_site'.format(size))

            if not os.path.exists(run_dir):
                os.makedirs(run_dir)
            
            try:
                if lp_source_dir:
                    # Controlled-comparison mode: reuse the LP products of a
                    # previous run so both algorithms face the same F_{k,t}
                    src_dir = os.path.join(
                        lp_source_dir, problem.name,
                        '{}-{}'.format(traffic_seed, problem.traffic_matrix.model),
                        '{}-per_site'.format(size))
                    src_ssp_fname = os.path.join(
                        src_dir, '{}-{}-LP-in-mega_ssp_input.pkl'.format(problem.name, size))
                    print_('\nReusing site-level LP products from {}'.format(src_ssp_fname))
                    with open(src_ssp_fname, 'rb') as r:
                        ssp_dict = pickle.load(r)
                    lp_runtime = 0.0
                    lp_obj = sum(flow for items in ssp_dict.values()
                                 for (flow, _) in items)
                    algo_label = 'mega-order-sharedLP'

                    with open(os.path.join(run_dir,
                        '{}-LP-in-mega_{}-paths_edge-disjoint-{}_dist-metric-{}.txt'
                        .format(problem.name, num_paths, edge_disjoint,
                                dist_metric)), 'w') as log:
                        log.write('LP solution reused from {}\n'.format(src_ssp_fname))

                    # copy the LP sol-dict from the source run for parity, if present
                    src_sol_fname = os.path.join(
                        src_dir, '{}-LP-in-mega_{}-paths_edge-disjoint-{}_dist-metric-{}_sol-dict.pkl'
                        .format(problem.name, num_paths, edge_disjoint, dist_metric))
                    if os.path.exists(src_sol_fname):
                        with open(src_sol_fname, 'rb') as r:
                            lp_sol_dict = pickle.load(r)
                        with open(os.path.join(run_dir,
                            '{}-LP-in-mega_{}-paths_edge-disjoint-{}_dist-metric-{}_sol-dict.pkl'
                            .format(problem.name, num_paths, edge_disjoint,
                                    dist_metric)), 'wb') as w:
                            pickle.dump(lp_sol_dict, w)

                    with open(os.path.join(run_dir,
                        '{}-{}-LP-in-mega_ssp_input.pkl'
                        .format(problem.name, size)), 'wb') as w:
                        pickle.dump(ssp_dict, w)
                else:
                    # Site-level LP (same as MegaTop)
                    print_('\nSite level Linear programming in mega-order, {} paths, edge disjoint {}, dist metric {}'
                        .format(num_paths, edge_disjoint, dist_metric))

                    with open(os.path.join(run_dir,
                        '{}-LP-in-mega_{}-paths_edge-disjoint-{}_dist-metric-{}.txt'
                        .format(problem.name, num_paths, edge_disjoint, dist_metric)), 'w') as log:

                        lp = SiteLP_Formulation.new_max_flow(
                            num_paths,
                            edge_disjoint=edge_disjoint,
                            dist_metric=dist_metric,
                            out=log)

                        lp.solve(problem, top=False)
                        lp_sol_dict = lp.extract_sol_as_dict()
                        ssp_dict = lp.ssp_output()

                        with open(os.path.join(run_dir,
                            '{}-LP-in-mega_{}-paths_edge-disjoint-{}_dist-metric-{}_sol-dict.pkl'
                            .format(problem.name, num_paths, edge_disjoint, dist_metric)), 'wb') as w:
                            pickle.dump(lp_sol_dict, w)

                        with open(os.path.join(run_dir,
                            '{}-{}-LP-in-mega_ssp_input.pkl'
                            .format(problem.name, size)), 'wb') as w:
                            pickle.dump(ssp_dict, w)

                    lp_runtime = lp.runtime
                    lp_obj = lp.obj_val
                    algo_label = 'mega-order'

                #import pdb; pdb.set_trace()

                # Server-level SSP with historical awareness
                print('\n--- Server-level SSP (Order-Preserving) ---')
                ssp = SSP_ORDER_MAIN(
                    size, problem_name, problem.traffic_matrix.model,
                    traffic_seed, problem.traffic_matrix.scale_factor,
                    tm_fname,
                    previous_solution=previous_solution,
                    complete_path_fname=complete_path_fname
                )

                LP_satisfied_flow = ssp.LP_satisfied_flow
                SSP_satisfied_flow = ssp.SSP_satisfied_flow

                print_('LP flow:', LP_satisfied_flow, 'SSP flow:', SSP_satisfied_flow)
                print_('SSP Satisfied Demand(%):', SSP_satisfied_flow / total_demand)
                print_('LP Satisfied Demand(%):', LP_satisfied_flow / total_demand)
                print_('LP runtime:', lp_runtime)
                print_('LP obj:', lp_obj)
                print_('total time:', lp_runtime + ssp.ssp_runtime)
                print_('total reordered srv-srv pairs', ssp.total_deleted_pairs_used)

                current_objective_assignment = _ssp_out_to_assignment(ssp.out)
                objective = evaluate_assignment_objective(
                    current_objective_assignment,
                    previous_objective_assignment, ssp.tm, problem.G,
                    epsilon=epsilon, loss_weight=loss_weight)
                print_('Exact-objective value:', objective['obj_val'])


                result_line = PLACEHOLDER.format(
                    problem.name,
                    len(problem.G.nodes),
                    len(problem.G.edges),
                    traffic_seed,
                    problem.traffic_matrix.scale_factor,
                    problem.traffic_matrix.model,
                    len(problem.commodity_list),
                    total_demand,
                    algo_label,
                    num_paths,
                    edge_disjoint,
                    dist_metric,
                    size,
                    lp_obj,
                    SSP_satisfied_flow / total_demand,
                    LP_satisfied_flow / total_demand,
                    0.0,
                    lp_runtime,
                    ssp.ssp_runtime,
                    ssp.ssp_run_time_per_path,
                    lp_runtime + ssp.ssp_runtime,
                    epsilon,
                    loss_weight,
                    objective['obj_val'],
                )

                print_(result_line, file=results)

                #pdb.set_trace()

                # Store current solution for next iteration
                previous_solution = ssp.extract_solution()
                previous_objective_assignment = current_objective_assignment

                # Save previous_solution to txt file for debugging
                # import pprint
                # prev_sol_fname = os.path.join(run_dir, 'previous_solution.txt')
                # with open(prev_sol_fname, 'w') as f:
                #     pprint.pprint(previous_solution, f, width=200, compact=False)
                # print(f"  Saved previous_solution to {prev_sol_fname}")

                print(f"\nCompleted TM matrix {idx+1}/{len(problems)}")
                print(f"Stability info: {len(previous_solution)} site pairs processed\n")

            except Exception as e:
                print_(
                    'Site level Linear programming in Mega-Order {} paths, edge disjoint {}, dist metric {}, Problem {}, traffic seed {}, traffic model {} failed'
                    .format(num_paths, edge_disjoint, dist_metric,
                            problem.name, traffic_seed,
                            problem.traffic_matrix.model))
                traceback.print_exc(file=sys.stdout)


if __name__ == '__main__':
    if not os.path.exists(MEGA_DIR):
        os.makedirs(MEGA_DIR)
    
    #if len(sys.argv) == 2 and sys.arv[2] == 'triangle':
    #problems = get_tri_problem()
    #benchmarks_tri(problems)

    args, size, problems = get_args_and_problems()
    #print(size)
    #print(problems)
    if args.dry_run:   # no actual move
        print('Problems to run:')
        for problem in problems:
            print(problem)
    else:
        benchmark(problems,size)
