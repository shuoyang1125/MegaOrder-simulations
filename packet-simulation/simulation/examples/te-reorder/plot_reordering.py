#!/usr/bin/env python3
"""Plot N_reassigned (endpoint pairs moved to the short tunnel) vs
N_reordered (out-of-order packets detected at the receivers), from
experiment_summary.csv. Single series -> line chart with markers, no legend
box (the title names the series), hairline grid, direct label on the last
point only, plus a table printout.
"""
import csv
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# dataviz reference palette: series slot 1 (blue), light surface + chrome inks
SERIES = "#2a78d6"
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"

csv_path = sys.argv[1] if len(sys.argv) > 1 else "outputs/experiment_summary.csv"
out_path = sys.argv[2] if len(sys.argv) > 2 else "outputs/reordered_vs_reassigned.png"

rows = []
with open(csv_path) as f:
    for row in csv.DictReader(f):
        rows.append((int(row["reassigned_pairs"]),
                     int(row["reordered_packets"]),
                     int(row["seed"])))
rows.sort()
xs = [r[0] for r in rows]
ys = [r[1] for r in rows]

plt.rcParams.update({
    "font.family": "system-ui, -apple-system, Segoe UI, sans-serif",
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
})
fig, ax = plt.subplots(figsize=(7.2, 4.5), dpi=150)
fig.subplots_adjust(left=0.11, right=0.72, top=0.80, bottom=0.14)

ax.plot(xs, ys, color=SERIES, linewidth=2, solid_joinstyle="round",
        zorder=2)
ax.scatter(xs, ys, s=40, color=SERIES, edgecolors=SURFACE, linewidths=2,
           zorder=3)

# hairline solid grid, recessive; no top/right spines
for y in ax.get_yticks():
    if y == 0:
        continue
    ax.axhline(y, color=GRID, linewidth=1, zorder=1)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
for s in ("left", "bottom"):
    ax.spines[s].set_color(MUTED)
ax.tick_params(colors=MUTED, labelcolor=INK_2)
ax.grid(False)

ax.set_xlabel("Reassigned endpoint pairs (moved to the short tunnel at t = 0.5 s)",
              color=INK_2)
ax.set_ylabel("Out-of-order packets", color=INK_2)
ax.set_title("TE reconfiguration from the long tunnel to the short tunnel\n"
             "causes packet reordering at the receivers",
             loc="left", color=INK, fontsize=12, pad=12)

# direct label on the endpoint only; linear-fit reference in the subtitle
if len(xs) >= 2:
    slope = (ys[-1] - ys[0]) / (xs[-1] - xs[0])
    per_pair = ys[-1] / xs[-1] if xs[-1] else 0.0
    ax.annotate(f"{ys[-1]:,}", (xs[-1], ys[-1]), xytext=(8, 0),
                textcoords="offset points", va="center",
                color=INK, fontsize=10)
    ax.annotate(f"~{per_pair:.1f} reordered packets per reassigned pair",
                xy=(0.0, 1.02), xycoords="axes fraction",
                color=MUTED, fontsize=9, annotation_clip=False)

fig.savefig(out_path, facecolor=SURFACE)
print(f"saved {out_path}")

# table view twin
print()
print(f"{'seed':>5} {'reassigned_pairs':>17} {'reordered_packets':>18}")
for seed, x, y in sorted((r[2], r[0], r[1]) for r in rows):
    print(f"{seed:>5} {x:>17} {y:>18}")
