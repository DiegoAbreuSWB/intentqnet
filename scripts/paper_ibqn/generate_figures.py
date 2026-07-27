"""P-IBQN3: generates every manuscript figure from the processed CSVs in
results/paper_ibqn/processed/ (plus two small, disclosed direct reads of
frozen raw files for the diamond-route and planning-cost figures, cited
in each figure's own docstring/caption). matplotlib only, no seaborn.
Every figure written as both PDF (vector) and PNG (raster). No pie
charts, no 3D, no "phase transition"/"oracle planner" wording, never
color-only distinction (markers/hatches/linestyles used throughout).

Run: python scripts/paper_ibqn/generate_figures.py
Writes: results/paper_ibqn/figures/*.{pdf,png}
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "results" / "paper_ibqn" / "processed"
OUT_DIR = PROJECT_ROOT / "results" / "paper_ibqn" / "figures"

plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
    "legend.fontsize": 9, "xtick.labelsize": 9, "ytick.labelsize": 9,
    "figure.dpi": 150,
})

HATCHES = ["//", "\\\\", "xx", "..", "oo", "++"]


def save(fig, name: str) -> None:
    fig.savefig(OUT_DIR / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT_DIR / f"{name}.png", bbox_inches="tight", dpi=200)
    plt.close(fig)
    print(f"wrote {name}.pdf / .png")


def _box(ax, xy, w, h, text, fc="#e8e8e8", ec="black", fontsize=8):
    box = FancyBboxPatch(xy, w, h, boxstyle="round,pad=0.02", fc=fc, ec=ec, lw=1.0)
    ax.add_patch(box)
    ax.text(xy[0] + w / 2, xy[1] + h / 2, text, ha="center", va="center", fontsize=fontsize, wrap=True)
    return (xy[0], xy[1], w, h)


def _edge_point(box, target_xy):
    """Returns the point on `box`'s (x,y,w,h) border closest to target_xy,
    so arrows terminate at box edges, never at centers (which would draw
    the arrowhead/line through the label text)."""
    bx, by, bw, bh = box
    cx, cy = bx + bw / 2, by + bh / 2
    tx, ty = target_xy
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return (cx, cy)
    scale_x = (bw / 2) / abs(dx) if dx != 0 else float("inf")
    scale_y = (bh / 2) / abs(dy) if dy != 0 else float("inf")
    scale = min(scale_x, scale_y, 1.0) if min(scale_x, scale_y) < 1.0 else min(scale_x, scale_y)
    scale = min(scale_x, scale_y)
    return (cx + dx * scale, cy + dy * scale)


def _connect(ax, box_a, box_b, **kwargs):
    """Draws an arrow from box_a's border to box_b's border, pointed
    along the line between their centers - avoids overlapping either
    box's text."""
    bx, by, bw, bh = box_a
    center_a = (bx + bw / 2, by + bh / 2)
    bx2, by2, bw2, bh2 = box_b
    center_b = (bx2 + bw2 / 2, by2 + bh2 / 2)
    start = _edge_point(box_a, center_b)
    end = _edge_point(box_b, center_a)
    _arrow(ax, start, end, **kwargs)


def _arrow(ax, start, end, style="-|>", color="black", lw=1.2, ls="solid"):
    arrow = FancyArrowPatch(start, end, arrowstyle=style, mutation_scale=12, color=color, lw=lw, linestyle=ls)
    ax.add_patch(arrow)


# ---------------------------------------------------------------------------
# Figure 1: IBQN architecture
# ---------------------------------------------------------------------------
def fig_ibqn_architecture():
    fig, ax = plt.subplots(figsize=(11.5, 5.0))
    ax.set_xlim(0, 13.5)
    ax.set_ylim(0, 6.5)
    ax.axis("off")

    stages = [
        "Intent\nspecification", "Validation", "Planner\ninterface", "Admission",
        "Execution\nadapter", "SeQUeNCe", "Observation", "Assurance", "Reconciliation", "Persistence",
    ]
    x0, y0, w, h, gap = 0.15, 2.9, 1.15, 1.1, 0.2
    boxes = []
    for i, s in enumerate(stages):
        x = x0 + i * (w + gap)
        box = _box(ax, (x, y0), w, h, s, fontsize=7.5)
        boxes.append(box)
        if i > 0:
            _connect(ax, boxes[i - 1], box)

    # common planner interface: 6 planner boxes feeding into "Planner interface" (index 2)
    planners = ["L1", "L2", "L2-R", "L3", "L3-R", "L4"]
    planner_box_target = boxes[2]
    px0 = planner_box_target[0] + planner_box_target[2] / 2 - 1.35
    pboxes = []
    for j, p in enumerate(planners):
        px = px0 + j * 0.47
        pbox = _box(ax, (px, 4.9), 0.4, 0.4, p, fc="#d0e4f5", fontsize=6.5)
        pboxes.append(pbox)
        _connect(ax, pbox, planner_box_target, lw=0.7, color="#555555")
    ax.text(px0 + 1.4, 5.5, "Common planner interface (IntentPlannerPolicy)", fontsize=8, ha="center")

    # offline oracle: outside the runtime lifecycle, dashed connection from Admission
    oracle_box = _box(ax, (0.15, 0.3), 2.1, 1.0, "Offline oracle\n(experimental analysis,\nNOT in the runtime path)", fc="#f7e6c4", fontsize=7.5)
    admission_box = boxes[3]
    _connect(ax, admission_box, oracle_box, color="#8a6d3b", ls="dashed", lw=1.2)
    ax.text((admission_box[0] + oracle_box[0] + oracle_box[2]) / 2, 1.55, "REJECTED intents\n(analyzed offline only,\nnever inside the assurance loop)",
            fontsize=7, ha="center", color="#8a6d3b")

    ax.set_title("IBQN architecture: common planner interface, planner-independent downstream path,\noffline oracle kept outside the runtime assurance loop", fontsize=10)
    save(fig, "fig_ibqn_architecture")


# ---------------------------------------------------------------------------
# Figure 2: lifecycle state machine
# ---------------------------------------------------------------------------
def fig_lifecycle_state_machine():
    fig, ax = plt.subplots(figsize=(9.5, 6.0))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 10.5)
    ax.axis("off")

    pos = {
        "RECEIVED": (1, 9.3), "VALIDATED": (3.3, 9.3), "PLANNING": (5.6, 9.3), "PLANNED": (7.9, 9.3),
        "DEPLOYING": (10, 9.3), "ACTIVE": (10, 6.6), "SATISFIED": (7.9, 4), "VIOLATED": (10, 4),
        "RECONCILING": (7.9, 1.3), "REJECTED": (5.6, 6.6), "FAILED": (10, 1.3), "COMPLETED": (5.6, 4),
        "CANCELLED": (1, 1.3),
    }
    terminal = {"REJECTED", "FAILED", "COMPLETED", "CANCELLED"}
    boxes = {}
    w, h = 1.5, 0.75
    for state, (x, y) in pos.items():
        fc = "#f2d0d0" if state in terminal else "#d0e4f5"
        boxes[state] = _box(ax, (x - w / 2, y - h / 2), w, h, state, fc=fc, fontsize=7)

    edges = [
        ("RECEIVED", "VALIDATED"), ("RECEIVED", "REJECTED"), ("VALIDATED", "PLANNING"),
        ("PLANNING", "PLANNED"), ("PLANNING", "REJECTED"), ("PLANNED", "DEPLOYING"),
        ("DEPLOYING", "ACTIVE"), ("DEPLOYING", "FAILED"), ("ACTIVE", "SATISFIED"),
        ("SATISFIED", "COMPLETED"), ("SATISFIED", "VIOLATED"), ("VIOLATED", "RECONCILING"),
        ("VIOLATED", "FAILED"), ("RECONCILING", "PLANNING"), ("RECONCILING", "FAILED"),
    ]
    for a, b in edges:
        _connect(ax, boxes[a], boxes[b], lw=0.9)

    # highlight ACTIVE -> FAILED (validation-discovered) with a visibly
    # different curved dashed path so it doesn't overlap ACTIVE->VIOLATED
    xa, ya, wa, ha = boxes["ACTIVE"]
    xb, yb, wb, hb = boxes["VIOLATED"]
    _connect(ax, boxes["ACTIVE"], boxes["VIOLATED"], lw=0.9)
    start = (xa + wa, ya + ha * 0.25)
    end = (xb + wb, yb + hb * 0.75)
    arrow = FancyArrowPatch(start, end, connectionstyle="arc3,rad=0.5", arrowstyle="-|>",
                             mutation_scale=12, color="#b02020", lw=1.6, linestyle="dashed")
    ax.add_patch(arrow)
    ax.text(xa + wa + 0.5, (ya + yb) / 2, "ACTIVE$\\to$FAILED:\nadded after\nvalidation-discovered\nSIMULATION_ERROR gap\n(Validation-B1)",
            fontsize=6.5, color="#b02020", ha="left")

    ax.text(1, 0.35, "CANCELLED is reachable from every\nnon-terminal state (edges omitted for clarity)", fontsize=6, ha="center", style="italic")

    red_patch = mpatches.Patch(facecolor="#f2d0d0", edgecolor="black", label="Terminal state")
    blue_patch = mpatches.Patch(facecolor="#d0e4f5", edgecolor="black", label="Non-terminal state")
    ax.legend(handles=[red_patch, blue_patch], loc="lower center", bbox_to_anchor=(0.5, -0.05), ncol=2, frameon=False, fontsize=8)
    ax.set_title("Intent lifecycle state machine (13 real IntentStatus values)", fontsize=10)
    save(fig, "fig_lifecycle_state_machine")


# ---------------------------------------------------------------------------
# Figure 3: planner error taxonomy matrix
# ---------------------------------------------------------------------------
def fig_planner_error_taxonomy():
    fig, ax = plt.subplots(figsize=(6.3, 4.2))
    ax.set_xlim(0, 4.3)
    ax.set_ylim(0, 4)
    ax.axis("off")

    # columns: (0)=planner REJECT, (1)=planner ADMIT
    # rows: (1)=operational truth UNSATISFIABLE (top), (0)=SATISFIABLE (bottom)
    cells = {
        (0, 1): ("Correct rejection", "#d6ead6"), (1, 1): ("False feasibility\n(detected by assurance)", "#f2d0d0"),
        (0, 0): ("False rejection\n(detected by offline oracle only)", "#f2d0d0"), (1, 0): ("Correct feasibility", "#d6ead6"),
    }
    for (cx, cy), (label, color) in cells.items():
        _box(ax, (cx * 1.6 + 0.9, cy * 1.6 + 0.9), 1.5, 1.5, label, fc=color, fontsize=7.5)

    ax.text(1.65, 3.85, "Planner decision: REJECT", ha="center", fontsize=8, fontweight="bold")
    ax.text(3.25, 3.85, "Planner decision: ADMIT", ha="center", fontsize=8, fontweight="bold")
    ax.text(0.3, 2.45, "Operational truth:\nUNSATISFIABLE", ha="center", fontsize=7.5, rotation=90)
    ax.text(0.3, 0.85, "Operational truth:\nSATISFIABLE", ha="center", fontsize=7.5, rotation=90)

    ax.text(2.4, 0.5, "Outside this matrix (not a decision-quality outcome):\n"
                      "stochastic operational failure  |  architectural failure  |  simulator/infrastructure failure",
            ha="center", fontsize=7, style="italic")
    ax.set_title("Planner decision vs. operational truth", fontsize=9)
    save(fig, "fig_planner_error_taxonomy")


# ---------------------------------------------------------------------------
# Figure 4a/4b: planner error results (separate files, different denominators)
# ---------------------------------------------------------------------------
def fig_false_feasibility_by_planner():
    df = pd.read_csv(PROCESSED_DIR / "planner_error_results.csv")
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    x = np.arange(len(df))
    bars = ax.bar(x, df["rate"], color="#a0b8d8", edgecolor="black")
    for i, b in enumerate(bars):
        b.set_hatch(HATCHES[i % len(HATCHES)])
    ax.set_xticks(x)
    ax.set_xticklabels(df["planner"])
    ax.set_ylabel("False-feasibility rate\n(violated / executed)")
    ax.set_ylim(0, 1)
    for i, row in df.iterrows():
        ax.annotate(f"{row['rate']:.2f}\n(n={int(row['denominator'])})", (i, row["rate"] + 0.02), ha="center", fontsize=7)
    ax.set_title("False-feasibility rate by planner (P02b + P03/P13)", fontsize=9)
    save(fig, "fig_false_feasibility_by_planner")


def fig_false_rejection_by_planner():
    df = pd.read_csv(PROCESSED_DIR / "oracle_by_planner.csv")
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    x = np.arange(len(df))
    yerr_low = df["false_rejection_rate"] - df["ci_low"]
    yerr_high = df["ci_high"] - df["false_rejection_rate"]
    bars = ax.bar(x, df["false_rejection_rate"], color="#d8a0a0", edgecolor="black",
                   yerr=[yerr_low, yerr_high], capsize=4)
    for i, b in enumerate(bars):
        b.set_hatch(HATCHES[i % len(HATCHES)])
    ax.set_xticks(x)
    ax.set_xticklabels(df["planner"])
    ax.set_ylabel("False-rejection rate\n(oracle-satisfiable / oracle-tested)")
    ax.set_ylim(0, 0.35)
    for i, row in df.iterrows():
        ax.annotate(f"n={int(row['oracle_tested'])}", (i, row["ci_high"] + 0.01), ha="center", fontsize=7)
    ax.set_title("False-rejection rate by planner (P02b/B2 only - F04 excluded, see text)", fontsize=8.5)
    save(fig, "fig_false_rejection_by_planner")


# ---------------------------------------------------------------------------
# Figure 5: purification boundary mechanism (F04, conceptual)
# ---------------------------------------------------------------------------
def fig_purification_boundary_mechanism():
    fig, ax = plt.subplots(figsize=(7.5, 3.6))
    ax.set_xlim(0.5, 0.85)
    ax.set_ylim(-1.6, 2.3)
    ax.axhline(0, color="black", lw=1)

    swap_only = 0.686375
    ceiling = 0.720252
    requested = 0.73
    ax.plot([swap_only], [0], marker="o", color="black", zorder=3)
    ax.annotate("swap-only fidelity\n(0.6864)", (swap_only, 0), xytext=(swap_only - 0.06, 1.5),
                ha="center", fontsize=7, arrowprops=dict(arrowstyle="-", lw=0.6))
    ax.plot([ceiling], [0], marker="s", color="#2060a0", zorder=3)
    ax.annotate("one-round analytical\nceiling (0.7203)", (ceiling, 0), xytext=(ceiling - 0.04, 0.9),
                ha="center", fontsize=7, color="#2060a0", arrowprops=dict(arrowstyle="-", lw=0.6, color="#2060a0"))
    ax.plot([requested], [0], marker="^", color="#b02020", zorder=3)
    ax.annotate("requested fidelity (0.73)\n-> REJECTED (generic IntentPlanner)", (requested, 0), xytext=(requested + 0.06, 1.7),
                ha="center", fontsize=7, color="#b02020", arrowprops=dict(arrowstyle="-", lw=0.6, color="#b02020"))

    _arrow(ax, (ceiling, -0.7), (requested, -0.7), color="#207020", lw=1.4)
    ax.text((ceiling + requested) / 2, -1.25, "iterative (multi-round) purification execution\nreaches requested fidelity -> oracle: satisfiable",
            fontsize=6.5, color="#207020", ha="center")

    ax.set_yticks([])
    ax.set_xlabel("Average fidelity")
    ax.set_title("F04 mechanism: one-round estimate vs. multi-round execution\n(three_node_1_repeater; NOT the L2-R DELIVERY_TARGET_EXCEEDS_WINDOW mechanism)", fontsize=8.5)
    save(fig, "fig_purification_boundary_mechanism")


# ---------------------------------------------------------------------------
# Figure 6: assurance vs offline oracle
# ---------------------------------------------------------------------------
def fig_assurance_vs_oracle():
    fig, ax = plt.subplots(figsize=(7.0, 3.0))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4)
    ax.axis("off")

    runtime = ["ADMITTED", "EXECUTED", "assurance", "SATISFIED /\nVIOLATED"]
    for i, s in enumerate(runtime):
        _box(ax, (0.3 + i * 2.3, 2.3), 1.9, 0.9, s, fc="#d0e4f5", fontsize=7.5)
        if i > 0:
            _arrow(ax, (0.3 + i * 2.3 - 0.4, 2.75), (0.3 + i * 2.3, 2.75))
    ax.text(0.1, 3.4, "Runtime path:", fontsize=8, fontweight="bold")

    offline = ["REJECTED", "offline oracle\nre-simulation", "correct / false\nrejection classification"]
    for i, s in enumerate(offline):
        _box(ax, (0.3 + i * 3.0, 0.3), 2.5, 0.9, s, fc="#f7e6c4", fontsize=7.5)
        if i > 0:
            _arrow(ax, (0.3 + i * 3.0 - 0.5, 0.75), (0.3 + i * 3.0, 0.75), color="#8a6d3b")
    ax.text(0.1, 1.4, "Offline experimental analysis (never part of the runtime lifecycle):", fontsize=8, fontweight="bold")

    ax.text(5, 1.95, "Assurance does NOT evaluate rejected intents\n(evaluation = None by design)", fontsize=7.5,
            ha="center", style="italic", color="#8a6d3b")
    save(fig, "fig_assurance_vs_oracle")


# ---------------------------------------------------------------------------
# Figure 7a/7b: reconciliation
# ---------------------------------------------------------------------------
def fig_reconciliation_recovery():
    df = pd.read_csv(PROCESSED_DIR / "reconciliation_results.csv")
    fig, ax = plt.subplots(figsize=(5.5, 3.4))
    x = np.arange(len(df))
    w = 0.35
    b1 = ax.bar(x - w / 2, df["triggered"], w, label="Triggered", color="#c0c0c0", edgecolor="black", hatch="..")
    b2 = ax.bar(x + w / 2, df["recovered"], w, label="Recovered", color="#a0d0a0", edgecolor="black", hatch="//")
    ax.set_xticks(x)
    ax.set_xticklabels(df["action"], rotation=15, ha="right")
    ax.set_ylabel("Count")
    for i, row in df.iterrows():
        ax.annotate(f"{row['recovery_rate']*100:.0f}%", (i, max(row["triggered"], row["recovered"]) + 1.5), ha="center", fontsize=8)
    ax.legend(frameon=False)
    ax.set_title("Reconciliation: triggered vs. recovered, by action (F05)", fontsize=9)
    save(fig, "fig_reconciliation_recovery")


def fig_reconciliation_workflow():
    fig, ax = plt.subplots(figsize=(7.0, 2.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 2)
    ax.axis("off")
    steps = ["VIOLATED", "diagnosis /\naction selection", "episode 2\n(replan + re-execute)", "assurance\n(re-evaluate)"]
    for i, s in enumerate(steps):
        _box(ax, (0.2 + i * 2.3, 0.6), 1.9, 0.9, s, fc="#d0e4f5", fontsize=7.5)
        if i > 0:
            _arrow(ax, (0.2 + i * 2.3 - 0.4, 1.05), (0.2 + i * 2.3, 1.05))
    _arrow(ax, (9.1, 1.05), (9.9, 1.4), color="#207020")
    ax.text(9.9, 1.55, "SATISFIED\n(recovered)", fontsize=7, color="#207020")
    _arrow(ax, (9.1, 1.05), (9.9, 0.7))
    ax.text(9.9, 0.55, "still VIOLATED\n(not recovered)", fontsize=7, color="#b02020")
    save(fig, "fig_reconciliation_workflow")


# ---------------------------------------------------------------------------
# Figure 8: multi-intent scenarios
# ---------------------------------------------------------------------------
def fig_multi_intent_scenarios():
    df = pd.read_csv(PROCESSED_DIR / "multi_intent_results.csv")
    agg = df.groupby("scenario")[["admitted", "satisfied", "reservation_rejected", "violated", "failed"]].sum().reset_index()
    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    metrics = ["satisfied", "reservation_rejected", "violated"]
    labels = ["Satisfied", "Reservation-rejected", "Violated"]
    x = np.arange(len(agg))
    w = 0.25
    for j, (m, lab) in enumerate(zip(metrics, labels)):
        bars = ax.bar(x + (j - 1) * w, agg[m], w, label=lab, edgecolor="black", hatch=HATCHES[j])
    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("_", "\n") for s in agg["scenario"]], fontsize=7.5)
    ax.set_ylabel("Intents (both planners combined)")
    ax.legend(frameon=False, fontsize=7.5)
    ax.set_title("Multi-intent outcomes by scenario (P17, 40 intents/scenario)\nAdmission (planner) vs. reservation rejection (NetworkManager) vs. final outcome", fontsize=8)
    save(fig, "fig_multi_intent_scenarios")


# ---------------------------------------------------------------------------
# Figure 9a/9b: overhead decomposition (full and control-plane-only)
# ---------------------------------------------------------------------------
def fig_overhead_full():
    df = pd.read_csv(PROCESSED_DIR / "overhead_results.csv")
    df = df[df["median_s"] != "NA_NOT_MEASURED"].copy()
    df["median_s"] = df["median_s"].astype(float)
    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    x = np.arange(len(df))
    ax.bar(x, df["median_s"], color="#a0b8d8", edgecolor="black")
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(df["component"], rotation=30, ha="right", fontsize=7.5)
    ax.set_ylabel("Median wall time (s, log scale)")
    ax.set_title("Full overhead decomposition (P17, median wall time, log scale)\nSimulation dominates ($\\approx$99.91% of total) - log scale keeps other components visible", fontsize=8)
    save(fig, "fig_overhead_full")


def fig_overhead_control_plane():
    df = pd.read_csv(PROCESSED_DIR / "overhead_results.csv")
    df = df[(df["median_s"] != "NA_NOT_MEASURED") & (df["component"] != "simulation")].copy()
    df["median_s"] = df["median_s"].astype(float)
    fig, ax = plt.subplots(figsize=(5.5, 3.2))
    x = np.arange(len(df))
    bars = ax.bar(x, df["median_s"] * 1000, color="#c0d8c0", edgecolor="black")
    for i, b in enumerate(bars):
        b.set_hatch(HATCHES[i % len(HATCHES)])
    ax.set_xticks(x)
    ax.set_xticklabels(df["component"], rotation=30, ha="right", fontsize=7.5)
    ax.set_ylabel("Median wall time (ms)")
    ax.set_title("Control-plane-only decomposition (simulation excluded, linear scale)", fontsize=9)
    save(fig, "fig_overhead_control_plane")


# ---------------------------------------------------------------------------
# Figure 10: planning capability vs cost
# ---------------------------------------------------------------------------
def fig_planner_capability_cost():
    err = pd.read_csv(PROCESSED_DIR / "planner_error_results.csv").set_index("planner")["rate"]
    p02b = pd.read_csv(PROJECT_ROOT / "results/planner_study/raw/P02b_resource_aware_planners/trials.csv")
    name_by_level = {
        "L1": "conservative_one_round", "L2": "iterative_analytical", "L2-R": "iterative_resource_aware",
        "L3": "probabilistic", "L3-R": "probabilistic_resource_aware",
    }
    medians = {level: p02b[p02b["planner_name"] == name]["planning_time_s"].median() for level, name in name_by_level.items()}
    l4a = pd.read_csv(PROJECT_ROOT / "results/planner_study/raw/P03_l4_cost/trials.csv")
    l4b = pd.read_csv(PROJECT_ROOT / "results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv")
    medians["L4"] = pd.concat([l4a, l4b])["planning_time_s"].median()

    fig, ax = plt.subplots(figsize=(5.5, 4.0))
    markers = ["o", "s", "^", "D", "v", "P"]
    for i, planner in enumerate(["L1", "L2", "L2-R", "L3", "L3-R", "L4"]):
        ax.scatter(medians[planner], err[planner], marker=markers[i], s=70, edgecolor="black",
                    facecolor="none" if planner != "L4" else "#d8a0a0", label=planner)
        ax.annotate(planner, (medians[planner], err[planner]), textcoords="offset points", xytext=(6, 4), fontsize=8)
    ax.set_xscale("log")
    ax.set_xlabel("Median planning time (s, log scale)")
    ax.set_ylabel("False-feasibility rate\n(violated / executed)")
    ax.set_title("Planning cost vs. false-feasibility rate\n(L4's point uses a different, unmatched grid - see text)", fontsize=8.5)
    save(fig, "fig_planner_capability_cost")


# ---------------------------------------------------------------------------
# Figure 11: diamond candidate routes
# ---------------------------------------------------------------------------
def fig_diamond_candidate_routes():
    fig, ax = plt.subplots(figsize=(6.5, 4.6))
    ax.set_xlim(0, 6)
    ax.set_ylim(0, 5.2)
    ax.axis("off")

    nodes = {"r1": (0.5, 2.9), "bad": (3, 4.3), "good1": (2.2, 1.5), "good2": (3.8, 1.5), "r3": (5.5, 2.9)}
    for name, (x, y) in nodes.items():
        ax.add_patch(plt.Circle((x, y), 0.32, fc="#e8e8e8", ec="black"))
        ax.text(x, y, name, ha="center", va="center", fontsize=7.5)

    _arrow(ax, nodes["r1"], nodes["bad"], color="#b02020", lw=1.8)
    _arrow(ax, nodes["bad"], nodes["r3"], color="#b02020", lw=1.8)
    ax.text(3, 4.75, "shortest-hop route (2 hops, lower fidelity)\nused when feasible by L1/L2/L2-R/L3/L3-R\n(ShortestHopCountRouting - fixed, no alternative evaluated)", fontsize=6.5, ha="center", color="#b02020")

    _arrow(ax, nodes["r1"], nodes["good1"], color="#207020", lw=1.8)
    _arrow(ax, nodes["good1"], nodes["good2"], color="#207020", lw=1.8)
    _arrow(ax, nodes["good2"], nodes["r3"], color="#207020", lw=1.8)
    ax.text(3, 0.95, "alternative route (3 hops, higher fidelity)\nALWAYS selected by L4 in the tested boundary trials (candidate evaluation)\nalso used by shortest-hop planners in a subset of trials (120/250) where the 2-hop route was infeasible",
            fontsize=6.5, ha="center", color="#207020")

    ax.set_title("diamond_heterogeneous candidate routes\nData do not support claiming a single fixed route for every planner/trial - see caption", fontsize=8.5)
    save(fig, "fig_diamond_candidate_routes")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig_ibqn_architecture()
    fig_lifecycle_state_machine()
    fig_planner_error_taxonomy()
    fig_false_feasibility_by_planner()
    fig_false_rejection_by_planner()
    fig_purification_boundary_mechanism()
    fig_assurance_vs_oracle()
    fig_reconciliation_recovery()
    fig_reconciliation_workflow()
    fig_multi_intent_scenarios()
    fig_overhead_full()
    fig_overhead_control_plane()
    fig_planner_capability_cost()
    fig_diamond_candidate_routes()
    print("DONE")


if __name__ == "__main__":
    main()
