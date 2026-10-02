"""Figures for the calibrated ("realistic") campaign suite, drawn from the
processed tables `scripts/realistic/analyze_suite.py` writes - never from
hand-typed numbers. matplotlib only; every series is distinguishable by
marker/hatch as well as color.

  python scripts/realistic/generate_figures.py [--root results/realistic]

Writes <root>/figures/*.pdf and *.png. A figure whose table is missing is
skipped with a note.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_ROOT / "results" / "realistic"

HARDWARE = [("literature", "Literature hardware"), ("theoretical_ops", "Ideal local operations")]
POLICIES = [
    ("disabled", "No purification", "o", "#444444", "-"),
    ("once", "One round", "s", "#1f77b4", "--"),
    ("automatic", "Until target (1-round estimate)", "^", "#d95f02", "-."),
    ("iterative_analytical", "Until target (iterative estimate)", "D", "#2ca02c", ":"),
]
PLANNERS = ["L1", "L2", "L2-R", "L2-RB", "L3-RB"]
PLANNER_LABELS = {"L1": "One-\nround", "L2": "Iterative", "L2-R": "Res.-aware\nsame-cycle",
                  "L2-RB": "Res.-aware\nbuffered", "L3-RB": "Probabilistic\nbuffered", "L4": "Simulation\nin the loop"}

plt.rcParams.update({
    "font.size": 8, "axes.titlesize": 8.5, "axes.labelsize": 8, "legend.fontsize": 7, "xtick.labelsize": 7,
    "ytick.labelsize": 7, "figure.dpi": 150, "axes.grid": True, "grid.alpha": 0.3, "grid.linewidth": 0.5,
    "pdf.fonttype": 42,
})
SINGLE_COLUMN, DOUBLE_COLUMN = 3.5, 7.16  # IEEE conference column widths, inches


def save(fig, out_dir: Path, name: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(out_dir / f"{name}.png", bbox_inches="tight", dpi=220)
    plt.close(fig)
    print(f"wrote {name}.pdf / .png")


def errorbars(table: pd.DataFrame, prefix: str) -> np.ndarray:
    value = table[f"{prefix}_mean" if f"{prefix}_mean" in table else f"{prefix}_rate"]
    return np.vstack([(value - table[f"{prefix}_ci_low"]).clip(lower=0), (table[f"{prefix}_ci_high"] - value).clip(lower=0)])


# --------------------------------------------------------------------------
def fig_generation_model(processed: Path, out: Path) -> None:
    """Simulator vs planner generation laws, every audited chain."""
    table = pd.read_csv(processed / "r00_generation_model_audit.csv")
    table = table[~table["reverse"].astype(bool)]
    fig, ax = plt.subplots(figsize=(SINGLE_COLUMN, 2.7))
    markers = {0: "o", 1: "s", 2: "^", 3: "D"}
    for n, g in table.groupby("n_repeaters"):
        ax.errorbar(g["rate_model"], g["rate_measured"], yerr=g["rate_measured"] * g["1 sigma"], fmt=markers[n],
                    ms=4, mfc="none", color="#1f77b4", elinewidth=0.6, lw=0, label=f"buffered law, {n} rep." if n else "direct link")
    multi = table[table["n_repeaters"] > 0]
    ax.scatter(multi["rate_same_cycle"], multi["rate_measured"], marker="x", s=14, color="#d62728", lw=0.8,
               label="same-cycle law")
    lo, hi = 1e-6, 2e3
    ax.plot([lo, hi], [lo, hi], color="black", lw=0.7, ls="--")
    ax.set_xscale("log"), ax.set_yscale("log")
    ax.set_xlim(lo, hi), ax.set_ylim(5, hi)
    ax.set_xlabel("Planner model (end-to-end pairs/s)")
    ax.set_ylabel("Simulator (end-to-end pairs/s)")
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), frameon=False, ncol=2, columnspacing=1.0, handletextpad=0.3)
    save(fig, out, "fig_generation_model")


def fig_purification_policies(processed: Path, out: Path) -> None:
    """Delivered pairs per executed purification policy against the target
    fidelity, chain with one repeater, both hardware conditions."""
    table = pd.read_csv(processed / "r03_purification_by_policy.csv")
    fig, axes = plt.subplots(2, 2, figsize=(DOUBLE_COLUMN, 3.9), sharey="row")
    for row, topology in enumerate(["chain1", "chain2"]):
        for col, (hardware, title) in enumerate(HARDWARE):
            ax = axes[row][col]
            cell = table[(table["topology"] == topology) & (table["hardware"] == hardware)]
            if cell.empty:  # campaign still running for this cell
                ax.set_title(f"{title} - no data yet")
                continue
            for offset, (policy, label, marker, color, ls) in enumerate(POLICIES):
                g = cell[(cell["purification_policy"] == policy) & (cell["delivered_pairs_n"] > 0)].sort_values("requested_fidelity")
                if g.empty:
                    continue
                x = g["requested_fidelity"] + (offset - 1.5) * 0.0025
                ax.errorbar(x, g["delivered_pairs_mean"], yerr=errorbars(g, "delivered_pairs"), marker=marker, ms=3.5,
                            mfc="none", color=color, ls=ls, lw=0.9, elinewidth=0.6, capsize=1.5, label=label)
            ax.axhline(10, color="black", lw=0.6, ls=(0, (1, 2)))
            # targets every policy rejected at planning time (nothing was executed)
            by_target = cell.groupby("requested_fidelity").agg(rejected=("n_rejected", "sum"), trials=("seeds", "sum"))
            all_rejected = by_target.index[by_target["rejected"] == by_target["trials"]]
            targets = sorted(cell["requested_fidelity"].unique())
            if len(all_rejected):
                left = (max(t for t in targets if t < all_rejected.min()) + all_rejected.min()) / 2
                ax.axvspan(left, targets[-1] + 0.012, color="0.88", lw=0)
                ax.text((left + targets[-1] + 0.012) / 2, 0.5, "rejected at planning\nby every policy", ha="center",
                        va="center", fontsize=6.5, transform=ax.get_xaxis_transform())
            ax.set_xlim(targets[0] - 0.012, targets[-1] + 0.012)
            ax.set_title(f"{title} - {'one' if topology == 'chain1' else 'two'} repeater{'s' if topology == 'chain2' else ''}")
            if row == 1:
                ax.set_xlabel("Requested minimum fidelity")
            if col == 0:
                ax.set_ylabel("Delivered pairs in 0.3 s")
            ax.set_ylim(bottom=-2)
    handles, labels = axes[0][1].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, -0.03))
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, out, "fig_purification_policies")


def fig_planner_decision_quality(processed: Path, out: Path) -> None:
    """False feasibility (of executed admissions) and false rejection (of
    oracle-tested rejections) per planning model."""
    table = pd.read_csv(processed / "r04_planner_decision_quality.csv")
    has_oracle = "false_rejection_rate" in table
    fig, axes = plt.subplots(1, 2, figsize=(DOUBLE_COLUMN, 2.5), sharey=True)
    width = 0.38
    for ax, (hardware, title) in zip(axes, HARDWARE):
        cell = table[table["hardware"] == hardware].set_index("planner_level").reindex(PLANNERS)
        x = np.arange(len(PLANNERS))
        ff = cell["false_feasibility_rate"].to_numpy(dtype=float)
        ax.bar(x - width / 2, np.nan_to_num(ff), width, yerr=np.nan_to_num(errorbars(cell, "false_feasibility")), capsize=2,
               color="#d95f02", hatch="//", edgecolor="black", lw=0.5, error_kw=dict(lw=0.6), label="False feasibility")
        if has_oracle:
            fr = cell["false_rejection_rate"].to_numpy(dtype=float)
            ax.bar(x + width / 2, np.nan_to_num(fr), width, yerr=np.nan_to_num(errorbars(cell, "false_rejection")), capsize=2,
                   color="#1f77b4", hatch="..", edgecolor="black", lw=0.5, error_kw=dict(lw=0.6), label="False rejection")
            for xi, n in zip(x, cell["false_rejection_of"].fillna(0)):
                if n == 0:
                    ax.text(xi + width / 2, 0.02, "none\nrejected", ha="center", va="bottom", fontsize=5.5, rotation=90)
        for xi, n in zip(x, cell["false_feasibility_of"].fillna(0)):
            if n == 0:
                ax.text(xi - width / 2, 0.02, "none\nadmitted", ha="center", va="bottom", fontsize=5.5, rotation=90)
        ax.set_xticks(x, [PLANNER_LABELS[p] for p in PLANNERS])
        ax.set_title(title)
        ax.set_ylim(0, 1.05)
    axes[0].set_ylabel("Rate (95% Wilson interval)")
    axes[1].legend(loc="upper right", frameon=True)
    fig.tight_layout()
    save(fig, out, "fig_planner_decision_quality")


def fig_routing(processed: Path, out: Path) -> None:
    table = pd.read_csv(processed / "r02_routing.csv")
    strategies = [("shortest_hop_count", "Fewest hops", "//"), ("highest_fidelity", "Highest fidelity", ".."), ("least_loss", "Least loss", "xx")]
    fig, axes = plt.subplots(1, 2, figsize=(SINGLE_COLUMN, 2.3), sharey=True)
    for ax, topology in zip(axes, ["diamond", "mesh"]):
        x = np.arange(len(HARDWARE))
        for i, (strategy, label, hatch) in enumerate(strategies):
            cell = table[(table["topology"] == topology) & (table["routing_strategy"] == strategy)].set_index("hardware")
            cell = cell.reindex([h for h, _ in HARDWARE])
            ax.bar(x + (i - 1) * 0.27, cell["delivered_pairs_mean"].clip(lower=0.3), 0.27, yerr=errorbars(cell, "delivered_pairs"),
                   capsize=1.5, hatch=hatch, color="white", edgecolor="black", lw=0.5, error_kw=dict(lw=0.6), label=label)
        ax.axhline(10, color="black", lw=0.6, ls=(0, (1, 2)))
        ax.set_yscale("log")
        ax.set_xticks(x, ["Literature", "Ideal ops"])
        ax.set_title("Diamond" if topology == "diamond" else "Mesh")
    axes[0].set_ylabel("Delivered pairs in 0.3 s")
    axes[1].legend(loc="lower right", frameon=True, fontsize=6)
    fig.tight_layout()
    save(fig, out, "fig_routing")


def fig_reconciliation(processed: Path, out: Path) -> None:
    table = pd.read_csv(processed / "r06_reconciliation_by_case.csv")
    cases = [("route_change_recoverable", "Route\nchange"), ("duration_increase_recoverable", "Longer\nwindow"),
             ("slot_increase_recoverable", "More\nmemories"), ("decoherence_margin", "Decoherence\nmargin"),
             ("severe_loss_attempt", "Severe\nloss"), ("fidelity_ceiling_unrecoverable", "Fidelity\nceiling")]
    fig, axes = plt.subplots(1, 2, figsize=(DOUBLE_COLUMN, 2.3), sharey=True)
    for ax, (hardware, title) in zip(axes, HARDWARE):
        cell = table[table["hardware"] == hardware].set_index("case").reindex([c for c, _ in cases])
        x = np.arange(len(cases))
        ax.bar(x - 0.2, cell["initial_violated"].fillna(0), 0.4, color="white", hatch="//", edgecolor="black", lw=0.5,
               label="Violated in episode 1")
        ax.bar(x + 0.2, cell["recovered_count"].fillna(0), 0.4, color="#2ca02c", hatch="..", edgecolor="black", lw=0.5,
               label="Satisfied in episode 2")
        for xi, rejected in zip(x, cell["initial_rejected"].fillna(0)):
            if rejected:
                ax.text(xi, 0.5, f"{int(rejected)} rejected\nat planning", ha="center", va="bottom", fontsize=5.5)
        ax.set_xticks(x, [label for _, label in cases])
        ax.set_title(title)
    axes[0].set_ylabel("Intents (of 20 seeds)")
    axes[1].legend(loc="upper right", frameon=True)
    fig.tight_layout()
    save(fig, out, "fig_reconciliation")


def fig_resource_semantics(processed: Path, out: Path) -> None:
    table = pd.read_csv(processed / "r08_resource_semantics.csv")
    cell = table[table["hardware"] == "literature"].sort_values("slot_seconds")
    fig, ax = plt.subplots(figsize=(SINGLE_COLUMN, 2.2))
    for slots, marker in ((2, "o"), (4, "s")):
        g = cell[cell["reserved_memory_slots"] == slots]
        ax.errorbar(g["slot_seconds"], g["delivered_pairs_mean"], yerr=errorbars(g, "delivered_pairs"), marker=marker, ms=4,
                    mfc="none", lw=0, elinewidth=0.7, capsize=2, color="black", label=f"{slots} reserved memories")
    ax.axhline(cell["min_delivered_pairs"].iat[0], color="black", lw=0.6, ls=(0, (1, 2)))
    ax.set_xlabel("Reserved memories x window (memory-seconds)")
    ax.set_ylabel("Delivered pairs")
    ax.legend(loc="upper left", frameon=True)
    save(fig, out, "fig_resource_semantics")


FIGURES = [fig_generation_model, fig_purification_policies, fig_planner_decision_quality, fig_routing, fig_reconciliation,
           fig_resource_semantics]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    processed, out = args.root / "processed", args.root / "figures"
    for figure in FIGURES:
        try:
            figure(processed, out)
        except FileNotFoundError as exc:
            print(f"[skip] {figure.__name__}: {Path(exc.filename).name} not found")


if __name__ == "__main__":
    main()
