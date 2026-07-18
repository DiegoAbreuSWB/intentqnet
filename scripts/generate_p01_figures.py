"""P01 checkpoint-1 figures: L1 vs. L2 false-rejection resolution, fidelity
error, and planning cost. Reads only `results/planner_study/raw/P01_*` and
`results/planner_study/processed/P01_*` (produced by
`scripts/analyze_p01_l1_l2.py`, which must run first). matplotlib only, no
seaborn, no hardcoded values, Type 42 (not Type 3) fonts for eventual
inclusion in reports.
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "results" / "planner_study" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "results" / "planner_study" / "processed"
FIGURES_DIR = PROJECT_ROOT / "results" / "planner_study" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 200, "font.size": 10, "axes.titlesize": 11,
    "axes.labelsize": 10, "legend.fontsize": 9, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "pdf.fonttype": 42, "ps.fonttype": 42,
})

TOPOLOGY_LABELS = {"three_node": "Three-node chain", "four_node": "Four-node chain"}
PLANNER_LABELS = {"L1": "L1 (conservative, 1 round)", "L2": "L2 (iterative analytical)"}
PLANNER_COLORS = {"L1": "#C44E52", "L2": "#55A868"}


def figure_rejection_rate_by_level():
    cells = pd.read_csv(PROCESSED_DIR / "P01_l1_l2_comparison.csv")
    topologies = list(TOPOLOGY_LABELS)

    fig, axes = plt.subplots(1, len(topologies), figsize=(11, 4.2), sharey=True)
    for ax, topology in zip(axes, topologies):
        sub = cells[cells["topology"] == topology]
        for level in ["L1", "L2"]:
            level_sub = sub[sub["planner_level"] == level].sort_values("min_fidelity")
            ax.plot(
                level_sub["min_fidelity"], level_sub["rejection_rate"], marker="o",
                color=PLANNER_COLORS[level], label=PLANNER_LABELS[level],
            )
        ax.set_xlabel("Minimum requested fidelity")
        ax.set_title(TOPOLOGY_LABELS[topology])
        ax.set_ylim(-0.05, 1.05)
    axes[0].set_ylabel("Rejection rate")
    axes[0].legend(frameon=False, fontsize=8, loc="center left")
    fig.suptitle("Planner rejection rate: L1 vs. L2", y=1.03)
    fig.savefig(FIGURES_DIR / "P01_rejection_rate_by_level.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P01_rejection_rate_by_level.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P01_rejection_rate_by_level")


def figure_satisfaction_rate_by_level():
    """Companion to `figure_rejection_rate_by_level`: a 0% rejection rate
    does NOT mean success - on the four-node chain, L2 trades REJECTED for
    VIOLATED (planner accepts, but delivered_pairs falls short at
    execution time), never reaching SATISFIED at the lowest thresholds.
    Showing rejection rate alone would misleadingly suggest L2 "solves"
    the four-node chain the same way it solves the three-node chain."""
    cells = pd.read_csv(PROCESSED_DIR / "P01_l1_l2_comparison.csv")
    topologies = list(TOPOLOGY_LABELS)

    fig, axes = plt.subplots(1, len(topologies), figsize=(11, 4.2), sharey=True)
    for ax, topology in zip(axes, topologies):
        sub = cells[cells["topology"] == topology]
        for level in ["L1", "L2"]:
            level_sub = sub[sub["planner_level"] == level].sort_values("min_fidelity")
            ax.plot(
                level_sub["min_fidelity"], level_sub["satisfaction_rate"], marker="o",
                color=PLANNER_COLORS[level], label=PLANNER_LABELS[level],
            )
        ax.set_xlabel("Minimum requested fidelity")
        ax.set_title(TOPOLOGY_LABELS[topology])
        ax.set_ylim(-0.05, 1.05)
    axes[0].set_ylabel("Satisfaction rate\n(SATISFIED / n)")
    axes[0].legend(frameon=False, fontsize=8, loc="center left")
    fig.suptitle("Planner satisfaction rate: L1 vs. L2 (not the mirror of rejection rate - see VIOLATED)", y=1.03)
    fig.savefig(FIGURES_DIR / "P01_satisfaction_rate_by_level.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P01_satisfaction_rate_by_level.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P01_satisfaction_rate_by_level")


def figure_fidelity_error_by_level():
    frames = []
    for topology, campaign in [("three_node", "P01_l1_l2_purification_three_node"), ("four_node", "P01_l1_l2_purification_four_node")]:
        df = pd.read_csv(RAW_DIR / campaign / "trials.csv")
        df["topology"] = topology
        df["planner_level"] = df["purification_policy"].map({"automatic": "L1", "iterative_analytical": "L2"})
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["absolute_fidelity_error"])

    fig, ax = plt.subplots(figsize=(6, 4.2))
    groups, labels, colors = [], [], []
    for topology in TOPOLOGY_LABELS:
        for level in ["L1", "L2"]:
            sub = combined[(combined["topology"] == topology) & (combined["planner_level"] == level)]
            groups.append(sub["absolute_fidelity_error"].to_numpy())
            labels.append(f"{TOPOLOGY_LABELS[topology]}\n{PLANNER_LABELS[level]}")
            colors.append(PLANNER_COLORS[level])

    bp = ax.boxplot(groups, tick_labels=labels, showfliers=False, widths=0.5, patch_artist=True)
    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.35)
    for i, values in enumerate(groups, start=1):
        if len(values):
            rng = np.random.default_rng(i)
            x = i + rng.uniform(-0.1, 0.1, size=len(values))
            ax.scatter(x, values, s=10, color=colors[i - 1], alpha=0.6, zorder=3)
    ax.set_ylabel("Absolute fidelity-estimation error")
    ax.set_title("Fidelity-estimation error: L1 vs. L2 (SATISFIED/VIOLATED trials only)")
    ax.tick_params(axis="x", labelsize=7.5)
    fig.savefig(FIGURES_DIR / "P01_fidelity_error_by_level.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P01_fidelity_error_by_level.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P01_fidelity_error_by_level")


def figure_planning_time_by_level():
    cells = pd.read_csv(PROCESSED_DIR / "P01_l1_l2_comparison.csv")
    fig, ax = plt.subplots(figsize=(6, 4.2))
    x = np.arange(len(TOPOLOGY_LABELS))
    width = 0.35
    for i, level in enumerate(["L1", "L2"]):
        means = [
            cells[(cells.topology == t) & (cells.planner_level == level)]["mean_planning_time_s"].mean()
            for t in TOPOLOGY_LABELS
        ]
        ax.bar(x + (i - 0.5) * width, means, width, label=PLANNER_LABELS[level], color=PLANNER_COLORS[level])
    ax.set_xticks(x)
    ax.set_xticklabels(list(TOPOLOGY_LABELS.values()))
    ax.set_ylabel("Mean planning wall time (s)")
    ax.set_title("Planning cost: L1 vs. L2")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(FIGURES_DIR / "P01_planning_time_by_level.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P01_planning_time_by_level.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P01_planning_time_by_level")


if __name__ == "__main__":
    figure_rejection_rate_by_level()
    figure_satisfaction_rate_by_level()
    figure_fidelity_error_by_level()
    figure_planning_time_by_level()
    print("DONE")
