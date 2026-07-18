"""P02 checkpoint-2 figures: L1/L2/L3 comparison and L3 calibration.
Reads only `results/planner_study/processed/P02_*` (produced by
`scripts/analyze_p02.py`, which must run first).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED_DIR = PROJECT_ROOT / "results" / "planner_study" / "processed"
FIGURES_DIR = PROJECT_ROOT / "results" / "planner_study" / "figures"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 200, "font.size": 10, "axes.titlesize": 11,
    "axes.labelsize": 10, "legend.fontsize": 9, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "pdf.fonttype": 42, "ps.fonttype": 42,
})

PLANNER_COLORS = {"L1": "#C44E52", "L2": "#55A868", "L3": "#4C72B0"}


def figure_l1_l2_l3_comparison():
    df = pd.read_csv(PROCESSED_DIR / "P02_l1_l2_l3_comparison.csv")
    fig, axes = plt.subplots(1, 3, figsize=(12, 4))
    metrics = [
        ("rejection_rate", "Rejection rate"), ("false_feasibility", "False feasibility rate"),
        ("operational_satisfaction", "Operational satisfaction rate"),
    ]
    for ax, (metric, label) in zip(axes, metrics):
        colors = [PLANNER_COLORS[level] for level in df["planner_level"]]
        ax.bar(df["planner_level"], df[metric], color=colors)
        ax.set_ylabel(label)
        ax.set_ylim(0, 1.05)
    fig.suptitle("L1 vs. L2 vs. L3: decision quality (P02, all combinations)", y=1.03)
    fig.savefig(FIGURES_DIR / "P02_l1_l2_l3_comparison.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P02_l1_l2_l3_comparison.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P02_l1_l2_l3_comparison")


def figure_calibration_curve():
    curve = pd.read_csv(PROCESSED_DIR / "P02_calibration_curve.csv")
    fig, ax = plt.subplots(figsize=(5, 5))
    ax.plot([0, 1], [0, 1], "--", color="#999", label="perfect calibration")
    ax.scatter(curve["mean_predicted"], curve["mean_actual"], s=curve["n"] * 3, color=PLANNER_COLORS["L3"], alpha=0.7)
    for _, row in curve.iterrows():
        ax.annotate(f"n={int(row['n'])}", (row["mean_predicted"], row["mean_actual"]), fontsize=7, xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("Mean predicted satisfaction probability")
    ax.set_ylabel("Actual satisfaction rate")
    ax.set_xlim(-0.05, 1.05)
    ax.set_ylim(-0.05, 1.05)
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("L3 calibration curve (P02)")
    fig.savefig(FIGURES_DIR / "P02_calibration_curve.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P02_calibration_curve.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P02_calibration_curve")


if __name__ == "__main__":
    figure_l1_l2_l3_comparison()
    figure_calibration_curve()
    print("DONE")
