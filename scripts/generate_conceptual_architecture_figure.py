"""Fase K4: the ONE conceptual architecture figure - deliberately
separate from the experimental figures (results/figures/final/), saved
to results/figures/conceptual/. Shows the IBN operational cycle this
project implements (docs/ibn_principles_mapping.md), not any
experimental result.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "results" / "figures" / "conceptual"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STAGES = [
    ("Intent\n(WHAT)", "min_fidelity, reserved_memory_slots,\nmin_delivered_pairs, duration_s", "#4C72B0"),
    ("Translation", "IntentPlanner.plan()", "#55A868"),
    ("ExecutionPlan\n(HOW)", "route, fidelity_estimator,\npurification_strategy", "#55A868"),
    ("Deployment", "SequenceExecutor.deploy()\n(real SeQUeNCe reservation)", "#DD8452"),
    ("Quantum\noperations", "SeQUeNCe Timeline.run()\n(entanglement generation, swap,\npurification)", "#DD8452"),
    ("Per-intent\nobservation", "collect_intent_evidence()\n(DELIVERY events by intent_id)", "#8172B2"),
    ("Assurance", "evaluate_intent()\nSATISFIED / VIOLATED / REJECTED", "#C44E52"),
    ("Reconciliation", "decide_reconciliation_action()\n+ a new episode, when triggered", "#C44E52"),
]


def main() -> None:
    fig, ax = plt.subplots(figsize=(8, 13))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, len(STAGES) * 2 + 1)
    ax.axis("off")

    box_w, box_h = 8.5, 1.7
    x0 = 1.0
    for i, (title, detail, color) in enumerate(STAGES):
        y = (len(STAGES) - 1 - i) * 2 + 0.5
        box = FancyBboxPatch(
            (x0, y), box_w, box_h, boxstyle="round,pad=0.08,rounding_size=0.15",
            linewidth=1.5, edgecolor=color, facecolor=color, alpha=0.18,
        )
        ax.add_patch(box)
        title_y = y + box_h - 0.45 if "\n" in title else y + box_h - 0.35
        ax.text(x0 + box_w / 2, title_y, title, ha="center", va="center", fontsize=13, fontweight="bold", color=color)
        ax.text(x0 + box_w / 2, y + box_h * 0.28, detail, ha="center", va="center", fontsize=8.5, color="#333")

        if i < len(STAGES) - 1:
            arrow = FancyArrowPatch(
                (x0 + box_w / 2, y), (x0 + box_w / 2, y - 0.5),
                arrowstyle="-|>", mutation_scale=18, linewidth=1.5, color="#555",
            )
            ax.add_patch(arrow)

    # feedback loop: reconciliation -> back up to deployment (new episode)
    top_y = (len(STAGES) - 1 - 3) * 2 + 0.5 + box_h / 2  # Deployment box mid-height
    bottom_y = (len(STAGES) - 1 - 7) * 2 + 0.5 + box_h / 2  # Reconciliation box mid-height
    loop_arrow = FancyArrowPatch(
        (x0 + box_w, bottom_y), (x0 + box_w, top_y),
        connectionstyle="arc3,rad=0.6", arrowstyle="-|>", mutation_scale=18,
        linewidth=1.5, color="#C44E52", linestyle="--",
    )
    ax.add_patch(loop_arrow)
    ax.text(x0 + box_w + 2.6, (top_y + bottom_y) / 2, "new episode\n(if reconciliation\ndecides an action)", ha="left", va="center", fontsize=8.5, color="#C44E52", style="italic")

    ax.set_title("IBQN operational cycle\n(see docs/ibn_principles_mapping.md)", fontsize=13, pad=10)
    fig.savefig(OUT_DIR / "Figure_Architecture_Conceptual.pdf", bbox_inches="tight")
    fig.savefig(OUT_DIR / "Figure_Architecture_Conceptual.png", bbox_inches="tight")
    plt.close(fig)
    print(f"saved {OUT_DIR / 'Figure_Architecture_Conceptual.pdf'}")
    print(f"saved {OUT_DIR / 'Figure_Architecture_Conceptual.png'}")


if __name__ == "__main__":
    main()
