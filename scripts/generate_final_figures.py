"""Fase K2: publication-quality figures for the article, built ONLY from
final campaigns (F01-F08, 20 seeds - see docs/results_provenance.md).
Never loads C01-C04 (pilot). matplotlib only, no seaborn.

Saves each figure as both PDF and PNG to results/figures/final/, plus a
sources.json mapping every figure to its campaign/data/n - checked by
scripts/audit_final_results.py.

Run: python scripts/generate_final_figures.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"
FIGURES_DIR = RESULTS_DIR / "figures" / "final"
FIGURES_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 200, "font.size": 10, "axes.titlesize": 11,
    "axes.labelsize": 10, "legend.fontsize": 9, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "axes.spines.top": False, "axes.spines.right": False,
})

SOURCES: dict[str, dict] = {}


def save_figure(fig, name: str, *, campaign: str, n: int, source_files: list[str], description: str) -> None:
    pdf_path = FIGURES_DIR / f"{name}.pdf"
    png_path = FIGURES_DIR / f"{name}.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight")
    plt.close(fig)
    SOURCES[name] = {"campaign": campaign, "n": n, "source_files": source_files, "description": description}
    print(f"saved {name} (n={n})")


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float, float]:
    """Wilson score interval - well-behaved at p near 0 or 1, unlike a
    naive normal approximation (relevant here: several cells have
    satisfaction rates of exactly 0 or 1 at n=20)."""
    if n == 0:
        return 0.0, 0.0, 0.0
    p = successes / n
    z = stats.norm.ppf(1 - alpha / 2)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return p, max(0.0, center - half), min(1.0, center + half)


def jitter(n: int, width: float = 0.12, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.uniform(-width, width, size=n)


STRATEGY_LABELS = {
    "shortest_hop_count": "Shortest hop\ncount", "least_loss": "Least\nloss", "highest_fidelity": "Highest\nfidelity",
}
STRATEGY_ORDER = ["shortest_hop_count", "least_loss", "highest_fidelity"]


def _boxplot_with_points(ax, groups: list[np.ndarray], labels: list[str], *, color="#4C72B0"):
    bp = ax.boxplot(groups, tick_labels=labels, showfliers=False, widths=0.5, patch_artist=True)
    for patch in bp["boxes"]:
        patch.set_facecolor(color)
        patch.set_alpha(0.35)
    for median in bp["medians"]:
        median.set_color("black")
        median.set_linewidth(1.5)
    for i, values in enumerate(groups, start=1):
        x = i + jitter(len(values), seed=i)
        ax.scatter(x, values, s=14, color=color, alpha=0.7, zorder=3, edgecolors="none")


# ---------------------------------------------------------------------------
# Routing (F02)
# ---------------------------------------------------------------------------
def figure_routing():
    f02 = pd.read_csv(RESULTS_DIR / "raw" / "F02_routing" / "trials.csv")
    n_seeds = f02["seed"].nunique()

    for scenario, log_scale in [("diamond_heterogeneous", True), ("small_mesh", False)]:
        sub = f02[f02["scenario"] == scenario]
        groups = [sub[sub["routing_strategy"] == s]["delivered_pairs"].to_numpy() for s in STRATEGY_ORDER]
        labels = [STRATEGY_LABELS[s] for s in STRATEGY_ORDER]

        fig, ax = plt.subplots(figsize=(5, 4))
        _boxplot_with_points(ax, groups, labels)
        if log_scale:
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
            ax.set_ylim(top=ax.get_ylim()[1] * 3.0)  # headroom for the annotation, log scale
        else:
            lo, hi = ax.get_ylim()
            ax.set_ylim(lo, hi + 0.12 * (hi - lo))
        ax.set_ylabel("Delivered pairs per trial")
        ax.set_title("End-to-end entanglement delivery under\nalternative routing strategies")
        ax.text(
            0.02, 0.98, f"{scenario.replace('_', ' ')}, n={n_seeds} seeds/strategy",
            transform=ax.transAxes, va="top", ha="left", fontsize=8, style="italic", color="#555",
        )
        save_figure(
            fig, f"Figure_Routing_DeliveredPairs_{scenario}", campaign="F02_routing", n=n_seeds,
            source_files=["results/raw/F02_routing/trials.csv"],
            description=f"delivered_pairs distribution by routing strategy, {scenario}, n=20 seeds/strategy"
                        + (" (log y-axis: least_loss operates ~50x higher than the other two strategies here)" if log_scale else ""),
        )

    # Satisfaction rate with Wilson CI, both scenarios in one figure
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), sharey=True)
    for ax, scenario in zip(axes, ["diamond_heterogeneous", "small_mesh"]):
        sub = f02[f02["scenario"] == scenario]
        rates, los, his, labels = [], [], [], []
        for s in STRATEGY_ORDER:
            group = sub[sub["routing_strategy"] == s]
            successes = int(group["satisfied"].sum())
            n = len(group)
            p, lo, hi = wilson_ci(successes, n)
            rates.append(p)
            los.append(p - lo)
            his.append(hi - p)
            labels.append(f"{STRATEGY_LABELS[s]}\n({successes}/{n})")
        x = np.arange(len(STRATEGY_ORDER))
        ax.errorbar(x, rates, yerr=[los, his], fmt="o", color="#4C72B0", capsize=4, markersize=7)
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
        ax.set_ylim(-0.05, 1.05)
        ax.set_title(scenario.replace("_", " "))
        ax.axhline(1.0, color="#ccc", linewidth=0.8, zorder=0)
    axes[0].set_ylabel("Satisfaction rate (Wilson 95% CI)")
    fig.suptitle("Intent satisfaction under alternative routing strategies", y=1.02)
    save_figure(
        fig, "Figure_Routing_Satisfaction", campaign="F02_routing", n=n_seeds,
        source_files=["results/raw/F02_routing/trials.csv"],
        description="satisfaction rate (SATISFIED / n) with Wilson 95% CI, by routing strategy, both F02 topologies",
    )

    # Fidelity boxplots
    for scenario in ["diamond_heterogeneous", "small_mesh"]:
        sub = f02[f02["scenario"] == scenario]
        groups = [sub[sub["routing_strategy"] == s]["average_fidelity"].dropna().to_numpy() for s in STRATEGY_ORDER]
        labels = [STRATEGY_LABELS[s] for s in STRATEGY_ORDER]
        fig, ax = plt.subplots(figsize=(5, 4))
        _boxplot_with_points(ax, groups, labels, color="#DD8452")
        ax.set_ylabel("Average fidelity (observed)")
        ax.set_title(f"Observed fidelity under alternative\nrouting strategies ({scenario.replace('_', ' ')})")
        save_figure(
            fig, f"Figure_Routing_Fidelity_{scenario}", campaign="F02_routing", n=n_seeds,
            source_files=["results/raw/F02_routing/trials.csv"],
            description=f"average_fidelity distribution by routing strategy, {scenario}, n=20 seeds/strategy",
        )


# ---------------------------------------------------------------------------
# Overhead (F06)
# ---------------------------------------------------------------------------
def figure_overhead():
    f06 = pd.read_csv(RESULTS_DIR / "raw" / "F06_overhead" / "trials.csv")
    n_seeds = f06["seed"].nunique()

    # Panel A: total trial wall time per condition (distribution, not just mean)
    # Panel B: orchestration sub-stage breakdown, ibqn_instrumented only (the
    # only condition with a full stage decomposition) - on its own scale,
    # since it is ~1000x smaller than simulation_wall_time_s.
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(10, 4.2))

    conditions = ["native_sequence", "static_provisioning", "ibqn_instrumented"]
    cond_labels = ["Native\nSeQUeNCe", "Static\nprovisioning", "IBQN\ninstrumented"]
    groups = [f06[f06["condition"] == c]["total_trial_wall_time_s"].dropna().to_numpy() for c in conditions]
    _boxplot_with_points(ax_a, groups, cond_labels, color="#4C72B0")
    ax_a.set_ylabel("Total trial wall time (s)")
    ax_a.set_title("(A) Total wall time per condition")

    stages = ["planning_wall_time_s", "deployment_wall_time_s", "assurance_wall_time_s", "reconciliation_decision_wall_time_s"]
    stage_labels = ["Planning", "Deployment", "Assurance", "Reconciliation\ndecision"]
    ibqn = f06[f06["condition"] == "ibqn_instrumented"]
    stage_means = [ibqn[s].mean() for s in stages]
    stage_ns = [ibqn[s].notna().sum() for s in stages]
    bars = ax_b.bar(stage_labels, stage_means, color="#55A868")
    for bar, n in zip(bars, stage_ns):
        ax_b.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"n={n}", ha="center", va="bottom", fontsize=8)
    ax_b.set_ylabel("Mean wall time (s)")
    ax_b.set_title("(B) IBQN orchestration sub-stages\n(note the y-axis scale vs. panel A)")

    fig.suptitle("Overhead decomposition: IBQN orchestration vs. simulation wall time", y=1.05)
    fig.subplots_adjust(bottom=0.28)
    fig.text(
        0.5, -0.12,
        "intent_parsing/intent_validation always 0 here (intent passed as an already-built object, not a file);\n"
        "route_application is not isolated from deployment; persistence is not measured on this instrumented path\n"
        "(the instrumentation defines 12 timing fields; 10 are observable in this instrumented path - see docs/overhead_methodology.md).",
        ha="center", fontsize=7.5, color="#555",
    )
    save_figure(
        fig, "Figure_Overhead_StageBreakdown", campaign="F06_overhead", n=n_seeds,
        source_files=["results/raw/F06_overhead/trials.csv"],
        description="(A) total wall time distribution per condition; (B) IBQN's own orchestration sub-stages "
                     "(planning/deployment/assurance/reconciliation_decision), n annotated per stage since "
                     "reconciliation_decision is only recorded when a violation triggers it",
    )

    # Overhead ratio: distribution, not just mean
    fig, ax = plt.subplots(figsize=(5.5, 4))
    ratio_groups = [f06[f06["condition"] == c]["orchestration_overhead_ratio"].dropna().to_numpy() * 100 for c in conditions]
    _boxplot_with_points(ax, ratio_groups, cond_labels, color="#C44E52")
    ax.set_ylabel("Orchestration overhead ratio (%)")
    ax.set_title("Orchestration overhead as a proportion\nof total trial wall time")
    save_figure(
        fig, "Figure_Overhead_Ratio", campaign="F06_overhead", n=n_seeds,
        source_files=["results/raw/F06_overhead/trials.csv"],
        description="orchestration_overhead_ratio distribution (not just mean) per condition, n=20 seeds/condition; "
                     "below 0.31% of trial wall time in every condition observed here (see docs/overhead_methodology.md "
                     "for the exact wording - never stated as an absolute/universal 'negligible')",
    )


# ---------------------------------------------------------------------------
# Resource semantics (F08)
# ---------------------------------------------------------------------------
def figure_resource_semantics():
    f08 = pd.read_csv(RESULTS_DIR / "raw" / "F08_resource_semantics" / "trials.csv")
    n_seeds = f08["seed"].nunique()
    slot_values = sorted(f08["reserved_memory_slots"].unique())
    duration_values = sorted(f08["duration_s"].unique())

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    metrics = [
        ("delivered_pairs", "Delivered pairs"), ("delivery_ratio", "Delivery ratio\n(delivered / min_delivered_pairs)"),
        ("deliveries_per_reserved_slot", "Deliveries per\nreserved_memory_slot"),
    ]
    colors = {duration_values[0]: "#4C72B0", duration_values[1]: "#DD8452"}
    for ax, (metric, ylabel) in zip(axes, metrics):
        for duration in duration_values:
            means, los, his = [], [], []
            for slots in slot_values:
                cell = f08[(f08["reserved_memory_slots"] == slots) & (f08["duration_s"] == duration)][metric]
                m = cell.mean()
                se = cell.std(ddof=1) / np.sqrt(len(cell))
                ci = stats.t.ppf(0.975, df=len(cell) - 1) * se
                means.append(m)
                los.append(ci)
                his.append(ci)
            ax.errorbar(
                slot_values, means, yerr=[los, his], fmt="o-", capsize=4,
                color=colors[duration], label=f"duration_s={duration}",
            )
        ax.set_xlabel("reserved_memory_slots")
        ax.set_ylabel(ylabel)
        ax.set_xticks(slot_values)
    axes[0].legend(loc="upper left", frameon=False)
    axes[1].axhline(1.0, color="#999", linewidth=0.8, linestyle="--", zorder=0)
    fig.suptitle(
        "Resource semantics: reserved_memory_slots sizes the pool,\nduration_s controls how many times it can be reused",
        y=1.06,
    )
    fig.text(
        0.5, -0.04,
        f"F08_resource_semantics, three_node topology, n={n_seeds} seeds/cell, mean +/- 95% CI. "
        "delivery_ratio > 1 means delivered_pairs exceeded min_delivered_pairs (over-delivery, not duplication or error).",
        ha="center", fontsize=8, color="#555",
    )
    save_figure(
        fig, "Figure_ResourceSemantics", campaign="F08_resource_semantics", n=n_seeds,
        source_files=["results/raw/F08_resource_semantics/trials.csv"],
        description="delivered_pairs/delivery_ratio/deliveries_per_reserved_slot vs. reserved_memory_slots, "
                     "faceted by duration_s, mean +/- 95% CI, n=20 seeds/cell",
    )


# ---------------------------------------------------------------------------
# Fidelity estimation error (F02 + F03 + F07 combined - every campaign that
# records estimated_fidelity/observed_fidelity)
# ---------------------------------------------------------------------------
def figure_fidelity_error():
    frames = []
    for campaign in ["F02_routing", "F03_purification", "F07_estimators"]:
        df = pd.read_csv(RESULTS_DIR / "raw" / campaign / "trials.csv")
        df["campaign"] = campaign
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.dropna(subset=["absolute_fidelity_error"])
    n_total = len(combined)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))

    # by estimator (only F07 varies it; F02/F03 are always conservative_min)
    estimators = sorted(combined["fidelity_estimator"].unique())
    groups = [combined[combined["fidelity_estimator"] == e]["absolute_fidelity_error"].to_numpy() for e in estimators]
    _boxplot_with_points(axes[0], groups, estimators, color="#4C72B0")
    axes[0].set_ylabel("Absolute fidelity error\n|estimated - observed|")
    axes[0].set_title("(A) By fidelity estimator\n(all campaigns combined)")

    # by campaign x topology
    short_campaign = {"F02_routing": "F02", "F03_purification": "F03", "F07_estimators": "F07"}
    combined["campaign_scenario"] = combined["campaign"].map(short_campaign) + ": " + combined["scenario"]
    labels = sorted(combined["campaign_scenario"].unique())
    groups2 = [combined[combined["campaign_scenario"] == label]["absolute_fidelity_error"].to_numpy() for label in labels]
    _boxplot_with_points(axes[1], groups2, labels, color="#55A868")
    axes[1].set_ylabel("Absolute fidelity error")
    axes[1].set_title("(B) By campaign / topology")
    axes[1].tick_params(axis="x", labelsize=8, rotation=25)
    for label in axes[1].get_xticklabels():
        label.set_ha("right")

    fig.suptitle("Planner fidelity-estimation error distribution", y=1.03)
    save_figure(
        fig, "Figure_FidelityEstimationError", campaign="F02+F03+F07", n=n_total,
        source_files=[
            "results/raw/F02_routing/trials.csv", "results/raw/F03_purification/trials.csv",
            "results/raw/F07_estimators/trials.csv",
        ],
        description=f"absolute_fidelity_error distribution, n={n_total} trials with a defined estimate (only "
                     "trials where the plan was feasible/accepted have both an estimated and observed fidelity), "
                     "grouped by (A) fidelity_estimator and (B) campaign/topology",
    )


# ---------------------------------------------------------------------------
# Reconciliation (F05, classified by scripts/classify_f05_recovery_types.py)
# ---------------------------------------------------------------------------
CASE_LABELS = {
    "route_change_recoverable": "Route change\n(recoverable)",
    "duration_increase_recoverable": "Duration increase\n(recoverable)",
    "slot_increase_recoverable": "Slot increase\n(recoverable)",
    "fidelity_ceiling_unrecoverable": "Fidelity ceiling\n(unrecoverable)",
    "severe_loss_attempt": "Severe loss\n(attempted, failed)",
}
CASE_ORDER = list(CASE_LABELS)


def figure_reconciliation():
    f05 = pd.read_csv(RESULTS_DIR / "processed" / "F05_reconciliation" / "trials_with_recovery_type.csv")
    n_seeds = f05["seed"].nunique()

    # 7.1 before-after, paired by seed, for cases where reconciliation was attempted
    before_after_cases = ["route_change_recoverable", "duration_increase_recoverable", "slot_increase_recoverable", "severe_loss_attempt"]
    fig, axes = plt.subplots(1, 4, figsize=(14, 4.5), sharex=True)
    for ax, case in zip(axes, before_after_cases):
        sub = f05[(f05["case"] == case) & (f05["reconciliation_attempted"])]
        for _, row in sub.iterrows():
            color = "#55A868" if row["recovered"] else "#C44E52"
            ax.plot([0, 1], [row["episode1_delivered_pairs"], row["episode2_delivered_pairs"]], color=color, alpha=0.5, linewidth=1.2)
            ax.scatter([0, 1], [row["episode1_delivered_pairs"], row["episode2_delivered_pairs"]], color=color, s=14, zorder=3)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Episode 1", "Episode 2"])
        ax.set_title(CASE_LABELS[case], fontsize=9)
        ax.set_xlim(-0.3, 1.3)
    axes[0].set_ylabel("Delivered pairs")
    from matplotlib.lines import Line2D
    legend_handles = [
        Line2D([0], [0], color="#55A868", label="recovered"), Line2D([0], [0], color="#C44E52", label="not recovered"),
    ]
    fig.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, 1.08), ncol=2, frameon=False)
    fig.suptitle("Reconciliation: episode 1 to episode 2, one line per seed", y=1.16)
    save_figure(
        fig, "Figure_Reconciliation_BeforeAfter", campaign="F05_reconciliation", n=n_seeds,
        source_files=["results/processed/F05_reconciliation/trials_with_recovery_type.csv"],
        description="delivered_pairs per seed, episode 1 -> episode 2, for the 3 recoverable cases plus the "
                     "severe_loss_attempt case (attempted, never recovers) - fidelity_ceiling_unrecoverable is "
                     "excluded here since it never reaches a second episode (no_action, see recovery-rate figure)",
    )

    # 7.2 recovery rate per class, with n and Wilson CI
    fig, ax = plt.subplots(figsize=(8, 4.5))
    xs, rates, los, his, labels = [], [], [], [], []
    for i, case in enumerate(CASE_ORDER):
        sub = f05[f05["case"] == case]
        attempted = sub[sub["reconciliation_attempted"]]
        if len(attempted) == 0:
            xs.append(i)
            rates.append(np.nan)
            los.append(0)
            his.append(0)
            labels.append(f"{CASE_LABELS[case]}\n(0 attempts / {len(sub)})")
            continue
        successes = int(attempted["recovered"].sum())
        n = len(attempted)
        p, lo, hi = wilson_ci(successes, n)
        xs.append(i)
        rates.append(p)
        los.append(p - lo)
        his.append(hi - p)
        labels.append(f"{CASE_LABELS[case]}\n({successes}/{n} attempted)")
    valid = [i for i, r in enumerate(rates) if not np.isnan(r)]
    ax.errorbar([xs[i] for i in valid], [rates[i] for i in valid], yerr=[[los[i] for i in valid], [his[i] for i in valid]], fmt="o", color="#4C72B0", capsize=4, markersize=8)
    # "no attempts" is NOT a 0% recovery rate - placed in its own lane above
    # the axis, with text, so it can never be misread as a data point
    invalid = [i for i, r in enumerate(rates) if np.isnan(r)]
    for i in invalid:
        ax.annotate("N/A\n(no_action:\nnever attempted)", xy=(i, -0.22), ha="center", va="top", fontsize=8, color="#888")
    ax.set_xticks(range(len(CASE_ORDER)))
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylim(-0.42, 1.05)
    ax.axhspan(-0.42, -0.05, color="#f5f5f5", zorder=0)
    ax.set_ylabel("Recovery rate among attempted\n(Wilson 95% CI)")
    ax.set_title("Reconciliation recovery rate by scenario class")
    save_figure(
        fig, "Figure_Reconciliation_RecoveryRate", campaign="F05_reconciliation", n=n_seeds,
        source_files=["results/processed/F05_reconciliation/trials_with_recovery_type.csv"],
        description="recovered / reconciliation_attempted with Wilson 95% CI, per scenario class; "
                     "fidelity_ceiling_unrecoverable shown as an x (0 attempts - no_action is the correct decision, "
                     "not a missing data point)",
    )

    # 7.3 additional cost distribution (wall time, episodes) for attempted cases
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    attempted_cases = [c for c in CASE_ORDER if c != "fidelity_ceiling_unrecoverable"]
    groups_time = [f05[(f05["case"] == c) & (f05["reconciliation_attempted"])]["additional_wall_time_s"].dropna().to_numpy() for c in attempted_cases]
    _boxplot_with_points(axes[0], groups_time, [CASE_LABELS[c] for c in attempted_cases], color="#8172B2")
    axes[0].set_ylabel("Additional wall time (s)")
    axes[0].set_title("(A) Additional wall time\n(episode 2, when attempted)")
    axes[0].tick_params(axis="x", labelsize=7.5)

    episode_counts = f05.groupby("case")["episodes"].value_counts().unstack(fill_value=0)
    episode_counts = episode_counts.reindex(CASE_ORDER)
    bottom = np.zeros(len(episode_counts))
    for col in sorted(episode_counts.columns):
        axes[1].bar([CASE_LABELS[c] for c in episode_counts.index], episode_counts[col], bottom=bottom, label=f"{col} episode(s)")
        bottom += episode_counts[col].to_numpy()
    axes[1].set_ylabel("Number of seeds")
    axes[1].set_title("(B) Episode count per scenario class")
    axes[1].tick_params(axis="x", labelsize=7.5, rotation=30)
    for label in axes[1].get_xticklabels():
        label.set_ha("right")
    axes[1].legend(frameon=False, fontsize=8)
    fig.suptitle("Reconciliation cost: additional wall time and episodes", y=1.03)
    save_figure(
        fig, "Figure_Reconciliation_AdditionalCost", campaign="F05_reconciliation", n=n_seeds,
        source_files=["results/processed/F05_reconciliation/trials_with_recovery_type.csv"],
        description="(A) additional_wall_time_s distribution for episode 2, by scenario class; "
                     "(B) how many seeds needed 1 vs. 2 episodes, by scenario class - route/duration/slot "
                     "adjustments themselves are a fixed 2x multiplier (apply_reconciliation_decision), not a "
                     "distribution, so their 'magnitude' is not separately plotted",
    )


# ---------------------------------------------------------------------------
# Assurance outcomes (F02 + F03, via F04's combined/categorized data)
# ---------------------------------------------------------------------------
STATUS_COLORS = {"SATISFIED": "#55A868", "VIOLATED": "#DD8452", "REJECTED": "#C44E52"}


def figure_assurance_outcomes():
    combined = pd.read_csv(RESULTS_DIR / "processed" / "F04_planner_vs_operation" / "combined_trials_with_categories.csv")
    n_total = len(combined)

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    # Panel A: F02, scenario x routing_strategy -> final_status counts
    f02 = combined[combined["source_campaign"] == "F02_routing"]
    pivot_a = f02.groupby(["scenario", "routing_strategy"])["final_status"].value_counts().unstack(fill_value=0)
    pivot_a = pivot_a.reindex(columns=["SATISFIED", "VIOLATED", "REJECTED"], fill_value=0)
    row_labels_a = [f"{s}\n{r}" for s, r in pivot_a.index]
    bottom = np.zeros(len(pivot_a))
    for status in ["SATISFIED", "VIOLATED", "REJECTED"]:
        vals = pivot_a[status].to_numpy()
        axes[0].barh(row_labels_a, vals, left=bottom, color=STATUS_COLORS[status], label=status)
        for i, (v, b) in enumerate(zip(vals, bottom)):
            if v > 0:
                axes[0].text(b + v / 2, i, str(int(v)), ha="center", va="center", fontsize=8, color="white")
        bottom += vals
    axes[0].set_xlabel("Number of trials (n per row = 20)")
    axes[0].set_title("(A) F02_routing: scenario x routing_strategy")

    # Panel B: F03, scenario x requested_fidelity -> final_status counts
    f03 = combined[combined["source_campaign"] == "F03_purification"]
    pivot_b = f03.groupby(["scenario", "requested_fidelity"])["final_status"].value_counts().unstack(fill_value=0)
    pivot_b = pivot_b.reindex(columns=["SATISFIED", "VIOLATED", "REJECTED"], fill_value=0)
    row_labels_b = [f"{s}\nf={f}" for s, f in pivot_b.index]
    bottom = np.zeros(len(pivot_b))
    for status in ["SATISFIED", "VIOLATED", "REJECTED"]:
        vals = pivot_b[status].to_numpy()
        axes[1].barh(row_labels_b, vals, left=bottom, color=STATUS_COLORS[status], label=status)
        for i, (v, b) in enumerate(zip(vals, bottom)):
            if v > 0:
                axes[1].text(b + v / 2, i, str(int(v)), ha="center", va="center", fontsize=7, color="white")
        bottom += vals
    axes[1].set_xlabel("Number of trials (n per row = 40: 2 purification policies x 20 seeds)")
    axes[1].set_title("(B) F03_purification: scenario x requested_fidelity")
    axes[1].tick_params(axis="y", labelsize=7.5)

    handles = [plt.Rectangle((0, 0), 1, 1, color=STATUS_COLORS[s]) for s in ["SATISFIED", "VIOLATED", "REJECTED"]]
    fig.legend(handles, ["SATISFIED", "VIOLATED", "REJECTED"], loc="upper center", bbox_to_anchor=(0.5, 1.05), ncol=3, frameon=False)
    fig.suptitle("Assurance outcomes emerge from real trials, not by construction", y=1.12)
    save_figure(
        fig, "Figure_AssuranceOutcomes", campaign="F02_routing+F03_purification", n=n_total,
        source_files=["results/processed/F04_planner_vs_operation/combined_trials_with_categories.csv"],
        description="counts of SATISFIED/VIOLATED/REJECTED per cell, (A) F02 by scenario x routing_strategy, "
                     "(B) F03 by scenario x requested_fidelity - all three states occur across both campaigns "
                     "without being separately forced (n=600 total trials, real final campaigns, not the 2-seed "
                     "pilot C03_assurance_outcomes)",
    )


# ---------------------------------------------------------------------------
# Purification (F03, with planner-rejection vs. oracle-confirmed distinction
# from F04)
# ---------------------------------------------------------------------------
def figure_purification():
    f03 = pd.read_csv(RESULTS_DIR / "raw" / "F03_purification" / "trials.csv")
    combined = pd.read_csv(RESULTS_DIR / "processed" / "F04_planner_vs_operation" / "combined_trials_with_categories.csv")
    oracle_categories = combined[combined["source_campaign"] == "F03_purification"].set_index("trial_id")["category"]

    for scenario in ["three_node_1_repeater", "linear_chain_2_repeaters"]:
        sub = f03[f03["scenario"] == scenario].copy()
        sub["category"] = sub["trial_id"].map(oracle_categories)
        thresholds = sorted(sub["requested_fidelity"].unique())

        # slightly offset x for "disabled" so exactly-overlapping points/lines
        # (e.g. both policies identical when purification never triggers)
        # remain visible as two distinct markers instead of one hidden underneath
        span = (max(thresholds) - min(thresholds)) or 1.0
        x_offset = span * 0.004
        policy_style = {
            "disabled": dict(color="#4C72B0", marker="s", linestyle="--", dx=-x_offset),
            "automatic": dict(color="#DD8452", marker="o", linestyle="-", dx=x_offset),
        }

        has_any_simulated_data = sub["observed_fidelity"].notna().any()

        fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
        if has_any_simulated_data:
            for policy, style in policy_style.items():
                pol_sub = sub[sub["purification_policy"] == policy]
                means = [pol_sub[pol_sub["requested_fidelity"] == t]["observed_fidelity"].mean() for t in thresholds]
                xs = [t + style["dx"] for t in thresholds]
                axes[0].plot(xs, means, marker=style["marker"], linestyle=style["linestyle"], color=style["color"], label=policy, markersize=6)
            axes[0].legend(frameon=False, title="purification_policy")
        else:
            axes[0].text(
                0.5, 0.5, f"100% REJECTED at every tested threshold\n({min(thresholds)}-{max(thresholds)}, both "
                          "policies) - no simulation ever ran,\nso there is no observed_fidelity to plot here.",
                transform=axes[0].transAxes, ha="center", va="center", fontsize=9.5, color="#555", wrap=True,
            )
        axes[0].set_xlabel("Requested min_fidelity")
        axes[0].set_ylabel("Observed average_fidelity\n(SATISFIED/VIOLATED trials only)")
        axes[0].set_title("(A) Observed fidelity")

        if has_any_simulated_data:
            for policy, style in policy_style.items():
                pol_sub = sub[sub["purification_policy"] == policy]
                means = [pol_sub[pol_sub["requested_fidelity"] == t]["delivered_pairs"].mean() for t in thresholds]
                xs = [t + style["dx"] for t in thresholds]
                axes[1].plot(xs, means, marker=style["marker"], linestyle=style["linestyle"], color=style["color"], label=policy, markersize=6)
        # mark rejected/untested vs. rejected/oracle-confirmed regions (data-space width, not points)
        band_width = span / max(len(thresholds) - 1, 1) * 0.9 if len(thresholds) > 1 else span * 0.05
        for t in thresholds:
            cell = sub[sub["requested_fidelity"] == t]
            categories_here = set(cell["category"].dropna().unique())
            if "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE" in categories_here:
                axes[1].axvspan(t - band_width / 2, t + band_width / 2, color="#C44E52", alpha=0.15, zorder=0)
            elif "INFEASIBLE_AND_REJECTED" in categories_here:
                axes[1].axvspan(t - band_width / 2, t + band_width / 2, color="#888", alpha=0.15, zorder=0)
        axes[1].set_xlabel("Requested min_fidelity")
        axes[1].set_ylabel("Delivered pairs\n(0 when REJECTED - no simulation ran)")
        axes[1].set_title("(B) Delivered pairs")

        legend_elements = [
            plt.Rectangle((0, 0), 1, 1, color="#C44E52", alpha=0.3, label="rejected by planner,\noracle confirms satisfiable"),
            plt.Rectangle((0, 0), 1, 1, color="#888", alpha=0.3, label="rejected by planner,\nnever oracle-tested"),
        ]
        existing_handles = axes[1].get_legend_handles_labels()[0] if has_any_simulated_data else []
        axes[1].legend(handles=existing_handles + legend_elements, frameon=False, fontsize=7, loc="lower right" if not has_any_simulated_data else "upper right")

        fig.suptitle(f"Purification: fidelity ceiling vs. planner rejection ({scenario})", y=1.03)
        extra_note = "" if has_any_simulated_data else " (100% REJECTED, never simulated - see panel A)"
        save_figure(
            fig, f"Figure_Purification_{scenario}", campaign="F03_purification", n=20,
            source_files=["results/raw/F03_purification/trials.csv", "results/processed/F04_planner_vs_operation/combined_trials_with_categories.csv"],
            description=f"(A) observed fidelity, (B) delivered pairs, vs. requested min_fidelity, {scenario}{extra_note}; "
                        "shaded bands distinguish 'rejected but oracle-confirmed satisfiable' from 'rejected, "
                        "never oracle-tested' - never labeled simply 'infeasible region'",
        )


# ---------------------------------------------------------------------------
# Planner vs. operation (F02+F03+F07, via F04)
# ---------------------------------------------------------------------------
def figure_planner_operation():
    combined = pd.read_csv(RESULTS_DIR / "processed" / "F04_planner_vs_operation" / "combined_trials_with_categories.csv")
    n_total = len(combined)

    # 9.1 estimated vs observed fidelity
    frames = []
    for campaign in ["F02_routing", "F03_purification", "F07_estimators"]:
        df = pd.read_csv(RESULTS_DIR / "raw" / campaign / "trials.csv")
        df["campaign"] = campaign
        frames.append(df)
    fid = pd.concat(frames, ignore_index=True).dropna(subset=["estimated_fidelity", "observed_fidelity"])

    fig, ax = plt.subplots(figsize=(6.5, 6))
    markers = {"diamond_heterogeneous": "o", "small_mesh": "s", "three_node_1_repeater": "^", "linear_chain_2_repeaters": "D"}
    colors = {"conservative_min": "#4C72B0", "sequence_consistent": "#DD8452"}
    for estimator in fid["fidelity_estimator"].unique():
        for scenario in fid["scenario"].unique():
            sub = fid[(fid["fidelity_estimator"] == estimator) & (fid["scenario"] == scenario)]
            if len(sub) == 0:
                continue
            ax.scatter(
                sub["estimated_fidelity"], sub["observed_fidelity"], s=22, alpha=0.6,
                color=colors.get(estimator, "#999"), marker=markers.get(scenario, "x"),
                label=f"{estimator} / {scenario}",
            )
    data_min = min(fid["estimated_fidelity"].min(), fid["observed_fidelity"].min())
    data_max = max(fid["estimated_fidelity"].max(), fid["observed_fidelity"].max())
    pad = (data_max - data_min) * 0.08 or 0.02
    lims = [data_min - pad, data_max + pad]
    ax.plot(lims, lims, "--", color="#999", linewidth=1, zorder=0, label="y = x")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel("Estimated fidelity (planner)")
    ax.set_ylabel("Observed fidelity (simulation)")
    ax.set_title("Planner fidelity estimate vs. observed outcome")
    ax.legend(fontsize=6.5, loc="upper left", ncol=1)
    save_figure(
        fig, "Figure_PlannerOperation_FidelityScatter", campaign="F02+F03+F07", n=len(fid),
        source_files=["results/raw/F02_routing/trials.csv", "results/raw/F03_purification/trials.csv", "results/raw/F07_estimators/trials.csv"],
        description=f"estimated vs. observed fidelity, n={len(fid)} trials with both defined (feasible/accepted "
                     "trials only), color=estimator, marker=topology, y=x reference line",
    )

    # 9.2 planner-operation matrix
    category_labels = {
        "FEASIBLE_AND_SATISFIED": "Feasible ->\nSATISFIED",
        "FEASIBLE_BUT_VIOLATED": "Feasible ->\nVIOLATED",
        "INFEASIBLE_AND_REJECTED": "Infeasible ->\nREJECTED\n(untested)",
        "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE": "Infeasible ->\nREJECTED\n(oracle: satisfiable)",
        "EXECUTION_FAILED": "EXECUTION_\nFAILED",
    }
    # explicit 6th category the user requested, even though it has 0 occurrences here
    order = ["FEASIBLE_AND_SATISFIED", "FEASIBLE_BUT_VIOLATED", "INFEASIBLE_AND_REJECTED",
             "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE", "INFEASIBLE_AND_ORACLE_REJECTED", "EXECUTION_FAILED"]
    counts = combined["category"].value_counts().to_dict()
    counts.setdefault("INFEASIBLE_AND_ORACLE_REJECTED", 0)  # no oracle-tested trial was ever confirmed truly infeasible
    counts.setdefault("EXECUTION_FAILED", 0)
    labels = [category_labels.get(c, c.replace("_", "\n")) for c in order]
    values = [counts.get(c, 0) for c in order]
    colors_bar = ["#55A868", "#DD8452", "#888", "#C44E52", "#4C72B0", "#7f7f7f"]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    bars = ax.bar(labels, values, color=colors_bar)
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), str(v), ha="center", va="bottom", fontsize=9)
    ax.set_ylabel("Number of trials")
    ax.set_title("Planner decision vs. operational outcome (n=600)")
    ax.tick_params(axis="x", labelsize=8)
    save_figure(
        fig, "Figure_PlannerOperation_Matrix", campaign="F02+F03", n=n_total,
        source_files=["results/processed/F04_planner_vs_operation/combined_trials_with_categories.csv"],
        description="6 planner-decision x operational-outcome categories, explicitly separating "
                     "'rejected, never oracle-tested' from 'rejected, oracle confirms satisfiable' from "
                     "'rejected, oracle confirms genuinely infeasible' (0 occurrences in this data - shown, not hidden)",
    )


if __name__ == "__main__":
    figure_routing()
    figure_overhead()
    figure_resource_semantics()
    figure_fidelity_error()
    figure_reconciliation()
    figure_assurance_outcomes()
    figure_purification()
    figure_planner_operation()
    (FIGURES_DIR / "sources.json").write_text(json.dumps(SOURCES, indent=2), encoding="utf-8")
    print("DONE")
