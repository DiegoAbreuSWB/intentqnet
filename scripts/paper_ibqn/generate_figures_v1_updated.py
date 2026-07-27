"""IBQN-V1R: generates the two NEW figures needed for the V1-based
revision (paper_ibqn_v1_updated/) that don't already exist from
P-IBQN3: an architecture diagram whose planning stage is explicitly
shown as a replaceable component (not a fixed L1-L4 planner family),
and a planner/feasibility-model evolution diagram (one-round ->
iterative -> resource-aware -> probabilistic -> candidate-aware).
matplotlib only, same style conventions as generate_figures.py (no
seaborn, no pie charts, no 3D, hatches/markers not color-only).

Run: python scripts/paper_ibqn/generate_figures_v1_updated.py
Writes: results/paper_ibqn/figures/fig1_architecture_extensible.{pdf,png}
        results/paper_ibqn/figures/fig2_planner_evolution.{pdf,png}
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "results" / "paper_ibqn" / "figures"

plt.rcParams.update({
    "font.size": 10, "axes.titlesize": 11, "figure.dpi": 150,
})


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
    bx, by, bw, bh = box
    cx, cy = bx + bw / 2, by + bh / 2
    tx, ty = target_xy
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return (cx, cy)
    scale_x = (bw / 2) / abs(dx) if dx != 0 else float("inf")
    scale_y = (bh / 2) / abs(dy) if dy != 0 else float("inf")
    scale = min(scale_x, scale_y)
    return (cx + dx * scale, cy + dy * scale)


def _connect(ax, box_a, box_b, **kwargs):
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


def fig1_architecture_extensible():
    fig, ax = plt.subplots(figsize=(7.4, 9.6))
    ax.set_xlim(0, 9.6)
    ax.set_ylim(0, 15.8)
    ax.axis("off")

    stages = [
        ("Application", "#f0f0f0"),
        ("Declarative Quantum Intent (WHAT)\nmin. fidelity, reserved memory slots,\nmin. delivered pairs, duration", "#d8e8f5"),
        ("Validation\ntyped schema", "#d8e8f5"),
        ("Replaceable Planner / Feasibility Model\n(HOW - see extensibility examples, right)", "#f7e6c4"),
        ("Execution Plan\nroute, fidelity estimator,\npurification strategy", "#d8e8f5"),
        ("Deployment via the SeQUeNCe Adapter\n(real SeQUeNCe reservation)", "#d8e8f5"),
        ("Entanglement Generation, Purification,\nSwapping (SeQUeNCe Timeline.run())", "#d8e8f5"),
        ("Per-intent Observation\n(DELIVERY events by intent\\_id)", "#d8e8f5"),
        ("Intent Assurance\nSATISFIED / VIOLATED / REJECTED", "#d6ead6"),
        ("Episode-based Reconciliation\nnew episode (new Timeline),\nno active-reservation rerouting", "#f2d0d0"),
    ]
    w, h, gap = 6.0, 1.05, 0.32
    y0 = 15.3
    boxes = []
    for i, (text, fc) in enumerate(stages):
        y = y0 - i * (h + gap)
        box = _box(ax, (0.4, y - h), w, h, text, fc=fc, fontsize=7.5)
        boxes.append(box)
        if i > 0:
            _connect(ax, boxes[i - 1], box)

    # extensibility examples to the RIGHT of the planner box (side branch,
    # no overlap with the main downstream chain)
    planner_box = boxes[3]
    px, py, pw, ph = planner_box
    examples = ["routing strategy", "purification model", "resource-aware estimate",
                "threshold policy", "candidate evaluation", "future AI-based policy"]
    ex_x = px + pw + 0.5
    ex_w, ex_h = 2.6, 0.55
    ex_boxes = []
    for j, ex in enumerate(examples):
        ex_y = py + ph - 0.2 - j * (ex_h + 0.12)
        fc = "#e8e8e8" if j < 5 else "#f0d8e8"
        eb = _box(ax, (ex_x, ex_y - ex_h), ex_w, ex_h, ex, fc=fc, fontsize=6.5)
        ex_boxes.append(eb)
        _arrow(ax, (ex_x, ex_y - ex_h / 2), (px + pw, py + ph / 2), lw=0.6, color="#555555")
    ax.text(ex_x + ex_w / 2, py + ph - 0.2 - len(examples) * (ex_h + 0.12) - 0.15,
            "The planner is intentionally replaceable:\nthe rest of the lifecycle (execution,\nobservation, assurance, reconciliation,\npersistence) is unchanged.",
            fontsize=6.3, ha="center", va="top", style="italic")

    # offline oracle, to the right of Deployment/Execution area - clearly
    # separate from the main chain, dashed connection from the planner box
    oracle_y = ex_y - ex_h - 1.6
    oracle_box = _box(ax, (ex_x, oracle_y - 0.9), 2.8, 0.9,
                       "Offline oracle\n(experimental analysis for rejected\nintents - NOT in the runtime path)",
                       fc="#f7e6c4", fontsize=6.3)
    _connect(ax, planner_box, oracle_box, color="#8a6d3b", ls="dashed", lw=1.0)

    ax.set_title("IBQN architecture and intent lifecycle:\nthe planning stage is a replaceable component", fontsize=9.5)
    save(fig, "fig1_architecture_extensible")


def fig2_planner_evolution():
    fig, ax = plt.subplots(figsize=(7.4, 4.4))
    ax.set_xlim(0, 13.2)
    ax.set_ylim(0, 6.0)
    ax.axis("off")

    stages = [
        ("One-round\n(original)", "One analytical\npurification round", "False rejections\nnear the one-round\nceiling"),
        ("Iterative", "Multi-round\npurification estimate", "Removes the\none-round-ceiling\nmechanism"),
        ("Resource-aware", "Memory occupancy,\ngeneration capacity,\ndelivery window", "0% false feasibility\n(evaluated grid);\nconservative\ndelivery-window\nrejection"),
        ("Probabilistic", "Predicted\nsatisfaction\nprobability", "No consistent\ndecision improvement\nobserved"),
        ("Candidate-aware", "Bounded simulation\nof multiple\ncandidate routes", "Better route choice\n(diamond), higher\nplanning cost"),
    ]
    w, h, gap = 2.25, 1.3, 0.25
    x0 = 0.3
    boxes = []
    for i, (name, change, effect) in enumerate(stages):
        x = x0 + i * (w + gap)
        box = _box(ax, (x, 4.0), w, h, name, fc="#d8e8f5", fontsize=8.5)
        boxes.append(box)
        if i > 0:
            _connect(ax, boxes[i - 1], box)
        ax.text(x + w / 2, 3.65, change, ha="center", va="top", fontsize=6.5)
        ax.text(x + w / 2, 2.05, effect, ha="center", va="top", fontsize=6.5, color="#555555")
        ax.plot([x + w / 2, x + w / 2], [3.95, 3.75], color="#999999", lw=0.6)

    ax.text(0.3, 5.75, "Feasibility-model evolution", fontsize=10, fontweight="bold")
    ax.text(0.3, 5.35, "(each stage diagnosed a limitation of the previous one - implementation labels: L1, L2, L2-R, L3/L3-R, L4)", fontsize=7)
    save(fig, "fig2_planner_evolution")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig1_architecture_extensible()
    fig2_planner_evolution()
    print("DONE")


if __name__ == "__main__":
    main()
