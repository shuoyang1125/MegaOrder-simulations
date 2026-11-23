# Mega Reordering Analysis

## Overview

This script analyzes srv-srv pair reordering in Mega algorithm by comparing two TM matrices.

**Reordered pair definition**: A srv-srv pair that was assigned to one path in TM1 but assigned to a **different path** in TM2.

## Usage

### Step 1: Edit the script

Open `analyze_mega_reordering.py` and edit the file paths at the top of the `main()` function:

```python
tm1_solution_path = "Mega-logs/Uninett2010.graphml/1505250729-uniform/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl"
tm2_solution_path = "Mega-logs/Uninett2010.graphml/1655001236-uniform/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl"
```

### Step 2: Run the script

```bash
cd /home/zyxl/MegaTE-main/benchmarks
python analyze_mega_reordering.py
```

### Example Comparisons

**Compare two consecutive TM matrices:**
```python
# Edit in script:
tm1_solution_path = "Mega-logs/Uninett2010.graphml/1505250729-uniform/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl"
tm2_solution_path = "Mega-logs/Uninett2010.graphml/1655001236-uniform/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl"
```

**Compare different server sizes:**
```python
# Edit in script:
tm1_solution_path = "Mega-logs/Uninett2010.graphml/1505250729-uniform/1-per_site/Uninett2010.graphml-1-ssp_solution.pkl"
tm2_solution_path = "Mega-logs/Uninett2010.graphml/1505250729-uniform/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl"
```

**Compare Mega vs MegaOrder:**
```python
# Edit in script:
tm1_solution_path = "Mega-logs/Uninett2010.graphml/1505250729-uniform/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl"
tm2_solution_path = "Mega-order-logs/Uninett2010.graphml/1505250729-uniform/10-per_site/Uninett2010.graphml-10-ssp_solution.pkl"
```

## Output

The script outputs:

```
Mega Reordering Analysis Results
============================================================
Total srv-srv pairs in TM1: 5234
Total srv-srv pairs in TM2: 5128
Common srv-srv pairs: 4987

Stable pairs (same path): 4788
Reordered pairs (different path): 199
Pairs only in TM1: 247
Pairs only in TM2: 141

Stability rate: 96.01%
Reordering rate: 3.99%
============================================================

First 10 reordered pairs (srv_pair, tm1_path, tm2_path):
  (74, 84): path 1523 -> path 3245
  (75, 85): path 1523 -> path 3246
  (76, 86): path 1523 -> path 3247
  ...
```

## Metrics Explanation

- **Stable pairs**: srv-srv pairs assigned to the **same path** in both TM1 and TM2
- **Reordered pairs**: srv-srv pairs assigned to **different paths** in TM1 vs TM2
- **Stability rate**: `stable_pairs / common_pairs` (higher is better, ideal is 100%)
- **Reordering rate**: `reordered_pairs / common_pairs` (lower is better, ideal is 0%)

## Algorithm

1. **Load SSP solutions** from two `.pkl` files
2. **Initialize fixed path_num mapping** using complete path file (same logic as `SSP_ORDER_MAIN._init_fixed_path_nums`)
3. **Map solutions to fixed path_nums** to ensure consistent path numbering across TMs
4. **Count reordered pairs** by comparing path assignments

## Comparison with MegaOrder

- **Mega**: High reordering rate (5-20%) because each TM is optimized independently
- **MegaOrder**: Low reordering rate (<5%) because it maintains historical assignments

This script helps quantify the stability improvement of MegaOrder over Mega.
