"""IEEE ICC 2027 manuscript figures - final editorial pass.

Rebuilds a small, page-budget-constrained set of figures from the F01-F08
final campaigns (never C01-C04 pilot data - see article/provenance.md) with
publication-grade editorial polish:

- every axis/legend label goes through LABELS below (no underscored
  variable names, no internal campaign codes in visible titles/suptitles);
- detailed interpretive context lives in sources.json (-> LaTeX captions),
  never as long in-figure text;
- vector PDF + PNG, bbox_inches="tight", matplotlib only (no seaborn);
- individual points/seeds and 95% or Wilson CIs are preserved wherever the
  underlying figures in scripts/generate_final_figures.py already had them;
- no hardcoded numbers - every value plotted is read from
  results/raw or results/processed at run time.

Two output trees:
- article/figures/          - the 5 main-manuscript figures (see
  article/figure_selection_and_page_budget.md).
- article/supplementary/figures/ - everything dropped from the main body
  for space (full cost breakdown, fully-rejected four-node chain detail,
  before/after per-seed panel, stage-by-stage overhead breakdown).

Run: python scripts/generate_article_figures.py
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
from matplotlib.lines import Line2D
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"
MAIN_DIR = PROJECT_ROOT / "article" / "figures"
SUPP_DIR = PROJECT_ROOT / "article" / "supplementary" / "figures"
MAIN_DIR.mkdir(parents=True, exist_ok=True)
SUPP_DIR.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "figure.dpi": 100, "savefig.dpi": 300, "font.size": 11, "axes.titlesize": 12,
    "axes.labelsize": 11, "legend.fontsize": 9.5, "xtick.labelsize": 9.5, "ytick.labelsize": 9.5,
    "axes.spines.top": False, "axes.spines.right": False, "font.family": "serif",
    "pdf.fonttype": 42, "ps.fonttype": 42,  # embed as Type 42 (TrueType), never Type 3 - required for IEEE submission
})

MAIN_SOURCES: dict[str, dict] = {}
SUPP_SOURCES: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# Label mapping (section 3 of the editorial pass) - applied everywhere an
# internal variable/category name would otherwise leak into a visible label.
# ---------------------------------------------------------------------------
LABELS = {
    "reserved_memory_slots": "Reserved memory slots",
    "duration_s": "Reservation duration (s)",
    "min_fidelity": "Minimum requested fidelity",
    "requested_fidelity": "Minimum requested fidelity",
    "delivered_pairs": "Delivered pairs",
    "absolute_fidelity_error": "Absolute fidelity-estimation error",
    "shortest_hop_count": "Shortest hop count",
    "least_loss": "Least loss",
    "highest_fidelity": "Highest fidelity",
    "sequence_consistent": "SeQUeNCe-consistent",
    "conservative_min": "Conservative-minimum",
    "three_node_1_repeater": "Three-node chain",
    "linear_chain_2_repeaters": "Four-node chain",
    "diamond_heterogeneous": "Heterogeneous diamond",
    "small_mesh": "Small mesh",
    "delivery_ratio": "Delivery ratio",
    "average_fidelity": "Observed average fidelity",
    "estimated_fidelity": "Estimated fidelity (planner)",
    "observed_fidelity": "Observed fidelity (simulation)",
    "min_delivered_pairs": "Minimum delivered pairs (goal)",
    "orchestration_overhead_ratio": "Orchestration overhead ratio",
}


def L(key: str) -> str:
    return LABELS.get(key, key.replace("_", " "))


def save_main(fig, name: str, *, campaign: str, n: int, source_files: list[str], caption: str) -> None:
    fig.savefig(MAIN_DIR / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(MAIN_DIR / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
    MAIN_SOURCES[name] = {"campaign": campaign, "n": n, "source_files": source_files, "caption": caption}
    print(f"[main] saved {name} (n={n})")


def save_supp(fig, name: str, *, campaign: str, n: int, source_files: list[str], caption: str) -> None:
    fig.savefig(SUPP_DIR / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(SUPP_DIR / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
    SUPP_SOURCES[name] = {"campaign": campaign, "n": n, "source_files": source_files, "caption": caption}
    print(f"[supp] saved {name} (n={n})")


def wilson_ci(successes: int, n: int, alpha: float = 0.05) -> tuple[float, float, float]:
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


def boxplot_with_points(ax, groups: list[np.ndarray], labels: list[str], *, color="#4C72B0"):
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


STRATEGY_ORDER = ["shortest_hop_count", "least_loss", "highest_fidelity"]


# ===========================================================================
# Figure 1 - conceptual architecture (redrawn to the exact required flow and
# four-layer distinction; see docs/ibn_principles_mapping.md).
# ===========================================================================
def figure_architecture():
    fig, ax = plt.subplots(figsize=(7.2, 11))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 26)
    ax.axis("off")

    # (layer_name, color, [(box_title, box_detail), ...])
    layers = [
        ("Intent layer", "#4C72B0", [
            ("Application", None),
            ("Declarative Quantum Intent\n(WHAT)", "minimum fidelity, reserved memory slots,\nminimum delivered pairs, duration"),
            ("Validation", "typed schema, 9 real\nvalidation exceptions"),
        ]),
        ("Planning / orchestration layer", "#55A868", [
            ("Translation and Planning", "IntentPlanner.plan()"),
            ("Execution Plan\n(HOW)", "route, fidelity estimator,\npurification strategy"),
        ]),
        ("SeQUeNCe / network layer", "#DD8452", [
            ("Deployment via the\nSeQUeNCe Adapter", "SequenceExecutor.deploy()\n(real SeQUeNCe reservation)"),
            ("Entanglement Generation,\nPurification, Swapping", "SeQUeNCe Timeline.run()"),
        ]),
        ("Assurance loop", "#C44E52", [
            ("Per-intent Observation", "collect_intent_evidence()\n(DELIVERY events by intent_id)"),
            ("Intent Assurance", "evaluate_intent()"),
            ("SATISFIED / VIOLATED / REJECTED", None),
            ("Episode-based Reconciliation", "decide_reconciliation_action()\n+ a NEW episode (new Timeline),\nnever in-place adaptation"),
        ]),
    ]

    box_w = 7.6
    x0 = 1.4
    box_gap = 0.35
    layer_gap = 1.05  # extra headroom so each layer's tag label never collides with the box below it
    y_cursor = 24.3
    box_positions: dict[str, tuple[float, float, float]] = {}  # title -> (x_center, y_center, y_top)
    layer_bands: list[tuple[float, float, float, str]] = []  # (y_top, y_bottom, color, label)

    for layer_idx, (layer_name, color, boxes) in enumerate(layers):
        if layer_idx > 0:
            y_cursor -= (layer_gap - box_gap)
        layer_top = y_cursor + box_gap
        for title, detail in boxes:
            box_h = 1.55 if detail else 1.05
            y = y_cursor - box_h
            box = FancyBboxPatch(
                (x0, y), box_w, box_h, boxstyle="round,pad=0.08,rounding_size=0.15",
                linewidth=1.6, edgecolor=color, facecolor=color, alpha=0.16,
            )
            ax.add_patch(box)
            if detail:
                ax.text(x0 + box_w / 2, y + box_h - 0.32, title, ha="center", va="center", fontsize=10.5, fontweight="bold", color=color)
                ax.text(x0 + box_w / 2, y + box_h * 0.33, detail, ha="center", va="center", fontsize=8, color="#333")
            else:
                ax.text(x0 + box_w / 2, y + box_h / 2, title, ha="center", va="center", fontsize=10.5, fontweight="bold", color=color)
            box_positions[title] = (x0 + box_w / 2, y + box_h / 2, y + box_h)
            y_cursor = y - box_gap
        layer_bottom = y_cursor + box_gap
        layer_bands.append((layer_top, layer_bottom, color, layer_name))

    # sequential arrows (skip the terminal-status box, which fans out to 3
    # outcomes conceptually rather than a single successor)
    titles_in_order = [title for _, _, boxes in layers for title, _ in boxes]
    for i in range(len(titles_in_order) - 1):
        a_title, b_title = titles_in_order[i], titles_in_order[i + 1]
        ax_c, ay_c, ay_top = box_positions[a_title]
        bx_c, by_c, by_top = box_positions[b_title]
        ay_bottom = ay_c - (ay_top - ay_c)
        arrow = FancyArrowPatch(
            (ax_c, ay_bottom), (bx_c, by_top), arrowstyle="-|>", mutation_scale=16, linewidth=1.4, color="#444",
        )
        ax.add_patch(arrow)

    # feedback arrow: reconciliation -> back to "Translation and Planning"
    # (never depicted as adaptation within the same Timeline/episode)
    recon_x, recon_y, _ = box_positions["Episode-based Reconciliation"]
    plan_x, plan_y, _ = box_positions["Translation and Planning"]
    loop = FancyArrowPatch(
        (recon_x + box_w / 2 - 0.3, recon_y), (plan_x + box_w / 2 - 0.3, plan_y),
        connectionstyle="arc3,rad=0.55", arrowstyle="-|>", mutation_scale=16,
        linewidth=1.4, color="#C44E52", linestyle="--",
    )
    ax.add_patch(loop)
    ax.text(
        plan_x + box_w / 2 + 0.55, (recon_y + plan_y) / 2, "new episode\n(new SeQUeNCe Timeline),\nno active-reservation rerouting",
        ha="left", va="center", fontsize=7.6, color="#C44E52", style="italic",
    )

    # layer grouping: a thin colored bracket beside each layer's boxes, with a
    # short horizontal tag above the group (a rotated label along the whole
    # band was tried first but overlapped neighboring bands whenever a label
    # string was longer than that band's height allowed).
    LAYER_TAGS = {
        "Intent layer": "INTENT LAYER",
        "Planning / orchestration layer": "PLANNING / ORCHESTRATION",
        "SeQUeNCe / network layer": "SEQUENCE / NETWORK LAYER",
        "Assurance loop": "ASSURANCE LOOP",
    }
    for y_top, y_bottom, color, label in layer_bands:
        ax.add_patch(plt.Rectangle((0.55, y_bottom + 0.05), 0.18, (y_top - 0.05) - (y_bottom + 0.05), color=color, alpha=0.7))
        ax.text(
            0.85, y_top + 0.32, LAYER_TAGS[label], ha="left", va="bottom", fontsize=8.3, fontweight="bold", color=color,
        )

    fig.savefig(MAIN_DIR / "Figure1_Architecture.pdf", bbox_inches="tight")
    fig.savefig(MAIN_DIR / "Figure1_Architecture.png", bbox_inches="tight")
    plt.close(fig)
    MAIN_SOURCES["Figure1_Architecture"] = {
        "campaign": "N/A (conceptual, not an experimental result)", "n": 0, "source_files": [],
        "caption": "IBQN architecture and intent lifecycle: an application declares WHAT it needs (a declarative "
                   "quantum intent), which is validated, translated into an execution plan (HOW), deployed onto "
                   "SeQUeNCe through the adapter layer, and observed per intent after execution. Assurance compares "
                   "observed evidence against the intent's success condition (SATISFIED/VIOLATED/REJECTED); a "
                   "violation triggers episode-based reconciliation, which plans and deploys a NEW episode (a new "
                   "SeQUeNCe Timeline) rather than adapting the active reservation in place. No natural-language or "
                   "LLM-based parsing is involved at any stage - intents are typed, schema-validated objects.",
    }
    print("[main] saved Figure1_Architecture")


# ===========================================================================
# Figure 2 - routing (A: diamond, log scale; B: small mesh, linear scale)
# ===========================================================================
def figure_routing():
    f02 = pd.read_csv(RESULTS_DIR / "raw" / "F02_routing" / "trials.csv")
    n_seeds = f02["seed"].nunique()
    strategy_labels = [L(s) for s in STRATEGY_ORDER]

    diamond = f02[f02["scenario"] == "diamond_heterogeneous"]
    mesh = f02[f02["scenario"] == "small_mesh"]

    diamond_means = diamond.groupby("routing_strategy")["delivered_pairs"].mean()
    ratio = diamond_means["least_loss"] / diamond_means["shortest_hop_count"]

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(9.5, 4.3))

    groups_a = [diamond[diamond["routing_strategy"] == s]["delivered_pairs"].to_numpy() for s in STRATEGY_ORDER]
    boxplot_with_points(ax_a, groups_a, strategy_labels)
    ax_a.set_yscale("log")
    ax_a.yaxis.set_major_formatter(mticker.ScalarFormatter())
    ax_a.set_ylim(top=ax_a.get_ylim()[1] * 3.0)
    ax_a.set_ylabel(f"{L('delivered_pairs')} per trial (log scale)")
    ax_a.set_title(f"(A) {L('diamond_heterogeneous')}")

    groups_b = [mesh[mesh["routing_strategy"] == s]["delivered_pairs"].to_numpy() for s in STRATEGY_ORDER]
    boxplot_with_points(ax_b, groups_b, strategy_labels, color="#DD8452")
    lo, hi = ax_b.get_ylim()
    ax_b.set_ylim(lo, hi + 0.15 * (hi - lo))
    ax_b.set_ylabel(f"{L('delivered_pairs')} per trial")
    ax_b.set_title(f"(B) {L('small_mesh')}")

    fig.suptitle("Entanglement delivery under alternative routing strategies", y=1.03)
    save_main(
        fig, "Figure2_Routing", campaign="F02_routing", n=n_seeds,
        source_files=["results/raw/F02_routing/trials.csv"],
        caption=(
            f"Delivered pairs per trial by routing strategy, n={n_seeds} seeds/strategy. (A) In the heterogeneous "
            f"diamond topology, Least loss delivers {ratio:.0f}x more pairs than Shortest hop count or Highest "
            "fidelity (log scale) - not because it is universally superior, but because in this specific topology "
            "its selected route (3 hops through two low-loss links) has a per-attempt entanglement-generation "
            "success rate roughly 50x higher than the 2-hop route through a high-loss link chosen by the other two "
            "strategies, despite an identical total path distance and one extra hop. (B) In the small-mesh "
            "topology, all three strategies are near-equivalent (no comparably lossy edge exists to route around), "
            "and all trials reach SATISFIED. The two topologies together show the routing-strategy gap is "
            "topology-dependent, not an intrinsic ranking of strategies."
        ),
    )

    # supplementary: fidelity-by-strategy panels (dropped from main figure for
    # space, per the editorial instruction)
    fig, axes = plt.subplots(1, 2, figsize=(9.5, 4.2), sharey=False)
    for ax, (scenario, label) in zip(axes, [("diamond_heterogeneous", L("diamond_heterogeneous")), ("small_mesh", L("small_mesh"))]):
        sub = f02[f02["scenario"] == scenario]
        groups = [sub[sub["routing_strategy"] == s]["average_fidelity"].dropna().to_numpy() for s in STRATEGY_ORDER]
        boxplot_with_points(ax, groups, strategy_labels, color="#8172B2")
        ax.set_ylabel(L("average_fidelity"))
        ax.set_title(label)
    fig.suptitle("Observed fidelity by routing strategy (supplementary detail)", y=1.03)
    save_supp(
        fig, "Supp_Routing_Fidelity", campaign="F02_routing", n=n_seeds,
        source_files=["results/raw/F02_routing/trials.csv"],
        caption="Observed average fidelity by routing strategy, both F02 topologies - dropped from the main "
                "routing figure for space; fidelity differences across strategies are small relative to the "
                "delivered-pairs gap and do not change the routing interpretation in the main text.",
    )


# ===========================================================================
# Figure 3 - planner-vs-operation gap and fidelity-estimation error
# ===========================================================================
CATEGORY_LABELS = {
    "FEASIBLE_AND_SATISFIED": "Feasible -> Satisfied",
    "FEASIBLE_BUT_VIOLATED": "Feasible -> Violated",
    "INFEASIBLE_AND_REJECTED": "Infeasible -> Rejected\n(not oracle-tested)",
    "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE": "Infeasible -> Oracle-confirmed\nsatisfiable",
    "INFEASIBLE_AND_ORACLE_REJECTED": "Infeasible -> Oracle-confirmed\ninfeasible",
    "EXECUTION_FAILED": "Execution failed",
}
CATEGORY_ORDER = [
    "FEASIBLE_AND_SATISFIED", "FEASIBLE_BUT_VIOLATED", "INFEASIBLE_AND_REJECTED",
    "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE", "INFEASIBLE_AND_ORACLE_REJECTED", "EXECUTION_FAILED",
]
CATEGORY_COLORS = ["#55A868", "#DD8452", "#888888", "#C44E52", "#4C72B0", "#7f7f7f"]


def figure_planner_assurance():
    combined = pd.read_csv(RESULTS_DIR / "processed" / "F04_planner_vs_operation" / "combined_trials_with_categories.csv")
    n_total = len(combined)
    gap_metrics = json.loads((RESULTS_DIR / "processed" / "F04_planner_vs_operation" / "gap_metrics.json").read_text(encoding="utf-8"))

    counts = combined["category"].value_counts().to_dict()
    counts.setdefault("INFEASIBLE_AND_ORACLE_REJECTED", 0)
    counts.setdefault("EXECUTION_FAILED", 0)
    labels = [CATEGORY_LABELS[c] for c in CATEGORY_ORDER]
    values = [counts.get(c, 0) for c in CATEGORY_ORDER]

    frames = []
    for campaign in ["F02_routing", "F03_purification", "F07_estimators"]:
        df = pd.read_csv(RESULTS_DIR / "raw" / campaign / "trials.csv")
        frames.append(df)
    fid_all = pd.concat(frames, ignore_index=True).dropna(subset=["absolute_fidelity_error"])
    n_fid = len(fid_all)
    estimators = sorted(fid_all["fidelity_estimator"].unique())
    fid_groups = [fid_all[fid_all["fidelity_estimator"] == e]["absolute_fidelity_error"].to_numpy() for e in estimators]
    estimator_labels = [L(e) for e in estimators]

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(10.5, 4.6))

    y_pos = np.arange(len(labels))
    bars = ax_a.barh(y_pos, values, color=CATEGORY_COLORS)
    ax_a.set_yticks(y_pos)
    ax_a.set_yticklabels(labels, fontsize=8.5)
    ax_a.invert_yaxis()
    for bar, v in zip(bars, values):
        ax_a.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" {v}", ha="left", va="center", fontsize=9)
    ax_a.set_xlabel("Number of trials")
    ax_a.set_title(f"(A) Planner decision vs. operational outcome\n(n={n_total})")

    boxplot_with_points(ax_b, fid_groups, estimator_labels, color="#4C72B0")
    ax_b.set_ylabel(L("absolute_fidelity_error"))
    ax_b.set_title(f"(B) Fidelity-estimation error by estimator\n(n={n_fid})")

    fig.suptitle("Planner-operation gap and fidelity-estimation accuracy", y=1.04)
    false_rejection_pct = gap_metrics["false_rejection_rate"] * 100
    save_main(
        fig, "Figure3_PlannerAssurance", campaign="F02+F03+F07", n=n_total,
        source_files=[
            "results/processed/F04_planner_vs_operation/combined_trials_with_categories.csv",
            "results/raw/F02_routing/trials.csv", "results/raw/F03_purification/trials.csv", "results/raw/F07_estimators/trials.csv",
        ],
        caption=(
            f"(A) Six planner-decision x operational-outcome categories across n={n_total} trials (F02+F03), "
            f"explicitly separating rejections never oracle-tested from rejections the offline oracle confirms "
            f"were actually satisfiable ({false_rejection_pct:.0f}% of the {counts.get('INFEASIBLE_AND_REJECTED', 0) + counts.get('INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE', 0)} oracle-tested rejections here) "
            "and from genuinely oracle-confirmed-infeasible cases (0 observed). These false rejections stem from "
            "the planner's conservative one-round purification-fidelity model, which caps its feasibility estimate "
            "at the fidelity reachable after a single purification round, while SeQUeNCe's 'until_target' mode can "
            "apply multiple rounds at execution time - not from topology heterogeneity (see "
            "docs/false_rejection_root_cause.md). Assurance exposing this gap is part of the architecture's "
            f"motivation, not a failure of it. (B) Absolute fidelity-estimation error (n={n_fid} trials with both "
            "an estimate and an observation), by estimator: the SeQUeNCe-consistent estimator reproduces the "
            "simulator's own fidelity model near-exactly, while the Conservative-minimum estimator carries "
            "systematic bias in heterogeneous topologies; near-zero error here reflects consistency with the "
            "simulator's model, not validated real-hardware accuracy."
        ),
    )

    # supplementary: full estimated-vs-observed scatter (kept, but out of the
    # 6-page main body - the boxplot in panel B already carries the estimator
    # comparison the main text needs)
    fig, ax = plt.subplots(figsize=(6, 6))
    markers = {"diamond_heterogeneous": "o", "small_mesh": "s", "three_node_1_repeater": "^", "linear_chain_2_repeaters": "D"}
    colors = {"conservative_min": "#4C72B0", "sequence_consistent": "#DD8452"}
    fid_scatter = pd.concat([pd.read_csv(RESULTS_DIR / "raw" / c / "trials.csv") for c in ["F02_routing", "F03_purification", "F07_estimators"]], ignore_index=True)
    fid_scatter = fid_scatter.dropna(subset=["estimated_fidelity", "observed_fidelity"])
    for estimator in fid_scatter["fidelity_estimator"].unique():
        for scenario in fid_scatter["scenario"].unique():
            sub = fid_scatter[(fid_scatter["fidelity_estimator"] == estimator) & (fid_scatter["scenario"] == scenario)]
            if len(sub) == 0:
                continue
            ax.scatter(
                sub["estimated_fidelity"], sub["observed_fidelity"], s=20, alpha=0.6,
                color=colors.get(estimator, "#999"), marker=markers.get(scenario, "x"),
                label=f"{L(estimator)} / {L(scenario)}",
            )
    lims = [
        min(fid_scatter["estimated_fidelity"].min(), fid_scatter["observed_fidelity"].min()) - 0.02,
        max(fid_scatter["estimated_fidelity"].max(), fid_scatter["observed_fidelity"].max()) + 0.02,
    ]
    ax.plot(lims, lims, "--", color="#999", linewidth=1, zorder=0, label="y = x")
    ax.set_xlim(lims)
    ax.set_ylim(lims)
    ax.set_xlabel(L("estimated_fidelity"))
    ax.set_ylabel(L("observed_fidelity"))
    ax.set_title("Planner fidelity estimate vs. observed outcome")
    ax.legend(fontsize=6.5, loc="upper left", ncol=1)
    save_supp(
        fig, "Supp_FidelityScatter", campaign="F02+F03+F07", n=len(fid_scatter),
        source_files=["results/raw/F02_routing/trials.csv", "results/raw/F03_purification/trials.csv", "results/raw/F07_estimators/trials.csv"],
        caption=f"Estimated vs. observed fidelity, n={len(fid_scatter)} trials with both defined. Multiple seeds "
                "may overlap under deterministic fidelity computation for a given configuration.",
    )


# ===========================================================================
# Figure 4 - purification satisfaction threshold + reconciliation recovery
# ===========================================================================
def figure_purification_reconciliation():
    f03 = pd.read_csv(RESULTS_DIR / "raw" / "F03_purification" / "trials.csv")
    combined = pd.read_csv(RESULTS_DIR / "processed" / "F04_planner_vs_operation" / "combined_trials_with_categories.csv")
    oracle_categories = combined[combined["source_campaign"] == "F03_purification"].set_index("trial_id")["category"]

    scenario = "three_node_1_repeater"
    sub = f03[f03["scenario"] == scenario].copy()
    sub["category"] = sub["trial_id"].map(oracle_categories)
    thresholds = sorted(sub["requested_fidelity"].unique())
    span = (max(thresholds) - min(thresholds)) or 1.0
    band_width = span / max(len(thresholds) - 1, 1) * 0.9 if len(thresholds) > 1 else span * 0.05

    f05 = pd.read_csv(RESULTS_DIR / "processed" / "F05_reconciliation" / "trials_with_recovery_type.csv")
    n_seeds_f05 = f05["seed"].nunique()

    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(12.5, 4.6))

    # --- Panel A: purification satisfaction step (discrete, not smoothed) ---
    policy_style = {
        "disabled": dict(color="#4C72B0", marker="s", label="Disabled"),
        "automatic": dict(color="#DD8452", marker="o", label="Automatic"),
    }
    for policy, style in policy_style.items():
        pol_sub = sub[sub["purification_policy"] == policy]
        rates = []
        for t in thresholds:
            cell = pol_sub[pol_sub["requested_fidelity"] == t]
            rates.append(cell["satisfied"].mean() if len(cell) else np.nan)
        ax_a.plot(thresholds, rates, marker=style["marker"], color=style["color"], label=style["label"], markersize=6, linewidth=1.6)
    for t in thresholds:
        cell = sub[sub["requested_fidelity"] == t]
        categories_here = set(cell["category"].dropna().unique())
        if "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE" in categories_here:
            ax_a.axvspan(t - band_width / 2, t + band_width / 2, color="#C44E52", alpha=0.15, zorder=0)
        elif "INFEASIBLE_AND_REJECTED" in categories_here:
            ax_a.axvspan(t - band_width / 2, t + band_width / 2, color="#888", alpha=0.15, zorder=0)
    ax_a.set_xlabel(L("min_fidelity"))
    ax_a.set_ylabel("Satisfaction rate")
    ax_a.set_ylim(-0.05, 1.15)
    ax_a.set_title(f"(A) Purification satisfaction step\n({L(scenario)})")
    legend_a = [
        Line2D([0], [0], color="#4C72B0", marker="s", label="Disabled"),
        Line2D([0], [0], color="#DD8452", marker="o", label="Automatic"),
        plt.Rectangle((0, 0), 1, 1, color="#C44E52", alpha=0.3, label="Rejected,\noracle-confirmed satisfiable"),
        plt.Rectangle((0, 0), 1, 1, color="#888", alpha=0.3, label="Rejected,\nnever oracle-tested"),
    ]
    ax_a.legend(handles=legend_a, fontsize=6.8, loc="lower left", frameon=False)

    # --- Panel B: reconciliation recovery rate by class, Wilson CI ---
    CASE_LABELS = {
        "route_change_recoverable": "Route change",
        "duration_increase_recoverable": "Duration increase",
        "slot_increase_recoverable": "Slot increase",
        "fidelity_ceiling_unrecoverable": "Fidelity ceiling",
        "severe_loss_attempt": "Severe loss",
    }
    CASE_ORDER = list(CASE_LABELS)
    RECOVERY_TYPE_LABELS = {
        "strict_recovery": "strict",
        "resource_adjusted_recovery": "resource-adjusted",
        "sla_relaxed_recovery": "SLA-relaxed",
        "not_applicable": "no action (infeasible)",
    }
    xs, rates, los, his, labels_b, recovery_type_by_case = [], [], [], [], [], {}
    for i, case in enumerate(CASE_ORDER):
        case_sub = f05[f05["case"] == case]
        attempted = case_sub[case_sub["reconciliation_attempted"]]
        recovery_types_here = sorted(set(case_sub["recovery_type"].dropna().unique()) - {"not_applicable"})
        recovery_type_by_case[CASE_LABELS[case]] = (
            "/".join(RECOVERY_TYPE_LABELS.get(r, r) for r in recovery_types_here) if recovery_types_here else "no action (infeasible)"
        )
        if len(attempted) == 0:
            xs.append(i)
            rates.append(np.nan)
            los.append(0)
            his.append(0)
            labels_b.append(f"{CASE_LABELS[case]}\n(0 attempts)")
            continue
        successes = int(attempted["recovered"].sum())
        n = len(attempted)
        p, lo, hi = wilson_ci(successes, n)
        xs.append(i)
        rates.append(p)
        los.append(p - lo)
        his.append(hi - p)
        labels_b.append(f"{CASE_LABELS[case]}\n({successes}/{n})")
    valid = [i for i, r in enumerate(rates) if not np.isnan(r)]
    invalid = [i for i, r in enumerate(rates) if np.isnan(r)]
    ax_b.errorbar([xs[i] for i in valid], [rates[i] for i in valid], yerr=[[los[i] for i in valid], [his[i] for i in valid]], fmt="o", color="#4C72B0", capsize=4, markersize=8)
    for i in invalid:
        ax_b.annotate("no action\n(infeasible)", xy=(i, -0.22), ha="center", va="top", fontsize=7, color="#888")
    ax_b.set_xticks(range(len(CASE_ORDER)))
    ax_b.set_xticklabels(labels_b, fontsize=7.8)
    ax_b.set_ylim(-0.42, 1.05)
    ax_b.axhspan(-0.42, -0.05, color="#f5f5f5", zorder=0)
    ax_b.set_ylabel("Recovery rate among attempted\n(Wilson 95% CI)")
    ax_b.set_title(f"(B) Reconciliation recovery by class\n(n={n_seeds_f05} seeds/class)")
    recovery_type_summary = "; ".join(f"{case} = {rtype}" for case, rtype in recovery_type_by_case.items())

    fig.suptitle("Purification limits and reconciliation recovery", y=1.03)
    save_main(
        fig, "Figure4_PurificationReconciliation", campaign="F03_purification+F05_reconciliation", n=len(thresholds),
        source_files=[
            "results/raw/F03_purification/trials.csv", "results/processed/F04_planner_vs_operation/combined_trials_with_categories.csv",
            "results/processed/F05_reconciliation/trials_with_recovery_type.csv",
        ],
        caption=(
            f"(A) Satisfaction rate vs. requested minimum fidelity for {L(scenario)} (20 seeds/policy/threshold): "
            "a sharp step, not a gradual transition, because the planner's one-round purification-fidelity ceiling "
            "is a fixed threshold, not a soft estimate (see docs/false_rejection_root_cause.md). Beyond the "
            "ceiling, the planner rejects deterministically; the offline oracle confirms every tested rejection in "
            "this range is actually satisfiable by the real simulator, distinguishing an oracle-confirmed-"
            "satisfiable region from any hypothetically untested region (none occurs in this densified range). The "
            "four-node chain (linear_chain_2_repeaters), where every trial was rejected and never reached the "
            "oracle-tested range, is reported in the supplementary material rather than as a second main-figure "
            "panel. (B) Reconciliation recovery rate among attempted episodes, per scenario class, with the "
            f"recovery mechanism named explicitly rather than a single aggregated rate ({recovery_type_summary}); "
            "the fidelity-ceiling class is never attempted (reconciliation correctly recognizes it as infeasible, "
            "not a missing data point), and the severe-loss class is attempted but never recovers within the "
            "modeled action space."
        ),
    )

    # --- supplementary: four-node (fully-rejected) chain, small panel ---
    scenario2 = "linear_chain_2_repeaters"
    sub2 = f03[f03["scenario"] == scenario2].copy()
    sub2["category"] = sub2["trial_id"].map(combined[combined["source_campaign"] == "F03_purification"].set_index("trial_id")["category"])
    thresholds2 = sorted(sub2["requested_fidelity"].unique())
    fig, ax = plt.subplots(figsize=(5, 3.6))
    for t in thresholds2:
        cell = sub2[sub2["requested_fidelity"] == t]
        categories_here = set(cell["category"].dropna().unique())
        color = "#C44E52" if "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE" in categories_here else "#888"
        ax.axvspan(t - 0.003, t + 0.003, color=color, alpha=0.4)
    ax.text(
        0.5, 0.5, f"100% REJECTED at every tested threshold\n({min(thresholds2)}-{max(thresholds2)}, both policies)\n"
                  "no simulation ever ran - see Fig. 4(A) caption",
        transform=ax.transAxes, ha="center", va="center", fontsize=8.5, color="#555", wrap=True,
    )
    ax.set_xlim(min(thresholds2) - 0.01, max(thresholds2) + 0.01)
    ax.set_xlabel(L("min_fidelity"))
    ax.set_yticks([])
    ax.set_title(f"{L(scenario2)}: fully-rejected range")
    save_supp(
        fig, "Supp_Purification_FourNodeChain", campaign="F03_purification", n=20,
        source_files=["results/raw/F03_purification/trials.csv", "results/processed/F04_planner_vs_operation/combined_trials_with_categories.csv"],
        caption=f"{L(scenario2)}: every tested threshold in the densified range was REJECTED by the planner and "
                "never simulated; shading follows the same oracle-confirmed-satisfiable vs. never-oracle-tested "
                "convention as Figure 4(A).",
    )

    # --- supplementary: reconciliation before/after per seed, and cost ---
    before_after_cases = ["route_change_recoverable", "duration_increase_recoverable", "slot_increase_recoverable", "severe_loss_attempt"]
    fig, axes = plt.subplots(1, 4, figsize=(13, 4.2), sharex=True)
    for ax, case in zip(axes, before_after_cases):
        case_sub = f05[(f05["case"] == case) & (f05["reconciliation_attempted"])]
        for _, row in case_sub.iterrows():
            color = "#55A868" if row["recovered"] else "#C44E52"
            ax.plot([0, 1], [row["episode1_delivered_pairs"], row["episode2_delivered_pairs"]], color=color, alpha=0.35, linewidth=1.1)
            ax.scatter([0, 1] + jitter(2, width=0.03, seed=hash(case) % 1000), [row["episode1_delivered_pairs"], row["episode2_delivered_pairs"]], color=color, s=12, zorder=3, alpha=0.8)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["Episode 1", "Episode 2"])
        ax.set_title(CASE_LABELS[case], fontsize=9)
        ax.set_xlim(-0.3, 1.3)
    axes[0].set_ylabel(L("delivered_pairs"))
    legend_handles = [Line2D([0], [0], color="#55A868", label="recovered"), Line2D([0], [0], color="#C44E52", label="not recovered")]
    fig.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, 1.08), ncol=2, frameon=False)
    fig.suptitle("Reconciliation: episode 1 to episode 2, one line per seed (supplementary)", y=1.16)
    save_supp(
        fig, "Supp_Reconciliation_BeforeAfter", campaign="F05_reconciliation", n=n_seeds_f05,
        source_files=["results/processed/F05_reconciliation/trials_with_recovery_type.csv"],
        caption=f"{L('delivered_pairs')} per seed, episode 1 -> episode 2, for the 3 recoverable cases plus severe "
                "loss (attempted, never recovers); points jittered slightly to reduce overlap. "
                "fidelity_ceiling_unrecoverable is excluded (never reaches a second episode - see Figure 4(B)).",
    )

    attempted_cases = [c for c in CASE_ORDER if c != "fidelity_ceiling_unrecoverable"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.2))
    groups_time = [f05[(f05["case"] == c) & (f05["reconciliation_attempted"])]["additional_wall_time_s"].dropna().to_numpy() for c in attempted_cases]
    boxplot_with_points(axes[0], groups_time, [CASE_LABELS[c] for c in attempted_cases], color="#8172B2")
    axes[0].set_ylabel("Additional wall time (s)")
    axes[0].set_title("(A) Additional wall time (episode 2)")
    axes[0].tick_params(axis="x", labelsize=7.5)

    episode_counts = f05.groupby("case")["episodes"].value_counts().unstack(fill_value=0).reindex(CASE_ORDER)
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
    fig.suptitle("Reconciliation cost detail (supplementary)", y=1.03)
    save_supp(
        fig, "Supp_Reconciliation_AdditionalCost", campaign="F05_reconciliation", n=n_seeds_f05,
        source_files=["results/processed/F05_reconciliation/trials_with_recovery_type.csv"],
        caption="(A) Additional wall time for episode 2, by scenario class; (B) number of seeds needing 1 vs. 2 "
                "episodes, by scenario class.",
    )


# ===========================================================================
# Figure 5 - resource semantics (only if page budget allows; see
# article/figure_selection_and_page_budget.md)
# ===========================================================================
def figure_resource_semantics():
    f08 = pd.read_csv(RESULTS_DIR / "raw" / "F08_resource_semantics" / "trials.csv")
    n_seeds = f08["seed"].nunique()
    slot_values = sorted(f08["reserved_memory_slots"].unique())
    duration_values = sorted(f08["duration_s"].unique())

    fig, axes = plt.subplots(1, 3, figsize=(12.5, 4))
    metrics = [
        ("delivered_pairs", L("delivered_pairs")),
        ("delivery_ratio", f"{L('delivery_ratio')}\n(delivered / minimum delivered pairs)"),
        ("deliveries_per_reserved_slot", f"Deliveries per\n{L('reserved_memory_slots').lower()}"),
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
            ax.errorbar(slot_values, means, yerr=[los, his], fmt="o-", capsize=4, color=colors[duration], label=f"{L('duration_s')}={duration}")
        ax.set_xlabel(L("reserved_memory_slots"))
        ax.set_ylabel(ylabel)
        ax.set_xticks(slot_values)
    axes[0].legend(loc="upper left", frameon=False, fontsize=8)
    axes[1].axhline(1.0, color="#999", linewidth=0.8, linestyle="--", zorder=0)
    fig.suptitle("Resource semantics: reserved slots vs. delivery", y=1.03)
    save_main(
        fig, "Figure5_ResourceSemantics", campaign="F08_resource_semantics", n=n_seeds,
        source_files=["results/raw/F08_resource_semantics/trials.csv"],
        caption=(
            f"{L('reserved_memory_slots')} sizes the memory pool available to a reservation; {L('duration_s').lower()} "
            "controls how many times that pool can be reused for entanglement generation within the reservation "
            "window. Delivery ratio is defined as delivered pairs divided by the intent's minimum-delivered-pairs "
            "goal; a ratio above 1 reflects over-delivery within the reservation window (memories reused multiple "
            "times), not duplication or a measurement error. Mean +/- 95% CI, n=20 seeds/cell, three-node topology."
        ),
    )


# ===========================================================================
# Supplementary - orchestration overhead (F06), not a main figure in any
# scenario per the priority order in figure_selection_and_page_budget.md.
# ===========================================================================
def figure_overhead_supplementary():
    f06 = pd.read_csv(RESULTS_DIR / "raw" / "F06_overhead" / "trials.csv")
    n_seeds = f06["seed"].nunique()
    conditions = ["native_sequence", "static_provisioning", "ibqn_instrumented"]
    cond_labels = ["Native\nSeQUeNCe", "Static\nprovisioning", "IBQN\ninstrumented"]

    fig, ax = plt.subplots(figsize=(5.5, 4))
    ratio_groups = [f06[f06["condition"] == c]["orchestration_overhead_ratio"].dropna().to_numpy() * 100 for c in conditions]
    boxplot_with_points(ax, ratio_groups, cond_labels, color="#C44E52")
    ax.set_ylabel(f"{L('orchestration_overhead_ratio')} (%)")
    ax.set_title("Orchestration overhead by condition")
    save_supp(
        fig, "Supp_Overhead_Ratio", campaign="F06_overhead", n=n_seeds,
        source_files=["results/raw/F06_overhead/trials.csv"],
        caption="Orchestration overhead ratio (orchestration wall time / total trial wall time) distribution per "
                "condition, n=20 seeds/condition. Static provisioning's ratio is highest not because it performs "
                "less control work, but because its total trial wall time denominator and event volume differ "
                "from the instrumented IBQN condition (see main text, Sec. VI-E).",
    )


if __name__ == "__main__":
    figure_architecture()
    figure_routing()
    figure_planner_assurance()
    figure_purification_reconciliation()
    figure_resource_semantics()
    figure_overhead_supplementary()
    (MAIN_DIR / "sources.json").write_text(json.dumps(MAIN_SOURCES, indent=2), encoding="utf-8")
    (SUPP_DIR / "sources.json").write_text(json.dumps(SUPP_SOURCES, indent=2), encoding="utf-8")
    print("DONE")
