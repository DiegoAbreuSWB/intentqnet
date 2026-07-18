"""P03 checkpoint-2 figure: L4 cost (planning wall time) vs. K, per
scenario. Reads only `results/planner_study/processed/P03_l4_cost_summary.csv`
(produced by `scripts/analyze_p03_l4_cost.py`, which must run first).
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

SCENARIO_LABELS = {"three_node_favorable": "Favorable", "three_node_resource_marginal": "Resource-marginal"}
SCENARIO_COLORS = {"three_node_favorable": "#55A868", "three_node_resource_marginal": "#C44E52"}


def main() -> None:
    summary = pd.read_csv(PROCESSED_DIR / "P03_l4_cost_summary.csv")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    for scenario, group in summary.groupby("scenario"):
        group = group.sort_values("k")
        label = SCENARIO_LABELS.get(scenario, scenario)
        color = SCENARIO_COLORS.get(scenario, "#4C72B0")
        axes[0].plot(group["k"], group["mean_planning_time_s"], marker="o", label=label, color=color)
        axes[1].plot(group["k"], group["satisfaction_rate"], marker="o", label=label, color=color)

    axes[0].set_xlabel("K (internal simulations per candidate)")
    axes[0].set_ylabel("Mean planning wall time (s)")
    axes[0].set_title("(A) L4 planning cost vs. K")
    axes[0].legend(frameon=False, fontsize=8)

    axes[1].set_xlabel("K (internal simulations per candidate)")
    axes[1].set_ylabel("Satisfaction rate")
    axes[1].set_ylim(-0.05, 1.05)
    axes[1].set_title("(B) L4 satisfaction rate vs. K")

    fig.suptitle("P03: L4 cost/accuracy vs. K (reduced scope - see docs/planner_comparison_methodology.md)", y=1.04)
    fig.savefig(FIGURES_DIR / "P03_l4_cost_vs_k.pdf", bbox_inches="tight")
    fig.savefig(FIGURES_DIR / "P03_l4_cost_vs_k.png", bbox_inches="tight")
    plt.close(fig)
    print("saved P03_l4_cost_vs_k")


if __name__ == "__main__":
    main()
