#Add lp-top on v3.1
#Add progress bar
import math
import numpy as np
import pickle
import time
import os
from alive_progress import alive_bar
from heapq import heappush, heappop
import os
from lib.config import TL_DIR, TOPOLOGIES_DIR, TM_DIR, edge_disjoint, num_paths
from benchmarks.benchmark_consts import TOP_HYPERPARAMS


class SSP():
    def __init__(self, tm, clas, path,  ref_table, delay = 10, epsilon = 0.05, clas_mode = False, top_mode = True, debug = False):
        self.epsilon = epsilon
        self.threads_num = 14
        self.pf = []
        self.top_lp = TOP_HYPERPARAMS 
        self.top_flag = top_mode
        self.tm = tm
        self.clas_mode = clas_mode
        if delay == 0:
            self.delay_flag = False
        else:
            self.delay_flag = True
        self.clas = clas
        self.delay = delay
        self.dpt = 0
        self.ct = 0
        self.gt = 0
        self.out = {}
        self.lrts = {
            'dp':[],
            'ga':[],
            'tt':[]
        }
        self.path = path
        self.path_list = []
        self.flow_list = []
        self.ref_table = ref_table
        self.debug = debug
        self.node_num = len(ref_table)
        self.result_table = np.zeros((self.node_num, self.node_num))
        np.ndarray.fill(self.result_table, -1)
        self.inv_table = []
        self.inv_cluster = []
        self.init_inverse_table()
        self.init_path_demand_list()
        self.flow_sum = sum(self.flow_list)
        
    def other_top(self):
        for index, (flow, path) in enumerate(self.pf[int(len(self.pf)*self.top_lp):]):
            ind = index + int(len(self.pf)*self.top_lp)
            for i in self.inv_table[path[0]]:
                for j in self.inv_table[path[-1]]:
                    if self.result_table[i,j] != -1:
                        continue
                    if (self.ref_table[i],self.ref_table[j]) not in self.path:
                        continue
                    if self.tm[i,j] < flow:
                        flow -= self.tm[i,j]
                        self.result_table[i,j] = ind

    def init_inverse_table(self):
        for srv_id, site_id in enumerate(self.ref_table):
            if site_id == -1:
                self.inv_table.append([])
                continue
            else:
                self.inv_table[site_id].append(srv_id)
    
    def init_path_demand_list(self):

        for path_data in self.path.values():
            for (flow, path) in path_data:
                self.pf.append((flow, path))   # flow是指site-site上一个tunnel分配的带宽值

        self.pf.sort() # 按照升序排序
        for (flow, path) in self.pf:          
            self.path_list.append(path)       # path_list [[73, 72, 71]...] 
            self.flow_list.append(flow)       # flow_list [0.7856539487838745...]
        
    def single_ssp(self, site_flow, site_pair, path_num):
        def next_tm(srv_pair):
            if srv_pair[1] == self.inv_table[site_pair[1]][-1]:
                return (srv_pair[0] + 1, self.inv_table[site_pair[1]][0])
            else:
                return (srv_pair[0], srv_pair[1] + 1)

        act = time.time()
        #tm_table = np.zeros((self.node_num, self.node_num, 3))
        cluster_board = self.epsilon * site_flow /3
        delta = cluster_board * (self.epsilon /3)
        if self.debug:
            print(f"------------ SSP {path_num} ------------")
            print("site pair:", site_pair)
            print("srv board:" + str(cluster_board))
            print("site flow:" + str(site_flow))
            '''
            srv_sum = 0
            for i in self.inv_table[site_pair[0]]:
                for j in self.inv_table[site_pair[1]]:
                    pass#srv_sum += self.tm[i,j]
            print("srv mean:" + str(srv_sum/(len(self.inv_table[site_pair[0]])*len(self.inv_table[site_pair[1]]))))
            '''
        #import pdb; pdb.set_trace()
        
        cluster_srv = []
        cluster_srv_sum = []
        sum = 0
        for i in self.inv_table[site_pair[0]]:
            for j in self.inv_table[site_pair[1]]:
                if self.result_table[i,j] != -1: 
                    continue
                if (self.ref_table[i],self.ref_table[j]) not in self.path:
                    continue
                sum += self.tm[i,j]
                if sum >= cluster_board:
                    cluster_srv.append((i,j))
                    cluster_srv_sum.append(sum)
                    sum = 0
                else:
                    pass
                    #cluster_srv[len(cluster_srv_sum)].append((i,j))
        bct = time.time()

            #tm_table[i,j,0] = len(cluster_srv)
            #cluster_srv.append(sum)
        if cluster_srv_sum == []:
            if self.debug:
                print("No demand left")
            return
        if self.debug:
            print("cluster srv num:", len(cluster_srv_sum))
            #print("cluster srv mean:", np.mean(cluster_srv))
        
        #pdb.set_trace()

        res_srv = []
        dp_srv =[]
        scaled_dp_srv = []
        dp2cluster = []
        res2cluster = []
        for index, c_srv in enumerate(cluster_srv_sum):
            if c_srv <= cluster_board:
                #tm_table[i,j,1] = len(res_srv)
                res_srv.append(c_srv)
                res2cluster.append(index)    # 我理解这个地方应该不会有符合条件的值 
            else:
                #tm_table[i,j,2] = len(dp_srv)
                dp_srv.append(c_srv)
                scaled_dp_srv.append(math.ceil(c_srv/delta))
                dp2cluster.append(index)
        
        #pdb.set_trace()

        # 0/1背包问题的动态规划求解，选择一些server pairs，使其总流量尽可能接近 site_flow，但不超过

        f = np.zeros((len(scaled_dp_srv) + 1,math.floor(site_flow/delta) + 1))
        s = np.zeros((math.floor(site_flow/delta) + 1,len(scaled_dp_srv) + 1))
        adp = time.time()
        for item in range(len(scaled_dp_srv)):
            for bagg in range(math.floor(site_flow/delta)):
                i = item + 1
                j = bagg + 1
                if j < scaled_dp_srv[item]:
                    f[i][j] = f[i - 1][j]
                else:
                    if f[i - 1][j] >= f[i - 1][j - scaled_dp_srv[item]] + scaled_dp_srv[item]:
                        f[i][j] = f[i - 1][j]
                        s[j][i] = 0
                    else:
                        s[j][i] = 1
                        s[j][:i] = s[j - scaled_dp_srv[item]][:i]
                        f[i][j] = f[i - 1][j - scaled_dp_srv[item]] + scaled_dp_srv[item]
        bdp = time.time()
        agt = time.time()
        dp_srv_sum = 0
        add_tm = 0

        # 将DP算法选中的"聚类server pairs"转换回"实际的server编号"，并更新分配表。

        for index in range(len(s[math.floor(site_flow/delta)][1:])):
            if s[math.floor(site_flow/delta)][1:][index] == 1:
                dp_srv_sum += dp_srv[index]
                (endi, endj) = next_tm(cluster_srv[dp2cluster[index]])
                if dp2cluster[index] == 0:
                    (starti, startj) = (self.inv_table[site_pair[0]][0], self.inv_table[site_pair[1]][0])
                else:
                    (starti, startj) = next_tm(cluster_srv[dp2cluster[index] - 1])
                for i in range(starti, endi + 1):
                    if i == starti and i == endi:
                        var_startj = startj
                        var_end = endj
                    elif i == starti:
                        var_startj = startj
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    elif i == endi:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = endj
                    else:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    for j in range(var_startj, var_end):
                        self.result_table[i,j] = path_num
                        self.flow_list[path_num] -= self.tm[i,j]
                        add_tm += 1
        
        #利用贪心算法处理剩余带宽，但剩余带宽压根就没处理
        bgt = time.time()
        res_demand = site_flow - dp_srv_sum
        res_srv.sort(reverse=True)
        for index, r_srv in enumerate(res_srv):
            if r_srv < res_demand:
                #rr += 1
                (endi, endj) = next_tm(cluster_srv[res2cluster[index]])
                if res2cluster[index] == 0:
                    (starti, startj) = (self.inv_table[site_pair[0]][0], self.inv_table[site_pair[1]][0])
                else:
                    (starti, startj) = next_tm(cluster_srv[res2cluster[index] - 1]) #(starti, startj) = next_tm(cluster_srv[dp2cluster[index] - 1])
                for i in range(starti, endi + 1):
                    if i == starti and i == endi:
                        var_startj = startj
                        var_end = endj
                    elif i == starti:
                        var_startj = startj
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    elif i == endi:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = endj
                    else:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    for j in range(var_startj, var_end):
                        self.result_table[i,j] = path_num
                        self.flow_list[path_num] -= self.tm[i,j]
                        add_tm += 1

        # 将贪心算法选中的"聚类server pairs"转换回"实际的server编号"，并更新分配表
        for index in range(len(s[math.floor(site_flow/delta)][1:])):
            if s[math.floor(site_flow/delta)][1:][index] == 0:
                dp_srv_sum += dp_srv[index]
                (endi, endj) = cluster_srv[dp2cluster[index]]
                endj += 1
                if dp2cluster[index] == 0:
                    (starti, startj) = (self.inv_table[site_pair[0]][0], self.inv_table[site_pair[1]][0])
                else:
                    (starti, startj) = cluster_srv[dp2cluster[index] - 1]
                    startj += 1
                for i in range(starti, endi + 1):
                    if i == starti and i == endi:
                        var_startj = startj
                        var_end = endj
                    elif i == starti:
                        var_startj = startj
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    elif i == endi:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = endj
                    else:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    for j in range(var_startj, var_end):
                        if self.tm[i,j] < self.flow_list[path_num]:
                            self.result_table[i,j] = path_num
                            self.flow_list[path_num] -= self.tm[i,j]
                            add_tm += 1

        self.dpt += bdp - adp
        self.ct += bct - act
        self.gt += bgt - agt
        self.lrts['dp'].append(bdp - adp)
        self.lrts['ga'].append(bgt - agt)
        self.lrts['tt'].append(bdp - adp + bct - act + bgt - agt)
        if self.debug:
            print('DP time:', bdp - adp)
            print('Cluster time:', bct - act)
            print('GA time:', bgt - agt)
            print('Singal time:', bdp - adp + bct - act + bgt - agt)
            print('Added server demand:', add_tm)
            print(f'Total flow:{site_flow}, res flow:{res_demand}, srv num:{(len(self.inv_table[site_pair[0]]), len(self.inv_table[site_pair[0]]))}')

    def class_greedy(self, clas_num):
        for i in range(self.node_num):
            for j in range(self.node_num):
                if self.ref_table[i] == -1 or self.ref_table[j] == -1 or self.ref_table[i] == self.ref_table[j]:
                    continue
                if (self.ref_table[i],self.ref_table[j]) not in self.path:
                    continue
                if self.clas[i,j] == clas_num:
                    m_path = ''
                    if self.delay_flag == True:
                        mini_delay = 1000000
                        for _, site_p in self.path[(self.ref_table[i],self.ref_table[j])]:
                            if mini_delay > self.delay(str(site_p)) and self.flow_list[self.path_list.index(site_p)] < self.tm[i,j]:
                                m_path = site_p
                    else:
                        for (_, site_p) in self.path[(self.ref_table[i],self.ref_table[j])]:
                            if self.flow_list[self.path_list.index(site_p)] > self.tm[i,j]:
                                m_path = site_p
                                break
                    path_pos = self.path_list.index(m_path)
                    self.flow_list[path_pos] -= self.tm[i,j]
                    self.result_table[i,j] = path_pos
    
    
    def show_class_delay(self):
        class_average_delay = {}
        class_delay_num = {}
        for i in range(self.node_num[0]):
            for j in range(self.node_num[1]):
                if self.result_table[i,j] != -1:
                    if str(self.clas[i,j]) in class_average_delay:
                        class_average_delay[str(self.clas[i,j])] += len(self.path_list[int(self.result_table[i,j])])
                        class_delay_num[str(self.clas[i,j])] += 1
                    else:
                        class_average_delay[str(self.clas[i,j])] = len(self.path_list[int(self.result_table[i,j])])
                        class_delay_num[str(self.clas[i,j])] = 1
        for key in class_average_delay.keys:
            class_average_delay[key] /= class_delay_num[key]
        print('delay:', class_average_delay)
    
    
    

    def solve(self):
        print('------------ SSP Enable ------------')
        if self.debug:
            print('path list:', self.path_list)
        print('Total path num:', len(self.path_list))
        print('Total node num:', self.node_num)
        if self.clas_mode == True:
            for i in range(1):
                print(f'------------ Class {i} ------------')
                self.class_greedy(i)
        if self.top_flag == True:
            with alive_bar(len(self.flow_list[:int(len(self.pf)*self.top_lp)])) as bar:
                for path_num, flow in enumerate(self.flow_list[:int(len(self.pf)*self.top_lp)]):
                        self.single_ssp(flow, (self.path_list[path_num][0],self.path_list[path_num][-1]), path_num)
                        bar()
        else:
            with alive_bar(len(self.flow_list)) as bar:
                for path_num, flow in enumerate(self.flow_list):
                        self.single_ssp(flow, (self.path_list[path_num][0],self.path_list[path_num][-1]), path_num)
                        bar()
        if self.top_flag == True:
            self.other_top()
        #self.show_class_delay()

    def output(self, output_dict=None):
        # never use a mutable default: chained TM runs in one process would
        # accumulate earlier TMs' entries into this TM's ssp_out (same fix
        # as SSP_ORDER_MAIN.output below)
        if output_dict is None:
            output_dict = {}
        for i in range(self.node_num):
            for j in range(self.node_num):
                if self.result_table[i,j] == -1:
                    continue
                srv_pair = (i,j)
                srv_path = [i] + self.path_list[int(self.result_table[i,j])] + [j]
                output_dict[srv_pair] = srv_path
            self.out = output_dict
        if self.debug:
            print('------------ output ------------')
            #print(output_dict)
    
    def save(self, file_path, filename):
        if filename.endswith('ssp_solution.pkl'):
            print('WARN: The file may be overwritten with the same name')
        if self.out == {}:
            print('ERROR: No output produced')
        else:
            with open(file_path + '/' + filename, 'wb') as f:
                pickle.dump(self.out, f)
    
    def pathnum(self):
        return len(self.flow_list)
    
    def total_demand(self):
        td = 0
        for i in range(self.node_num):
            for j in range(self.node_num):
                if (self.ref_table[i],self.ref_table[j]) not in self.path:
                    continue
                if self.result_table[i,j] != -1:
                    td += self.tm[i,j]
        return td

    def tm_sum(self):
        ts = 0
        for num in range(self.node_num):
            if self.ref_table[num] != -1:
                index = num
                break
        for i in range(index, self.node_num):
            for j in range(index, self.node_num):
                ts += self.tm[i,j]
        return ts

    def runtime(self):
    
        def part_runtime(part):
            self.lrts[part].sort(reverse=True)
            h = []
            for rt in self.lrts[part][:self.threads_num]:
                heappush(h, rt)
            curr_rt = 0
            for rt in self.lrts[part][self.threads_num:]:
                curr_rt = heappop(h)
                heappush(h, rt + curr_rt)
            while len(h) > 0:
                curr_rt = heappop(h)
            return curr_rt
        
        dp_rt = part_runtime('dp')
        ga_rt = part_runtime('ga')
        if self.debug:
            print('DP est time:', dp_rt)
            print('GA est time:', ga_rt)
        total_rt = part_runtime('tt')
        return total_rt

# to deal with the problem of Memory overflow, use SSP_PART to read and
# calculate a series of partitial TM 
        
class SSP_PART:
    def __init__(self,
                 tm_path,
                 path_path,
                 ref_table_path,
                 clas_path = "",
                 delay_path = "",
                 epsilon = 0.1,
                 delay_mode = False,
                 clas_mode = False,
                 top_mode = True,
                 debug = False,
                 start_site_pair = (0,0)):
        
        self.threads_num = 16
        self.top_lp = 0.1
        self.top_flag = top_mode
        self.clas_mode = clas_mode
        self.delay_flag = delay_mode
        self.epsilon = epsilon

        self.dpt = 0
        self.ct = 0
        self.gt = 0
        self.pf = []
        self.out = {}
        self.lrts = {
            "dp":[],
            "ga":[],
            "tt":[]
        }
        self.path_list = []
        self.flow_list = []
        self.part_previous_path = 0
        self.debug = debug
        self.inv_table = []
        self.inv_cluster = []
        if clas_mode:
            self.clas = self.from_file(clas_path)
        if delay_mode:
            self.delay = self.from_file(delay_path)
        self.ref_table = self.from_file(ref_table_path)
        self.tm = self.from_file(tm_path)
        self.node_num = (len(self.tm[:,0]),len(self.tm[0,:]))
        self.path = self.from_file(path_path)
        self.result_table = np.zeros((self.node_num[0] + 1, self.node_num[1] + 1))
        np.ndarray.fill(self.result_table, -1)
        self.init_inverse_table()
        self.init_path_demand_list()
        self.start_site_pair = start_site_pair
        self.start_srv_pair = (self.inv_table[self.start_site_pair[0]][0], self.inv_table[self.start_site_pair[1]][0])

    def other_top(self):
        with alive_bar(len(self.pf[int(len(self.pf)*self.top_lp):])) as bar:
            for index, (flow, path) in enumerate(self.pf[int(len(self.pf)*self.top_lp):]):
                ind = index + int(len(self.pf)*self.top_lp)
                for i in self.inv_table[path[0]]:
                    for j in self.inv_table[path[-1]]:
                        if self.result_table[i, j] != -1:
                            continue
                        if (self.ref_table[i],self.ref_table[j]) not in self.path:
                            continue
                        if self.tm[i, j] < flow:
                            flow -= self.tm[i, j]
                            self.result_table[i, j] = ind
            bar()

    def init_inverse_table(self):
        for srv_id, site_id in enumerate(self.ref_table):
            if site_id == -1:
                self.inv_table.append([])
                continue
            else:
                self.inv_table[site_id].append(srv_id)

    def flow_sum(self):
        f_s = 0
        for path_data in self.path.values():
            for (flow, _) in path_data:
                f_s += flow
        return f_s

    def init_path_demand_list(self):

        for path_data in self.path.values():
            for (flow, path) in path_data:
                self.pf.append((flow, path))

        self.pf.sort()
        for (flow, path) in self.pf:
            self.path_list.append(path)
            self.flow_list.append(flow)
        
    def single_ssp(self, site_flow, site_pair, path_num):
        def next_tm(srv_pair):
            if srv_pair[1] == self.inv_table[site_pair[1]][-1]:
                return (srv_pair[0] + 1, self.inv_table[site_pair[1]][0])
            else:
                return (srv_pair[0], srv_pair[1] + 1)

        act = time.time()
        #tm_table = np.zeros((self.node_num, self.node_num, 3))
        cluster_board = self.epsilon * site_flow /3
        delta = cluster_board * (self.epsilon /3)
        if self.debug:
            print(f"------------ Path ID {path_num} ------------")
            print("site pair:", site_pair)
            print("srv board:" + str(cluster_board))
            print("site flow:" + str(site_flow))
            '''
            srv_sum = 0
            for i in self.inv_table[site_pair[0]]:
                for j in self.inv_table[site_pair[1]]:
                    pass#srv_sum += self.tm[i,j]
            print("srv mean:" + str(srv_sum/(len(self.inv_table[site_pair[0]])*len(self.inv_table[site_pair[1]]))))
            '''
        
        cluster_srv = []
        cluster_srv_sum = []
        sum = 0
        
        for i in self.inv_table[site_pair[0]]:
            for j in self.inv_table[site_pair[1]]:
                
                if self.result_table[i - self.start_srv_pair[0], j - self.start_srv_pair[1]] != -1: 
                    continue
                if (self.ref_table[i],self.ref_table[j]) not in self.path:
                    continue
                sum += self.tm[i - self.start_srv_pair[0], j - self.start_srv_pair[1]]
                if sum >= cluster_board:
                    cluster_srv.append((i,j))
                    cluster_srv_sum.append(sum)
                    sum = 0
                else:
                    pass
                    #cluster_srv[len(cluster_srv_sum)].append((i,j))
        bct = time.time()

            #tm_table[i,j,0] = len(cluster_srv)
            #cluster_srv.append(sum)
        if cluster_srv_sum == []:
            if self.debug:
                print("No demand left")
            return
        if self.debug:
            print("cluster srv num:", len(cluster_srv_sum))
            #print("cluster srv mean:", np.mean(cluster_srv))

        res_srv = []
        dp_srv =[]
        scaled_dp_srv = []
        dp2cluster = []
        res2cluster = []
        for index, c_srv in enumerate(cluster_srv_sum):
            if c_srv <= cluster_board:
                #tm_table[i,j,1] = len(res_srv)
                res_srv.append(c_srv)
                res2cluster.append(index)
            else:
                #tm_table[i,j,2] = len(dp_srv)
                dp_srv.append(c_srv)
                scaled_dp_srv.append(math.ceil(c_srv/delta))
                dp2cluster.append(index)
        
        
        f = np.zeros((len(scaled_dp_srv) + 1,math.floor(site_flow/delta) + 1))
        s = np.zeros((math.floor(site_flow/delta) + 1,len(scaled_dp_srv) + 1))
        adp = time.time()
        for item in range(len(scaled_dp_srv)):
            for bagg in range(math.floor(site_flow/delta)):
                i = item + 1
                j = bagg + 1
                if j < scaled_dp_srv[item]:
                    f[i][j] = f[i - 1][j]
                else:
                    if f[i - 1][j] >= f[i - 1][j - scaled_dp_srv[item]] + scaled_dp_srv[item]:
                        f[i][j] = f[i - 1][j]
                        s[j][i] = 0
                    else:
                        s[j][i] = 1
                        s[j][:i] = s[j - scaled_dp_srv[item]][:i]
                        f[i][j] = f[i - 1][j - scaled_dp_srv[item]] + scaled_dp_srv[item]
        bdp = time.time()
        agt = time.time()
        dp_srv_sum = 0
        add_tm = 0

        for index in range(len(s[math.floor(site_flow/delta)][1:])):
            if s[math.floor(site_flow/delta)][1:][index] == 1:
                dp_srv_sum += dp_srv[index]
                (endi, endj) = next_tm(cluster_srv[dp2cluster[index]])
                if dp2cluster[index] == 0:
                    (starti, startj) = (self.inv_table[site_pair[0]][0], self.inv_table[site_pair[1]][0])
                else:
                    (starti, startj) = next_tm(cluster_srv[dp2cluster[index] - 1])
                for i in range(starti, endi + 1):
                    if i == starti and i == endi:
                        var_startj = startj
                        var_end = endj
                    elif i == starti:
                        var_startj = startj
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    elif i == endi:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = endj
                    else:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    for j in range(var_startj, var_end):
                        self.result_table[i - self.start_srv_pair[0],j - self.start_srv_pair[1]] = path_num
                        self.flow_list[path_num] -= self.tm[i - self.start_srv_pair[0],j - self.start_srv_pair[1]]
                        add_tm += 1
        

        bgt = time.time()
        res_demand = site_flow - dp_srv_sum
        res_srv.sort(reverse=True)
        for index, r_srv in enumerate(res_srv):
            if r_srv < res_demand:
                #rr += 1
                (endi, endj) = next_tm(cluster_srv[res2cluster[index]])
                if res2cluster[index] == 0:
                    (starti, startj) = (self.inv_table[site_pair[0]][0], self.inv_table[site_pair[1]][0])
                else:
                    (starti, startj) = next_tm(cluster_srv[res2cluster[index] - 1]) #(starti, startj) = next_tm(cluster_srv[dp2cluster[index] - 1])
                for i in range(starti, endi + 1):
                    if i == starti and i == endi:
                        var_startj = startj
                        var_end = endj
                    elif i == starti:
                        var_startj = startj
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    elif i == endi:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = endj
                    else:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    for j in range(var_startj, var_end):
                        self.result_table[i,j] = path_num
                        self.flow_list[path_num] -= self.tm[i,j]
                        add_tm += 1

        for index in range(len(s[math.floor(site_flow/delta)][1:])):
            if s[math.floor(site_flow/delta)][1:][index] == 0:
                dp_srv_sum += dp_srv[index]
                (endi, endj) = cluster_srv[dp2cluster[index]]
                endj += 1
                if dp2cluster[index] == 0:
                    (starti, startj) = (self.inv_table[site_pair[0]][0], self.inv_table[site_pair[1]][0])
                else:
                    (starti, startj) = cluster_srv[dp2cluster[index] - 1]
                    startj += 1
                for i in range(starti, endi + 1):
                    if i == starti and i == endi:
                        var_startj = startj
                        var_end = endj
                    elif i == starti:
                        var_startj = startj
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    elif i == endi:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = endj
                    else:
                        var_startj = self.inv_table[site_pair[1]][0]
                        var_end = self.inv_table[site_pair[1]][-1] + 1
                    for j in range(var_startj, var_end):
                        if self.tm[i - self.start_srv_pair[0],j - self.start_srv_pair[1]] < self.flow_list[path_num]:
                            self.result_table[i - self.start_srv_pair[0],j - self.start_srv_pair[1]] = path_num
                            self.flow_list[path_num] -= self.tm[i - self.start_srv_pair[0],j - self.start_srv_pair[1]]
                            add_tm += 1

        self.dpt += bdp - adp
        self.ct += bct - act
        self.gt += bgt - agt
        self.lrts["dp"].append(bdp - adp)
        self.lrts["ga"].append(bgt - agt)
        self.lrts["tt"].append(bdp - adp + bct - act + bgt - agt)
        if self.debug:
            print("DP time:", bdp - adp)
            print("Cluster time:", bct - act)
            print("GA time:", bgt - agt)
            print("Singal time:", bdp - adp + bct - act + bgt - agt)
            print("Added server demand:", add_tm)
            print(f"Total flow:{site_flow}, res flow:{res_demand}, srv num:{(len(self.inv_table[site_pair[0]]), len(self.inv_table[site_pair[0]]))}")

    def class_greedy(self, clas_num):
        for i in range(self.node_num):
            for j in range(self.node_num):
                if self.ref_table[i] == -1 or self.ref_table[j] == -1 or self.ref_table[i] == self.ref_table[j]:
                    continue
                if (self.ref_table[i],self.ref_table[j]) not in self.path:
                    continue
                if self.clas[i,j] == clas_num:
                    m_path = ""
                    if self.delay_flag == True:
                        mini_delay = 1000000
                        for _, site_p in self.path[(self.ref_table[i],self.ref_table[j])]:
                            if mini_delay > self.delay(str(site_p)) and self.flow_list[self.path_list.index(site_p)] < self.tm[i,j]:
                                m_path = site_p
                    else:
                        for (_, site_p) in self.path[(self.ref_table[i],self.ref_table[j])]:
                            if self.flow_list[self.path_list.index(site_p)] > self.tm[i,j]:
                                m_path = site_p
                                break
                    path_pos = self.path_list.index(m_path)
                    self.flow_list[path_pos] -= self.tm[i,j]
                    self.result_table[i,j] = path_pos

    def solve(self):
        print("------------ SSP Enable ------------")
        if self.debug:
            print("path list:", self.path_list)
        print("Total path num:", len(self.path_list))
        print("Total node num:", self.node_num)
        if self.clas_mode == True:
            for i in range(1):
                print(f"------------ Class {i} ------------")
                self.class_greedy(i)
        if self.top_flag == True:
            with alive_bar(len(self.flow_list[:int(len(self.pf)*self.top_lp)])) as bar:
                for path_num, flow in enumerate(self.flow_list[:int(len(self.pf)*self.top_lp)]):
                        self.single_ssp(flow, (self.path_list[path_num][0],self.path_list[path_num][-1]), path_num)
                        bar()
        else:
            with alive_bar(len(self.flow_list)) as bar:
                for path_num, flow in enumerate(self.flow_list):
                        self.single_ssp(flow, (self.path_list[path_num][0],self.path_list[path_num][-1]), path_num)
                        bar()
        if self.top_flag == True:
            self.other_top()

    def output(self):
        output_dict = {}
        for i in range(self.node_num[0]):
            for j in range(self.node_num[1]):
                if self.result_table[i,j] == -1:
                    continue
                srv_pair = (i + self.start_srv_pair[0],j + self.start_srv_pair[1])
                srv_path = [i + self.start_srv_pair[0]] + self.path_list[int(self.result_table[i,j])] + [j + self.start_srv_pair[1]]
                output_dict[srv_pair] = srv_path
            self.out = output_dict
        if self.debug:
            print("------------ output ------------")
            #print(output_dict)
    
    def save(self, file_path, filename):
        if filename == "ssp_solution.pkl":
            print("WARN: The file may be overwritten with the same name")
        if self.out == {}:
            print("ERROR: No output produced")
        else:
            with open(file_path + filename, 'wb') as f:
                pickle.dump(self.out, f)
    
    def pathnum(self):
        return len(self.flow_list)
    
    def total_demand(self):
        td = 0
        for i in range(self.node_num[0]):
            for j in range(self.node_num[1]):
                #if (self.ref_table[i + self.start_srv_pair[0]],self.ref_table[j + self.start_srv_pair[1]]) not in self.path:
                    #continue
                if self.result_table[i,j] != -1:
                    td += self.tm[i,j]
                    
        return td

    def tm_sum(self):
        ts = 0
        for i in range(self.node_num[0]):
            for j in range(self.node_num[1]):
                ts += self.tm[i,j]
        return ts

    def runtime(self):
    
        def part_runtime(part):
            self.lrts[part].sort(reverse=True)
            h = []
            for rt in self.lrts[part][:self.threads_num]:
                heappush(h, rt)
            curr_rt = 0
            for rt in self.lrts[part][self.threads_num:]:
                curr_rt = heappop(h)
                heappush(h, rt + curr_rt)
            while len(h) > 0:
                curr_rt = heappop(h)
            return curr_rt
        
        dp_rt = part_runtime("dp")
        ga_rt = part_runtime("ga")
        if self.debug:
            print("DP est time:", dp_rt)
            print("GA est time:", ga_rt)
        total_rt = part_runtime("tt")
        return total_rt
    
    def from_file(self, path):
        with open(path, 'rb') as f:
            return pickle.load(f)
        
    def add_nums2path(self, num, path):
        return path[:-4] + "_" + str(num) + ".pkl"
    
    def write_log(self, path, index, log):
        log_list = self.from_file(path)
        if index < len(log_list):
            log_list[index] = log
        else:
            log_list.append(log)
        with open(path, 'wb') as f:
            pickle.dump(log_list, f)




class SSP_TOP_MAIN(SSP):
    def __init__(self, size, problem_name, model, traffic_seed, scale_factor, tmuse):
        self.size = size
        self.problem_name = problem_name
        self.model = model
        self.traffic_seed = traffic_seed 
        self.scale_factor = scale_factor
        self.tmuse = tmuse
        self.total_run_time = None
        self.ssp_run_time_per_path = None
        self.ssp_runtime = None
        self.LP_satisfied_flow = None
        self.SSP_satisfied_flow = None
        self.ssp_top_main(size, problem_name, model, traffic_seed,scale_factor, tmuse)
        
        
    def ssp_top_main(self, size, problem_name, model, traffic_seed,scale_factor, tmuse):
        ## ref_table: a srv-stie reflection table
        ## tm: srv-level traffic matrix
        ## path: the solution of site-level TE
        ## The output will be saved in PKL format.
    
       
        ## Run the site-level TE:
        PATHS_DIR = os.path.join(TL_DIR, 'benchmarks','Top-Mega-logs')
        
        vals = os.path.basename(tmuse)[:-4].split('_')
        param = vals[4]
        toponame = problem_name + '_server2site.pkl'
        ref_table_fname = os.path.join(TOPOLOGIES_DIR, 'server2site-{}'.format(size),toponame)
        tm_fname = os.path.join(TM_DIR, 'srv-traffic-matrices-{}'.format(size), model, 
        '{}_{}_{}_{}_{}_traffic-matrix.pkl'.format(problem_name, model, traffic_seed, scale_factor, param))
        
        path_fname = os.path.join(PATHS_DIR, problem_name, '{}-{}'.format(traffic_seed, model), '{}-per_site'.format(size))
        save_fname = path_fname
        filename = '{}-{}-ssp_solution.pkl'.format(problem_name, size)
        path_fname = os.path.join(path_fname, '{}-{}-LP-in-mega_ssp_input.pkl'.format(problem_name, size))
    
        with open(ref_table_fname, 'rb') as f:
            ref_table = pickle.load(f)
            #print('ref,', size, ref_table)
        with open(tm_fname, 'rb') as f:
            tm = pickle.load(f)
        with open(path_fname, 'rb') as f:
            path = pickle.load(f)
            
        clas = []
        
        super().__init__(tm, 
                  clas, 
                  path, 
                  ref_table, 
                  delay = 0, 
                  epsilon = 0.1,
                  clas_mode=False,
                  top_mode=True,
                  debug=False)
                  
        start_time = time.time()
        self.solve()
        end_time = time.time()
        self.output()
        self.save(save_fname, filename)
        if self.debug == True:
            print('DP Total time:', self.dpt)
            print('Cluster Total time:', self.ct)
            print('GA Total time:', self.gt)
            print('Total Time:',end_time - start_time)
            print('Average time:', (end_time - start_time) / self.pathnum())
        print('------------ SSP results ------------')
        print('SSP Time:', self.runtime())
        
        
        self.total_run_time = end_time - start_time
        self.ssp_run_time_per_path = (end_time - start_time)/self.pathnum()
        self.ssp_runtime = self.runtime()
        self.LP_satisfied_flow = self.flow_sum
        self.SSP_satisfied_flow = self.total_demand()
        
    
class SSP_MAIN(SSP):
    def __init__(self, size, problem_name, model, traffic_seed,scale_factor, tmuse):
        self.size = size
        self.problem_name = problem_name
        self.model = model
        self.traffic_seed = traffic_seed 
        self.scale_factor = scale_factor
        self.tmuse = tmuse
        self.total_run_time = None
        self.ssp_run_time_per_path = None
        self.ssp_runtime = None
        self.LP_satisfied_flow = None
        self.SSP_satisfied_flow = None
        self.ssp_main(size, problem_name, model, traffic_seed,scale_factor, tmuse)
        
        
    def ssp_main(self, size, problem_name, model, traffic_seed,scale_factor, tmuse):
        ## ref_table: a srv-stie reflection table
        ## tm: srv-level traffic matrix
        ## path: the solution of site-level TE
        ## The output will be saved in PKL format.
    
       
        ## Run the site-level TE:
        PATHS_DIR = os.path.join(TL_DIR, 'benchmarks','Mega-logs')
        
        vals = os.path.basename(tmuse)[:-4].split('_')
        param = vals[4]
        toponame = problem_name + '_server2site.pkl'
        ref_table_fname = os.path.join(TOPOLOGIES_DIR, 'server2site-{}'.format(size),toponame)
        tm_fname = os.path.join(TM_DIR, 'srv-traffic-matrices-{}'.format(size), model, 
        '{}_{}_{}_{}_{}_traffic-matrix.pkl'.format(problem_name, model, traffic_seed, scale_factor, param))
        
        path_fname = os.path.join(PATHS_DIR, problem_name, '{}-{}'.format(traffic_seed, model), '{}-per_site'.format(size))
        save_fname = path_fname
        filename = '{}-{}-ssp_solution.pkl'.format(problem_name, size)
        path_fname = os.path.join(path_fname, '{}-{}-LP-in-mega_ssp_input.pkl'.format(problem_name, size))
    
        with open(ref_table_fname, 'rb') as f:
            ref_table = pickle.load(f)
            
        with open(tm_fname, 'rb') as f:
            tm = pickle.load(f)
            print('tm,', sum(tm))
        with open(path_fname, 'rb') as f:
            path = pickle.load(f)
            #print('path,', path)
            
        clas = []
        
        super().__init__(tm, 
                  clas, 
                  path, 
                  ref_table, 
                  delay = 0, 
                  epsilon = 0.1,
                  clas_mode=False,
                  top_mode=True,
                  debug=False)
                  
        start_time = time.time()
        self.solve()
        end_time = time.time()
        self.output()
        self.save(save_fname, filename)
        if self.debug == True:
            print('DP Total time:', self.dpt)
            print('Cluster Total time:', self.ct)
            print('GA Total time:', self.gt)
            print('Total Time:',end_time - start_time)
            print('Average time:', (end_time - start_time) / self.pathnum())
        print('------------ SSP results ------------')
        print('SSP Time:', self.runtime())
        
        
        self.total_run_time = end_time - start_time
        self.ssp_run_time_per_path = (end_time - start_time)/self.pathnum()
        self.ssp_runtime = self.runtime()
        self.LP_satisfied_flow = self.flow_sum
        self.SSP_satisfied_flow = self.total_demand()
        
        
class SSP_PART_MAIN(SSP_PART):
    def __init__(self, size, problem_name, model, traffic_seed, scale_factor, tmuse):
        self.size = size
        self.problem_name = problem_name
        self.model = model
        self.traffic_seed = traffic_seed 
        self.scale_factor = scale_factor
        self.tmuse = tmuse
        self.total_run_time = None
        self.ssp_run_time_per_path = None
        self.ssp_runtime = None
        self.LP_satisfied_flow = None
        self.SSP_satisfied_flow = None
        self.ssp_top_part_main(size, problem_name, model, traffic_seed,scale_factor, tmuse)
        
    def ssp_top_part_main(self, size, problem_name, model, traffic_seed,scale_factor, tmuse):
        ## ref_table: a srv-stie reflection table
        ## tm: srv-level traffic matrix
        ## path: the solution of site-level TE
        ## The output will be saved in PKL format.
    
       
        ## Run the site-level TE
        PATHS_DIR = os.path.join(TL_DIR, 'benchmarks','Top-Mega-logs')
        
        vals = os.path.basename(tmuse)[:-4].split('_')
        param = vals[4]
        toponame = problem_name + '_server2site.pkl'
        ref_table_fname = os.path.join(TOPOLOGIES_DIR, 'server2site-{}'.format(size), toponame)
        
        path_fname = os.path.join(PATHS_DIR, problem_name, '{}-{}'.format(traffic_seed, model), '{}-per_site'.format(size))
        save_fnames = path_fname
        log_path = os.path.join(path_fname, 'log.pkl')
        
        filename = '{}-{}-ssp_solution.pkl'.format(problem_name, size)
        path_fname = os.path.join(path_fname, '{}-{}-LP-in-mega_ssp_input.pkl'.format(problem_name, size))
        
        tm_list_fname = os.path.join(TM_DIR, 'srv-traffic-matrices-{}'.format(size), model, 'split_version', '{}_split_list.pkl'.format(problem_name))    
        with open(tm_list_fname, 'rb') as f:
            tm_list = pickle.load(f)
            
        
        tm_paths = os.path.join(TM_DIR, 'srv-traffic-matrices-{}'.format(size), model, 'split_version',
        '{}_{}_{}_{}_{}_traffic-matrix.pkl'.format(problem_name, model, traffic_seed, scale_factor, param))
        
        ssp_one = 1
        ssp_sum = 0
        ssp_tm_sum = 0
        ssp_time = 0
        start_point = 0
        if start_point != 0:
            logs = SSP.from_file(log_path)
            (ssp_sum, ssp_tm_sum, ssp_time) = logs[start_point]
        start_time = time.time()
        for index, (start_site_pair, end_site_pair) in enumerate(tm_list):
            if ssp_one and index != 0:
                print('DONE')
                break
            if index < start_point: continue
            if index == 0:
                with open(log_path,"wb") as f:pickle.dump([], f)
            print("Part SSP ", index,"|ID:", start_site_pair, "-", end_site_pair)
            
            print(index, tm_paths)
            
            tm_path = self.add_nums2path(index, tm_paths)
            #save_fname = self.add_nums2path(index, save_fnames)
            save_fname = os.path.join(save_fnames, filename)[:-4] + "_" + str(index) + ".pkl"
            super().__init__(
                tm_path,
                path_fname,
                ref_table_fname,
                clas_path = "",
                delay_path = "",
                epsilon = 0.1, 
                delay_mode = False,
                clas_mode = False,
                top_mode = False, 
                debug = False,
                start_site_pair = start_site_pair
            )
            
            
            if 1:
            #with alive_bar((end_site_pair[0] - start_site_pair[0])) as bar:
                for i in range(start_site_pair[0], end_site_pair[0]):
                    for j in range(start_site_pair[1], end_site_pair[1]):
                            if (i,j) not in self.path:continue
                            paths = self.path[(i,j)]
                            for flow, path in paths:
                                path_num = self.path_list.index(path)
                                self.single_ssp(flow, (path[0],path[-1]), path_num)
                    #bar()
            
            if self.debug == True:
                print("DP Total time:", self.dpt)
                print("Cluster Total time:", self.ct)
                print("GA Total time:", self.gt)
                print("Total Time:",end_time - start_time)
                print("Average time:", (end_time - start_time)/self.pathnum())
            ssp_sum += self.total_demand()
            ssp_tm_sum += self.tm_sum()
            ssp_time += self.runtime()
            log = (ssp_sum, ssp_tm_sum, ssp_time)
            self.write_log(log_path,index,log)
            print(self.runtime())
            
            
        end_time = time.time()
        print("------------ SSP results ------------")
        print("SSP time:", ssp_time)
        print("total time:",end_time - start_time)
        print("Satisfied demand:", ssp_sum/ssp_tm_sum)
        print("MCF Flow / Demand:",self.flow_sum()/ ssp_tm_sum)
        #print(ssp_sum, self.flow_sum(),ssp_tm_sum)
       
        self.output()
        self.save(save_fname, '')        
        
        self.total_run_time = end_time - start_time
        self.ssp_run_time_per_path = (end_time - start_time)/self.pathnum()
        self.ssp_runtime = self.runtime()
        self.LP_satisfied_flow = self.flow_sum
        self.SSP_satisfied_flow = self.total_demand()
    

class SSP_ORDER_MAIN(SSP):
    """
    Order-preserving SSP that maintains server pair assignments across TM matrices
    """

    def __init__(self, size, problem_name, model, traffic_seed, scale_factor, tmuse, previous_solution=None, complete_path_fname=None):
        # Set MegaOrder-specific state FIRST, before parent initialization
        self.size = size
        self.problem_name = problem_name
        self.model = model
        self.traffic_seed = traffic_seed
        self.scale_factor = scale_factor
        self.tmuse = tmuse
        self.total_run_time = None
        self.ssp_run_time_per_path = None
        self.ssp_runtime = None
        self.LP_satisfied_flow = None
        self.SSP_satisfied_flow = None
        self.previous_solution = previous_solution
        self.current_solution = {}
        self.complete_path_fname = complete_path_fname  # Store complete path file for fixed path_num mapping

        # Stability metrics
        self.total_deleted_pairs_used = 0    # Total count of deleted pairs used across all site_pairs

        self.ssp_order_main(size, problem_name, model, traffic_seed, scale_factor, tmuse)


    def ssp_order_main(self, size, problem_name, model, traffic_seed,scale_factor, tmuse):
        ## ref_table: a srv-stie reflection table
        ## tm: srv-level traffic matrix
        ## path: the solution of site-level TE
        ## The output will be saved in PKL format.
    
       
        ## Run the site-level TE:
        PATHS_DIR = os.path.join(TL_DIR, 'benchmarks','Mega-order-logs')
        
        vals = os.path.basename(tmuse)[:-4].split('_')
        param = vals[4]
        toponame = problem_name + '_server2site.pkl'
        ref_table_fname = os.path.join(TOPOLOGIES_DIR, 'server2site-{}'.format(size),toponame)
        tm_fname = os.path.join(TM_DIR, 'srv-traffic-matrices-{}'.format(size), model, 
        '{}_{}_{}_{}_{}_traffic-matrix.pkl'.format(problem_name, model, traffic_seed, scale_factor, param))
        
        path_fname = os.path.join(PATHS_DIR, problem_name, '{}-{}'.format(traffic_seed, model), '{}-per_site'.format(size))
        save_fname = path_fname
        filename = '{}-{}-ssp_solution.pkl'.format(problem_name, size)
        path_fname = os.path.join(path_fname, '{}-{}-LP-in-mega_ssp_input.pkl'.format(problem_name, size))
    
        with open(ref_table_fname, 'rb') as f:
            ref_table = pickle.load(f)
            
        with open(tm_fname, 'rb') as f:
            tm = pickle.load(f)
            print('tm,', sum(tm))
        with open(path_fname, 'rb') as f:
            path = pickle.load(f)
            #print('path,', path)
            
        clas = []
        
        super().__init__(tm, 
                  clas, 
                  path, 
                  ref_table, 
                  delay = 0, 
                  epsilon = 0.1,
                  clas_mode=False,
                  top_mode=True,
                  debug=False)
                  
        start_time = time.time()
        self.solve()
        end_time = time.time()
        self.output()
        self.save(save_fname, filename)
        if self.debug == True:
            print('DP Total time:', self.dpt)
            print('Cluster Total time:', self.ct)
            print('GA Total time:', self.gt)
            print('Total Time:',end_time - start_time)
            print('Average time:', (end_time - start_time) / self.pathnum())
        print('------------ SSP results ------------')
        print('SSP Time:', self.runtime())
        
        
        self.total_run_time = end_time - start_time
        self.ssp_run_time_per_path = (end_time - start_time)/self.pathnum()
        self.ssp_runtime = self.runtime()
        self.LP_satisfied_flow = self.flow_sum
        self.SSP_satisfied_flow = self.total_demand()

    def solve(self):
        """Override solve to use historical assignments with two-phase processing

        Two-phase processing applies to ALL paths (not just top_lp%):
        Phase 1: Process paths that need deletion (TM1 assigned > TM2 site_flow)
        Phase 2: Process paths that need addition (TM1 assigned < TM2 site_flow)
        Phase 3: Extract unused pairs
        Phase 4: Convert deleted to unused
        """
        # Initialize FIXED path_num assignment (overrides parent's flow-based sorting)
        self._init_fixed_path_nums()
        
        #import pdb; pdb.set_trace()
        
        # Check if this is the first TM matrix (no history yet)
        self.is_first_iteration = (len(self.previous_solution) == 0)

        print('------------ SSP Order Enable (Two-Phase Processing for ALL paths) ------------')
        if self.debug:
            print('path list:', self.path_list)
        print('Total path num:', len(self.path_list))
        print('Total node num:', self.node_num)

        # For first TM matrix, use standard SSP with TOP processing (no history to leverage)
        if self.is_first_iteration:
            print('\n=== First TM matrix: using standard SSP with TOP (no history) ===')
            super().solve()

            # Build current_solution from result_table for next iteration
            self._build_current_solution_from_result_table()
            return

        # For subsequent TM matrices, use two-phase processing with history
        # PHASE 0: Seed pairs from DEAD tunnels (previous solution used them,
        # but the current LP allocated F=0, so path_list_fixed[pn] is None)
        # into the site-pair deleted pools. Without this, those pairs are
        # skipped by the classification loop below and never enter any
        # source pool (they are TM1-used, so not in prev_unused; their tunnel
        # never runs Case A, so not in deleted) - they would strand for the
        # whole TM. Case B's Priority 2 consumes the deleted pool, so seeding
        # makes them reachable in the same TM.
        print('\n=== PHASE 0: Seeding dead-tunnel pairs into deleted pools ===')
        seeded_pairs = 0
        seeded_flow = 0.0
        for hist_key, hist in self.previous_solution.items():
            dead_assigned = []
            for pn, pd in hist.get('path_states', {}).items():
                if pn >= len(self.path_list_fixed) or self.path_list_fixed[pn] is None:
                    for (srv_i, srv_j, _) in pd.get('assigned', []):
                        dead_assigned.append((srv_i, srv_j, self.tm[srv_i, srv_j]))
            if dead_assigned:
                if hist_key not in self.current_solution:
                    self.current_solution[hist_key] = {'path_states': {}, 'deleted': [], 'unused': []}
                self.current_solution[hist_key]['deleted'].extend(dead_assigned)
                seeded_pairs += len(dead_assigned)
                seeded_flow += sum(f for _, _, f in dead_assigned)
        print('Seeded {} pairs ({:.2f} flow) from dead tunnels into deleted pools'.format(
            seeded_pairs, seeded_flow))

        # Classify ALL paths into deletion and addition groups
        deletion_paths = []
        addition_paths = []
        perfect_match_paths = []

        print('\n=== PHASE 1: Classifying ALL paths (using FIXED path_nums) ===')
        for path_num, flow in enumerate(self.flow_list_fixed):
            if self.path_list_fixed[path_num] is None:
                continue  # Skip paths not in current TM

            site_pair = (self.path_list_fixed[path_num][0], self.path_list_fixed[path_num][-1])
            hist_key = (site_pair[0], site_pair[1])

            if hist_key in self.previous_solution and path_num in self.previous_solution[hist_key].get('path_states', {}):
                prev_assigned = self.previous_solution[hist_key]['path_states'][path_num].get('assigned', [])
                # Calculate prev_flow using CURRENT TM's traffic demands (not historical flows)
                prev_flow = sum(self.tm[srv_i, srv_j] for srv_i, srv_j, _ in prev_assigned)

                if prev_flow > flow:
                    deletion_paths.append((path_num, flow, site_pair))
                    #print(f'  Path {path_num} ({site_pair}): needs deletion (prev={prev_flow:.2f}, curr={flow:.2f})')
                elif prev_flow < flow:
                    addition_paths.append((path_num, flow, site_pair))
                    #print(f'  Path {path_num} ({site_pair}): needs addition (prev={prev_flow:.2f}, curr={flow:.2f})')
                else:
                    perfect_match_paths.append((path_num, flow, site_pair))
                    #print(f'  Path {path_num} ({site_pair}): perfect match (prev={curr}={flow:.2f})')
            else:
                # No history for this path (new path or path_num changed)
                # Treat as addition: need initial assignment using standard SSP
                addition_paths.append((path_num, flow, site_pair))
                #print(f'  Path {path_num} ({site_pair}): no history, will assign')

        print(f'\n=== Summary: {len(deletion_paths)} deletions, {len(addition_paths)} additions, {len(perfect_match_paths)} perfect matches ===')

        # Process paths in two phases 
        if deletion_paths:
            print(f'\n=== PHASE 2: Processing {len(deletion_paths)} deletion paths ===')
            with alive_bar(len(deletion_paths)) as bar:
                for path_num, flow, site_pair in deletion_paths:
                    #print(f'\n>>> Processing deletion: Path {path_num} ({site_pair})')
                    self.single_ssp_order(flow, site_pair, path_num)
                    bar()

        if addition_paths:
            print(f'\n=== PHASE 3: Processing {len(addition_paths)} addition paths (can use deleted from PHASE 2) ===')
            with alive_bar(len(addition_paths)) as bar:
                for path_num, flow, site_pair in addition_paths:
                    #print(f'\n>>> Processing addition: Path {path_num} ({site_pair})')
                    self.single_ssp_order(flow, site_pair, path_num)
                    bar()

        # Process perfect match paths (no changes needed)
        if perfect_match_paths:
            print(f'\n=== PHASE 3.5: Processing {len(perfect_match_paths)} perfect match paths ===')
            for path_num, flow, site_pair in perfect_match_paths:
                print(f'>>> Processing perfect match: Path {path_num} ({site_pair})')
                self.single_ssp_order(flow, site_pair, path_num)

        # Update unused pairs for all site pairs based on final result_table
        #print('\n=== Extracting unused pairs for all site pairs ===')
        for site_pair in self.current_solution:
            self.current_solution[site_pair]['unused'] = self._extract_unused_pairs(site_pair)
            #print(f'  Site pair {site_pair}: {len(self.current_solution[site_pair]["unused"])} unused pairs')

        #pdb.set_trace()

        print('\n=== All paths processed ===')




    def single_ssp_order(self, site_flow, site_pair, path_num):
        """History-aware SSP with site-pair level deleted (Solution 3.1)

        Data structure:
            current_solution[(site_i, site_j)] = {
                'path_states': {
                    path_num: {
                        'path_num': path_num,
                        'assigned': [(srv_i, srv_j, flow), ...]  # per-path only
                    }
                },
                'deleted': [(srv_i, srv_j, flow), ...],  # site-pair level, shared across all paths
                'unused': [(srv_i, srv_j, flow), ...]    # site-pair level, shared across all paths
            }
        """
        hist_key = (site_pair[0], site_pair[1])

        if hist_key in self.previous_solution:
            hist = self.previous_solution[hist_key]

            # Get current path's history (per-path)
            path_states = hist.get('path_states', {})
            if path_num in path_states:
                path_hist = path_states[path_num]
                prev_assigned = path_hist.get('assigned', [])
            else:
                # This path is new in this TM
                prev_assigned = []

            # Get site pair's unused (shared across all paths)
            prev_unused = hist.get('unused', [])

            # Calculate prev_flow using CURRENT TM's traffic demands
            # prev_assigned stores (srv_i, srv_j, old_flow), but we need current TM's flow
            prev_flow = sum(self.tm[srv_i, srv_j] for srv_i, srv_j, _ in prev_assigned)

            print(f"History for {site_pair} path {path_num}: prev_flow={prev_flow:.2f}, site_flow={site_flow:.2f}")

            if prev_flow > site_flow:
                # Case A: Remove excess from current path
                excess = prev_flow - site_flow
                print(f"  Case A: Remove excess {excess:.2f}")
                removed = self._remove_pairs(prev_assigned, excess, site_pair)

                self._assign_pairs(removed['kept'], path_num)

                # Update current solution with new structure
                if hist_key not in self.current_solution:
                    self.current_solution[hist_key] = {'path_states': {}, 'deleted': [], 'unused': []}

                # Update current path's state (only assigned, deleted is site-pair level)
                self.current_solution[hist_key]['path_states'][path_num] = {
                    'path_num': path_num,
                    'assigned': removed['kept']
                }

                # Add removed pairs to site-pair level deleted (shared across all paths)
                self.current_solution[hist_key]['deleted'].extend(removed['removed'])

            elif prev_flow < site_flow:
                # Case B: Add more pairs to current path
                deficit = site_flow - prev_flow
                print(f"  Case B: Add deficit {deficit:.2f}")

                # Priority 1: Use unused pairs from history (shared)
                used_from_unused = self._use_pairs(prev_unused, deficit, site_pair)
                remaining_deficit = deficit - used_from_unused['flow']

                # Priority 2: Use deleted pairs from Phase 1 of current iteration (site-pair level)
                if remaining_deficit > 0:
                    current_deleted = self.current_solution.get(hist_key, {}).get('deleted', [])
                    if current_deleted:
                        used_from_deleted = self._use_pairs(current_deleted, remaining_deficit, site_pair)

                        # Update site-pair level deleted with remaining
                        self.current_solution[hist_key]['deleted'] = used_from_deleted['remaining']

                        # Accumulate stability metrics: count reused deleted pairs
                        reused_count = len(used_from_deleted['pairs'])
                        self.total_deleted_pairs_used += reused_count

                    else:
                        used_from_deleted = {'pairs': [], 'remaining': [], 'flow': 0}
                else:
                    used_from_deleted = {'pairs': [], 'remaining': [], 'flow': 0}


                # Update prev_assigned to use CURRENT TM's flow values
                prev_assigned_updated = [(srv_i, srv_j, self.tm[srv_i, srv_j]) for srv_i, srv_j, _ in prev_assigned]

                all_pairs = prev_assigned_updated + used_from_unused['pairs'] + used_from_deleted['pairs']

                #satisfied_flow = sum(flow for _, _, flow in all_pairs)

                self._assign_pairs(all_pairs, path_num)

                # Update current solution with new structure
                if hist_key not in self.current_solution:
                    self.current_solution[hist_key] = {'path_states': {}, 'deleted': [], 'unused': []}

                # Update current path's state (only assigned, no per-path deleted)
                self.current_solution[hist_key]['path_states'][path_num] = {
                    'path_num': path_num,
                    'assigned': all_pairs
                }


                #print(f"    Satisfied flow: {satisfied_flow:.2f} / {site_flow:.2f} ({satisfied_flow/site_flow*100:.1f}%)")

            else:
                # Case C: Perfect match
                print(f"  Case C: Perfect match, reuse all {len(prev_assigned)} pairs")
                # Update prev_assigned to use CURRENT TM's flow values
                prev_assigned_updated = [(srv_i, srv_j, self.tm[srv_i, srv_j]) for srv_i, srv_j, _ in prev_assigned]
                self._assign_pairs(prev_assigned_updated, path_num)

                if hist_key not in self.current_solution:
                    self.current_solution[hist_key] = {'path_states': {}, 'deleted': [], 'unused': []}

                # Update current path's state (only assigned, no per-path deleted)
                self.current_solution[hist_key]['path_states'][path_num] = {
                    'path_num': path_num,
                    'assigned': prev_assigned_updated
                }

        else:
            # No history for this site pair
            # Use simple greedy assignment (similar to other_top()), not complex SSP
            if not self.is_first_iteration:
                print(f"No history for {site_pair} path {path_num}, using simple greedy assignment")

            # Simple greedy assignment: assign server pairs until site_flow is satisfied
            assigned_pairs = self._simple_greedy_assign(site_flow, site_pair, path_num)

            # Initialize current solution with new structure
            if hist_key not in self.current_solution:
                self.current_solution[hist_key] = {'path_states': {}, 'deleted': [], 'unused': []}

            # Update current path's state (only assigned, no per-path deleted)
            self.current_solution[hist_key]['path_states'][path_num] = {
                'path_num': path_num,
                'assigned': assigned_pairs
            }


    def _extract_assigned_pairs(self, site_pair, path_num):
        """Extract assigned server pairs from result_table for a given site_pair and path_num"""
        assigned_pairs = []

        # Get server ranges for the site pair
        site_i, site_j = site_pair
        if not self.inv_table[site_i] or not self.inv_table[site_j]:
            return assigned_pairs

        starti = self.inv_table[site_i][0]
        endi = self.inv_table[site_i][-1]
        startj = self.inv_table[site_j][0]
        endj = self.inv_table[site_j][-1]

        # Extract all server pairs assigned to this path_num
        for i in range(starti, endi + 1):
            for j in range(startj, endj + 1):
                if self.result_table[i, j] == path_num:
                    flow = self.tm[i, j]
                    assigned_pairs.append((i, j, flow))

        return assigned_pairs

    def _extract_path_assigned_pairs(self, site_pair, path_num):
        """Extract assigned server pairs for a specific path within a site pair

        This is specifically for MegaOrder where we need to track assignments per path.
        """
        return self._extract_assigned_pairs(site_pair, path_num)

    def _extract_unused_pairs(self, site_pair):
        """Extract unused server pairs for a given site_pair (called after all paths processed)

        Unused pairs are those that:
        - Are NOT assigned to any path (result_table[i,j] == -1) - this is the
          ONLY membership criterion: unused is purely about assignment state,
          NOT about traffic demand
        - Belong to the site pair's server range

        This should be called at the END of solve() after all paths are processed,
        to capture the final state of the result_table.
        """
        unused_pairs = []

        # Get server ranges for the site pair
        site_i, site_j = site_pair
        if not self.inv_table[site_i] or not self.inv_table[site_j]:
            return unused_pairs

        starti = self.inv_table[site_i][0]
        endi = self.inv_table[site_i][-1]
        startj = self.inv_table[site_j][0]
        endj = self.inv_table[site_j][-1]

        # Extract all unassigned server pairs (regardless of demand)
        for i in range(starti, endi + 1):
            for j in range(startj, endj + 1):
                # Check if unassigned
                if self.result_table[i, j] == -1:
                    # Also verify it belongs to this site pair
                    if (self.ref_table[i], self.ref_table[j]) == (site_i, site_j):
                        unused_pairs.append((i, j, self.tm[i, j]))

        return unused_pairs

    def _remove_pairs(self, assigned_pairs, excess_flow, site_pair):
        """Remove pairs using greedy smallest-flow-first

        Strategy: Remove smallest flows (based on CURRENT TM) until total >= excess

        Args:
            assigned_pairs: List of (srv_i, srv_j, old_flow) from history
            excess_flow: Amount to remove
            site_pair: For accessing current TM values

        Note: Uses CURRENT TM's flow values for sorting and calculation
        """
        # Sort by CURRENT TM's flow (smallest first)
        sorted_pairs = sorted(assigned_pairs, key=lambda x: self.tm[x[0], x[1]])

        removed_flow = 0
        kept = []
        removed = []

        for srv_i, srv_j, old_flow in sorted_pairs:
            current_flow = self.tm[srv_i, srv_j]
            if removed_flow < excess_flow:
                removed.append((srv_i, srv_j, current_flow))
                removed_flow += current_flow
            else:
                kept.append((srv_i, srv_j, current_flow))

        print(f"    Removed {len(removed)} pairs (flow={removed_flow:.2f}), kept {len(kept)} pairs")
        return {'kept': kept, 'removed': removed, 'flow': removed_flow}

    def _use_pairs(self, available_pairs, deficit_flow, site_pair):
        """Use pairs from available pool (largest-flow-first)

        Args:
            available_pairs: List of (srv_i, srv_j, old_flow) from history
            deficit_flow: Amount to add
            site_pair: For accessing current TM values

        Note: Uses CURRENT TM's flow values for sorting and calculation.
        Candidates already assigned this TM (result_table != -1) are skipped
        and kept in 'remaining' - the pool only supplies currently-unassigned
        pairs.
        """
        if not available_pairs:
            return {'pairs': [], 'remaining': available_pairs, 'flow': 0}

        # Sort by CURRENT TM's flow (largest first)
        sorted_pairs = sorted(available_pairs, key=lambda x: -self.tm[x[0], x[1]])

        used_flow = 0
        used = []
        remaining = []

        for srv_i, srv_j, old_flow in sorted_pairs:
            current_flow = self.tm[srv_i, srv_j]
            if self.result_table[srv_i, srv_j] != -1:
                # already assigned to a tunnel this TM; not pool-eligible
                remaining.append((srv_i, srv_j, current_flow))
                continue
            if used_flow + current_flow <= deficit_flow:
                used.append((srv_i, srv_j, current_flow))
                used_flow += current_flow
            else:
                remaining.append((srv_i, srv_j, current_flow))

        print(f"    Used {len(used)} pairs from pool (flow={used_flow:.2f}/{deficit_flow:.2f})")
        return {'pairs': used, 'remaining': remaining, 'flow': used_flow}

    def _assign_pairs(self, pairs, path_num):
        """Assign pairs to result_table"""
        for srv_i, srv_j, flow in pairs:
            if srv_i < len(self.result_table) and srv_j < len(self.result_table):
                if self.result_table[srv_i, srv_j] == -1:
                    self.result_table[srv_i, srv_j] = path_num
                    #self.flow_list[path_num] -= self.tm[srv_i, srv_j]

    def _simple_greedy_assign(self, site_flow, site_pair, path_num):
        """
        Simple greedy assignment for site_pairs without history.

        Similar to other_top() logic:
        - Iterate through all server pairs in this site_pair
        - Assign unassigned pairs until site_flow is satisfied
        - No complex DP optimization, just greedy filling

        Returns:
            List of assigned (srv_i, srv_j, flow) tuples
        """
        assigned_pairs = []
        satisfied_flow = 0.0

        site_i, site_j = site_pair

        # Get server ranges for this site pair
        if not self.inv_table[site_i] or not self.inv_table[site_j]:
            return assigned_pairs

        starti = self.inv_table[site_i][0]
        endi = self.inv_table[site_i][-1]
        startj = self.inv_table[site_j][0]
        endj = self.inv_table[site_j][-1]

        # Greedy assign: iterate through server pairs and assign until site_flow satisfied
        for i in range(starti, endi + 1):
            for j in range(startj, endj + 1):
                # Skip if already assigned
                if self.result_table[i, j] != -1:
                    continue

                # Check if this server pair has traffic demand
                if self.tm[i, j] > 0:
                    # Check if adding this pair would exceed site_flow
                    if satisfied_flow + self.tm[i, j] <= site_flow:
                        # Assign this pair
                        self.result_table[i, j] = path_num
                        assigned_pairs.append((i, j, self.tm[i, j]))
                        satisfied_flow += self.tm[i, j]

                    # Stop if site_flow is satisfied
                    if satisfied_flow >= site_flow:
                        break

            if satisfied_flow >= site_flow:
                break

        print(f"    Simple greedy: assigned {len(assigned_pairs)} pairs (flow={satisfied_flow:.2f}/{site_flow:.2f})")
        return assigned_pairs

    def extract_solution(self):
        """Extract current solution for next iteration"""
        return self.current_solution

    def _build_current_solution_from_result_table(self):
        """
        Build current_solution from result_table after first TM matrix processing

        Maps parent's result_table (using parent path_nums) to fixed path_nums.
        """
        print('\n=== Building current_solution from result_table (using FIXED path_nums) ===')

        self.current_solution = {}
        #processed_count = 0

        # Iterate through FIXED path_nums (not parent's path_nums)
        for fixed_path_num in range(len(self.path_list_fixed)):
            if self.path_list_fixed[fixed_path_num] is None:
                continue  # This path doesn't exist in current TM

            path = self.path_list_fixed[fixed_path_num]
            flow = self.flow_list_fixed[fixed_path_num]
            site_pair = (path[0], path[-1])
            hist_key = (site_pair[0], site_pair[1])

            # Find corresponding parent_path_num (for extracting from result_table)
            parent_path_num = None
            for pn, (pf, pp) in enumerate(self.pf):
                if pp == path and pf == flow:
                    parent_path_num = pn
                    break

            if parent_path_num is None:
                print(f'  WARNING: Fixed path {fixed_path_num} not found in parent pf')
                continue

            # Initialize site-pair structure if needed
            if hist_key not in self.current_solution:
                self.current_solution[hist_key] = {
                    'path_states': {},
                    'deleted': [],
                    'unused': []
                }

            # Extract assigned pairs for this path (using parent_path_num)
            assigned_pairs = self._extract_path_assigned_pairs(site_pair, parent_path_num)

            # Store path state (using FIXED path_num)
            self.current_solution[hist_key]['path_states'][fixed_path_num] = {
                'path_num': fixed_path_num,
                'assigned': assigned_pairs
            }

            #processed_count += 1

        # Extract unused pairs for all site pairs
        for site_pair in self.current_solution:
            self.current_solution[site_pair]['unused'] = self._extract_unused_pairs(site_pair)

        #print(f'  Total site pairs: {len(self.current_solution)}')
        #print(f'  Paths with assignments: {processed_count}/{len(self.path_list_fixed)}')

    def _init_fixed_path_nums(self):
        """
        Initialize FIXED path_num assignment based on COMPLETE path file.

        Loads the complete path dict (all possible paths) and establishes fixed path_nums:
        - site_pair (0,1): path_nums 0, 1, 2, 3 (fixed)
        - site_pair (0,2): path_nums 4, 5, 6, 7 (fixed)
        - etc.

        Same site_pair ALWAYS gets same path_num range across different TM matrices,
        regardless of which paths are actually used in the current TM's ssp_dict.
        """
        print('\n=== Initializing FIXED path_num assignment from complete path file ===')

        # Load complete path dict
        if self.complete_path_fname is None:
            print('  WARNING: No complete path file provided, using parent\'s path dict (may cause path_num mismatch across TMs)')
            complete_path_dict = self.path
        else:
            print(f'  Loading complete path file: {self.complete_path_fname}')
            with open(self.complete_path_fname, 'rb') as f:
                complete_path_dict = pickle.load(f)

        # Step 1: Get sorted site_pairs from complete path dict
        sorted_site_pairs = sorted(complete_path_dict.keys())

        # Step 2: Calculate path_num ranges for each site_pair
        site_pair_path_num_start = {}  # site_pair -> starting path_num
        current_path_num = 0
        for site_pair in sorted_site_pairs:
            site_pair_path_num_start[site_pair] = current_path_num
            num_paths = len(complete_path_dict[site_pair])
            current_path_num += num_paths

        total_paths = current_path_num

        # Step 3: Build fixed arrays (some indices may be None if path not in current TM)
        self.path_list_fixed = [None] * total_paths
        self.flow_list_fixed = [0.0] * total_paths

        # Step 4: Assign paths from parent's pf list (current TM's ssp_dict)
        # to their fixed positions based on complete path dict
        for (flow, path) in self.pf:
            # Find which site_pair this path belongs to
            site_pair = (path[0], path[-1])

            if site_pair in site_pair_path_num_start:
                base_path_num = site_pair_path_num_start[site_pair]

                # Find the index of this path in complete path dict
                # Need to match path exactly (complete_paths has no flow, only paths)
                complete_paths = complete_path_dict[site_pair]
                for path_idx, comp_path in enumerate(complete_paths):
                    if comp_path == path:  # Match path
                        fixed_path_num = base_path_num + path_idx
                        if fixed_path_num < total_paths:
                            self.path_list_fixed[fixed_path_num] = path
                            self.flow_list_fixed[fixed_path_num] = flow
                        break

        # print(f'  Total paths (fixed array size): {total_paths}')
        # print(f'  Total site_pairs in complete path: {len(sorted_site_pairs)}')
        # print(f'  First 5 site_pairs: {sorted_site_pairs[:5]}')
        # if len(sorted_site_pairs) > 0:
        #     print(f'  Path_num ranges: {[(sp, site_pair_path_num_start[sp], site_pair_path_num_start[sp] + len(complete_path_dict[sp]) - 1) for sp in sorted_site_pairs[:5]]}')

        # # Verify: count non-None entries (paths used in current TM)
        # non_none_count = sum(1 for p in self.path_list_fixed if p is not None)
        # print(f'  Assigned paths in current TM: {non_none_count}/{total_paths}')

    def output(self, output_dict=None):
        """
        Override parent's output to handle both first and subsequent TM matrices.

        For first TM: result_table uses parent's path_num (flow-sorted)
        For subsequent TMs: result_table uses fixed_path_num (from MegaOrder)

        Solution: Check is_first_iteration to decide which path_list to use.
        """
        if output_dict is None:
            # never use a mutable default: chained TM runs in one process would
            # accumulate earlier TMs' entries into this TM's ssp_out
            output_dict = {}
        # Use parent's path_list for first TM, path_list_fixed for subsequent TMs
        path_list_to_use = self.path_list if self.is_first_iteration else self.path_list_fixed

        for i in range(self.node_num):
            for j in range(self.node_num):
                if self.result_table[i, j] == -1:
                    continue
                srv_pair = (i, j)
                path_num = int(self.result_table[i, j])
                srv_path = [i] + path_list_to_use[path_num] + [j]
                output_dict[srv_pair] = srv_path
        self.out = output_dict
        if self.debug:
            mode = "first TM (parent's path_list)" if self.is_first_iteration else "subsequent TM (fixed path_list)"
            print(f'------------ output (MegaOrder: {mode}) ------------')

    def save(self, file_path, filename):
        """Override save to include current_solution for MegaOrder"""
        # Save both SSP output and current_solution
        if not self.out:
            print('ERROR: No SSP output produced')
            return

        # Prepare output with both standard SSP results and current_solution
        output_data = {
            'ssp_out': self.out,           # Standard SSP output
            'current_solution': self.current_solution  # MegaOrder historical state
        }

        with open(file_path + '/' + filename, 'wb') as f:
            pickle.dump(output_data, f)
