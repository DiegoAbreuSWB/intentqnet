"""Figures for the L3 attempt-rate audit (M6c). Reads only
`results/planner_study/processed/l3_attempt_rate_audit_*` (produced by
`scripts/audit_l3_attempt_rate.py`, which must run first).
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


def figure_predicted_vs_observed():
    raw = pd.read_csv(PROCESSED_DIR / "l3_attempt_rate_audit_raw.csv")
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.scatter(raw["observed_attempt_rate"], raw["predicted_rate_m2"], s=20, alpha=0.5, label="original model (multiplier=2)", color="#C44E52")
    ax.scatter(raw["observed_attempt_rate"], raw["predicted_rate_m7.32"], s=20, alpha=0.5, label="best-fit model (multiplier~7.32)", color="#55A868")
    lims = [0, max(raw["observed_attempt_rate"].max(), raw["predicted_rate_m2"].max()) * 1.05]
    ax.plot(lims, lims, "--", color="#999", label="perfect fit")
    ax.set_xlabel("Observed attempt rate (eg_attempts / duration_s)")
    ax.set_ylabel("Predicted attempt rate")
    ax.set_title("L3 attempt-rate audit: predicted vs. observed")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(FIGURES_DIR / "l3_attempt_rate_predicted_vs_observed.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "l3_attempt_rate_predicted_vs_observed.png", bbox_inches="tight")
    plt.close(fig)
    print("saved l3_attempt_rate_predicted_vs_observed")


def figure_ratio_by_multiplier():
    fit = pd.read_csv(PROCESSED_DIR / "l3_attempt_rate_audit_fit.csv")
    fig, ax = plt.subplots(figsize=(5.5, 4))
    ax.errorbar(
        fit["round_trip_multiplier"], fit["mean_predicted_over_observed_ratio"], yerr=fit["std_ratio"],
        marker="o", capsize=4, color="#4C72B0",
    )
    ax.axhline(1.0, color="#999", linestyle="--", label="perfect fit (ratio=1.0)")
    ax.set_xlabel("Round-trip multiplier assumed")
    ax.set_ylabel("Mean (predicted / observed) attempt rate")
    ax.set_title("Candidate round-trip multiplier fit")
    ax.legend(frameon=False, fontsize=8)
    fig.savefig(FIGURES_DIR / "l3_attempt_rate_ratio_by_multiplier.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "l3_attempt_rate_ratio_by_multiplier.png", bbox_inches="tight")
    plt.close(fig)
    print("saved l3_attempt_rate_ratio_by_multiplier")


def figure_error_by_hops_and_topology():
    by_hops = pd.read_csv(PROCESSED_DIR / "l3_attempt_rate_audit_by_hops.csv")
    by_scenario = pd.read_csv(PROCESSED_DIR / "l3_attempt_rate_audit_by_scenario.csv")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].bar(by_hops["hop_count"].astype(str), by_hops["ratio_m2_original"], color="#DD8452")
    axes[0].axhline(1.0, color="#999", linestyle="--")
    axes[0].set_xlabel("Hop count")
    axes[0].set_ylabel("Ratio (predicted/observed), original model")
    axes[0].set_title("(A) Error by hop count")

    axes[1].bar(by_scenario["scenario"], by_scenario["ratio_m2_original"], color="#8172B2")
    axes[1].axhline(1.0, color="#999", linestyle="--")
    axes[1].set_ylabel("Ratio (predicted/observed), original model")
    axes[1].set_title("(B) Error by topology")
    axes[1].tick_params(axis="x", rotation=20)

    fig.suptitle("L3 attempt-rate error breakdown (original multiplier=2 model)", y=1.03)
    fig.savefig(FIGURES_DIR / "l3_attempt_rate_error_breakdown.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "l3_attempt_rate_error_breakdown.png", bbox_inches="tight")
    plt.close(fig)
    print("saved l3_attempt_rate_error_breakdown")


if __name__ == "__main__":
    figure_predicted_vs_observed()
    figure_ratio_by_multiplier()
    figure_error_by_hops_and_topology()
    print("DONE")
