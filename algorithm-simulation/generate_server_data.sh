#!/bin/bash

# MegaTE Server-level 数据生成脚本
# 用法: bash generate_server_data.sh

set -e  # 遇到错误立即退出

# 激活环境
source /home/zyxl/miniconda3/etc/profile.d/conda.sh
conda activate megate

# 设置路径
cd /home/zyxl/MegaTE-main/scripts
export PYTHONPATH=/home/zyxl/MegaTE-main

# 拓扑列表
TOPOLOGIES=("Cogentco.graphml") # "Uninett2010.graphml" "Deltacom.graphml" "UsCarrier.graphml" "Cogentco.graphml"

# 服务器规模
SERVER_SIZES=(5 20 40 60 80 100)

echo "=========================================="
echo "开始生成 Server-level 数据"
echo "拓扑: ${TOPOLOGIES[@]}"
echo "服务器规模: ${SERVER_SIZES[@]}"
echo "=========================================="
echo ""

# 步骤 1：生成 server-level 拓扑和路径
echo "步骤 1/2: 生成 Server-level 拓扑和路径..."
echo ""

for topo in "${TOPOLOGIES[@]}"; do
    for size in "${SERVER_SIZES[@]}"; do
        echo ">>> 处理: $topo, server size=$size"

        python3 generate_srv_path.py --topo "$topo" --server "$size"

        if [ $? -eq 0 ]; then
            echo "✅ 完成: $topo, server size=$size"
        else
            echo "❌ 失败: $topo, server size=$size"
            exit 1
        fi
        echo ""
    done
done

echo "=========================================="
echo "步骤 2/2: 生成 Server-level 流量矩阵..."
echo ""

# 步骤 2：生成 server-level 流量矩阵
for topo in "${TOPOLOGIES[@]}"; do
    for size in "${SERVER_SIZES[@]}"; do
        echo ">>> 处理: $topo, server size=$size"

        python3 generate_srv_tm.py --topo "$topo" --server "$size"

        if [ $? -eq 0 ]; then
            echo "✅ 完成: $topo, server size=$size"
        else
            echo "❌ 失败: $topo, server size=$size"
            exit 1
        fi
        echo ""
    done
done

echo "=========================================="
echo "✅ 所有数据生成完成！"
echo ""
echo "生成的数据："
echo "  - Server-level 拓扑: topologies/srv_topologies-{1,10}/"
echo "  - Server-level 路径: topologies/paths/srv_paths-{1,10}/"
echo "  - Server-level 流量矩阵: traffic-matrices/srv-traffic-matrices-{1,10}/"
echo "  - Server映射: topologies/server2site-{1,10}/"
echo "=========================================="
