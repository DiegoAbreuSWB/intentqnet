"""P02B / checkpoint 2B figures: L1/L2/L2-R/L3/L3-R decision quality,
L3-vs-L3-R calibration by region, threshold sensitivity, and cost. Reads
only results/planner_study/processed/P02b_* (produced by
scripts/analyze_p02b.py, which must run first).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
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

PLANNER_COLORS = {"L1": "#C44E52", "L2": "#DD8452", "L2-R": "#55A868", "L3": "#4C72B0", "L3-R": "#8172B2"}
PLANNER_ORDER = ["L1", "L2", "L2-R", "L3", "L3-R"]


def figure_decision_quality():
    df = pd.read_csv(PROCESSED_DIR / "P02b_decision_quality.csv")
    df = df.set_index("planner_level").reindex(PLANNER_ORDER).reset_index()
    fig, axes = plt.subplots(1, 4, figsize=(15, 4))
    metrics = [
        ("rejection_rate", "Rejection rate"), ("false_feasibility_rate", "False feasibility rate"),
        ("operational_satisfaction_rate", "Operational satisfaction rate"),
        ("balanced_accuracy_vs_oracle_proxy", "Balanced accuracy (vs. oracle proxy)"),
    ]
    for ax, (metric, label) in zip(axes, metrics):
        colors = [PLANNER_COLORS[level] for level in df["planner_level"]]
        ax.bar(df["planner_level"], df[metric], color=colors)
        ax.set_ylabel(label)
        ax.set_ylim(0, 1.05)
        ax.tick_params(axis="x", rotation=20)
    fig.suptitle("P02B: decision quality across the planner family", y=1.03)
    fig.savefig(FIGURES_DIR / "P02b_decision_quality.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P02b_decision_quality.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P02b_decision_quality")


def figure_calibration_by_region():
    curve = pd.read_csv(PROCESSED_DIR / "P02b_calibration_by_region.csv")
    curve = curve[curve["n"] > 0].copy()
    bins = curve["bin"].unique().tolist()
    fig, ax = plt.subplots(figsize=(7, 5))
    x = np.arange(len(bins))
    width = 0.35
    for i, level in enumerate(["L3", "L3-R"]):
        sub = curve[curve["planner_level"] == level].set_index("bin").reindex(bins)
        rates = sub["empirical_satisfaction_rate"].to_numpy(dtype=float)
        lo = sub["ci_low"].to_numpy(dtype=float)
        hi = sub["ci_high"].to_numpy(dtype=float)
        yerr = np.vstack([rates - lo, hi - rates])
        offset = (i - 0.5) * width
        ax.bar(x + offset, rates, width=width, yerr=yerr, capsize=3, label=level, color=PLANNER_COLORS[level])
        for xi, n in zip(x + offset, sub["n"]):
            if not np.isnan(n):
                ax.annotate(f"n={int(n)}", (xi, 0.02), fontsize=7, ha="center")
    ax.plot([-0.5, len(bins) - 0.5], [0, 1], "--", color="#999", alpha=0.4)
    ax.set_xticks(x)
    ax.set_xticklabels(bins, rotation=15)
    ax.set_ylabel("Empirical satisfaction rate (95% Wilson CI)")
    ax.set_ylim(0, 1.05)
    ax.set_title("L3 vs. L3-R: calibration by probability region (P02B)")
    ax.legend(frameon=False)
    fig.savefig(FIGURES_DIR / "P02b_calibration_by_region.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P02b_calibration_by_region.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P02b_calibration_by_region")


def figure_threshold_sensitivity():
    df = pd.read_csv(PROCESSED_DIR / "P02b_threshold_sensitivity.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for level in ["L3", "L3-R"]:
        sub = df[df["planner_level"] == level].sort_values("threshold")
        axes[0].plot(sub["threshold"], sub["admission_rate"], marker="o", label=level, color=PLANNER_COLORS[level])
        axes[1].plot(sub["threshold"], sub["operational_satisfaction"], marker="o", label=level, color=PLANNER_COLORS[level])
    axes[0].set_xlabel("Admission threshold")
    axes[0].set_ylabel("Admission rate")
    axes[0].set_title("(A) Does the threshold change decisions?")
    axes[0].set_ylim(0, 1.05)
    axes[1].set_xlabel("Admission threshold")
    axes[1].set_ylabel("Operational satisfaction rate")
    axes[1].set_title("(B) Resulting satisfaction rate")
    axes[1].set_ylim(0, 1.05)
    for ax in axes:
        ax.legend(frameon=False, fontsize=8)
    fig.suptitle("Threshold sensitivity: L3 vs. L3-R (P02B)", y=1.03)
    fig.savefig(FIGURES_DIR / "P02b_threshold_sensitivity.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P02b_threshold_sensitivity.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P02b_threshold_sensitivity")


def figure_cost():
    df = pd.read_csv(PROCESSED_DIR / "P02b_cost.csv")
    df = df.set_index("planner_level").reindex(PLANNER_ORDER).reset_index()
    fig, ax = plt.subplots(figsize=(6, 4))
    colors = [PLANNER_COLORS[level] for level in df["planner_level"]]
    ax.bar(df["planner_level"], df["mean_planning_time_s"] * 1000, color=colors)
    ax.set_ylabel("Mean planning wall time (ms)")
    ax.set_yscale("log")
    ax.set_title("P02B: planning cost across the planner family")
    ax.tick_params(axis="x", rotation=20)
    fig.savefig(FIGURES_DIR / "P02b_cost.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P02b_cost.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P02b_cost")


if __name__ == "__main__":
    figure_decision_quality()
    figure_calibration_by_region()
    figure_threshold_sensitivity()
    figure_cost()
    print("DONE")
