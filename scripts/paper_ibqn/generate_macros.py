"""P-IBQN4a: generates paper_ibqn/tables/result_macros.tex - every
quantitative value the manuscript prose cites as a macro, computed
directly from results/paper_ibqn/processed/*.csv (never hand-copied
from a checkpoint or from memory). This file must never be edited by
hand - re-run this script instead. tests/paper_ibqn/test_manuscript_content.py
cross-checks every macro against its source CSV.

Run: python scripts/paper_ibqn/generate_macros.py
Writes: paper_ibqn/tables/result_macros.tex
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "results" / "paper_ibqn" / "processed"
OUT_PATH = PROJECT_ROOT / "paper_ibqn" / "tables" / "result_macros.tex"

LEVEL_TO_MACRO = {"L1": "LOne", "L2": "LTwo", "L2-R": "LTwoR", "L3": "LThree", "L3-R": "LThreeR", "L4": "LFour"}


def pct(x: float, decimals: int = 1) -> str:
    return f"{x * 100:.{decimals}f}\\%"


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    macros: list[tuple[str, str]] = []

    # --- assurance ---
    assurance = pd.read_csv(PROCESSED_DIR / "assurance_results.csv")
    macros.append(("AssuranceMismatchTotal", str(int(assurance["mismatches"].sum()))))
    macros.append(("AssuranceExecutedTotal", str(int(assurance["executed_intents"].sum()))))
    macros.append(("AssuranceEvaluationsTotal", str(int(assurance["assurance_evaluations"].sum()))))
    macros.append(("AssuranceMissingTotal", str(int(assurance["missing_evaluations"].sum()))))

    # --- reconciliation ---
    recon = pd.read_csv(PROCESSED_DIR / "reconciliation_results.csv")
    total_row = recon[recon["action"] == "TOTAL"].iloc[0]
    macros.append(("ReconTotalTriggered", str(int(total_row["triggered"]))))
    macros.append(("ReconTotalEpisodeTwo", str(int(total_row["episode2_executed"]))))
    macros.append(("ReconTotalRecovered", str(int(total_row["recovered"]))))
    macros.append(("ReconTotalFailedRecovery", str(int(total_row["failed_recovery"]))))
    macros.append(("ReconTotalRate", pct(total_row["recovery_rate"])))
    action_macro_name = {"route_change": "ReconRouteChange", "slot_increase": "ReconSlotIncrease", "duration_increase": "ReconDurationIncrease"}
    for action, prefix in action_macro_name.items():
        row = recon[recon["action"] == action].iloc[0]
        macros.append((f"{prefix}Triggered", str(int(row["triggered"]))))
        macros.append((f"{prefix}EpisodeTwo", str(int(row["episode2_executed"]))))
        macros.append((f"{prefix}Recovered", str(int(row["recovered"]))))
        macros.append((f"{prefix}FailedRecovery", str(int(row["failed_recovery"]))))
        macros.append((f"{prefix}Rate", pct(row["recovery_rate"])))

    # --- P17 multi-intent scale ---
    p17_intents = pd.read_csv(PROJECT_ROOT / "results/ibqn_validation_b/P17_concurrent_intents/intents.csv")
    p17_groups = pd.read_csv(PROJECT_ROOT / "results/ibqn_validation_b/P17_concurrent_intents/groups.csv")
    macros.append(("PSeventeenGroupCount", str(int(len(p17_groups)))))
    macros.append(("PSeventeenIntentCount", str(int(len(p17_intents)))))

    multi = pd.read_csv(PROCESSED_DIR / "multi_intent_results.csv")
    for scenario in multi["scenario"].unique():
        grp = multi[multi["scenario"] == scenario]
        name = "".join(w.capitalize() for w in scenario.replace("_", " ").split())
        macros.append((f"MultiIntent{name}Admitted", str(int(grp["admitted"].sum()))))
        macros.append((f"MultiIntent{name}Satisfied", str(int(grp["satisfied"].sum()))))
        macros.append((f"MultiIntent{name}ReservationRejected", str(int(grp["reservation_rejected"].sum()))))
        macros.append((f"MultiIntent{name}Failed", str(int(grp["failed"].sum()))))

    # --- overhead (from P17 raw intent records, matching
    # docs/paper_ibqn_validation/overhead_measurement.md's exact method:
    # the MEDIAN OF THE PER-ROW RATIO, not the sum of each component's
    # own median - those are not interchangeable, and mixing them
    # produced a small, spurious discrepancy (0.096% vs 0.086%) caught
    # while building this script. Re-derived directly here rather than
    # trusting overhead_results.csv's per-component percentages for this
    # specific aggregate claim. ---
    p17_intents_full = pd.read_csv(PROJECT_ROOT / "results/ibqn_validation_b/P17_concurrent_intents/intents.csv")
    lifecycle_cols = ["intent_validation_wall_time_s", "orchestration_wall_time_s", "observation_extraction_wall_time_s", "assurance_wall_time_s"]
    lifecycle_sum = p17_intents_full[lifecycle_cols].sum(axis=1)
    total = (
        p17_intents_full["planning_wall_time_s"] + lifecycle_sum + p17_intents_full["simulation_wall_time_s_shared"]
    )
    macros.append(("OverheadLifecyclePct", f"{(lifecycle_sum / total).median() * 100:.3f}\\%"))
    macros.append(("OverheadPlannerPct", f"{(p17_intents_full['planning_wall_time_s'] / total).median() * 100:.3f}\\%"))
    macros.append(("OverheadSimulationPct", f"{(p17_intents_full['simulation_wall_time_s_shared'] / total).median() * 100:.2f}\\%"))

    f06 = pd.read_csv(PROJECT_ROOT / "results/raw/F06_overhead/trials.csv")
    f06_ratio = f06["orchestration_overhead_ratio"].mean()
    macros.append(("OverheadF06Ratio", f"{f06_ratio * 100:.2f}\\%"))

    # --- false feasibility (corrected denominator) ---
    feas = pd.read_csv(PROCESSED_DIR / "planner_error_results.csv")
    for _, row in feas.iterrows():
        m = LEVEL_TO_MACRO[row["planner"]]
        macros.append((f"FalseFeas{m}Num", str(int(row["numerator"]))))
        macros.append((f"FalseFeas{m}Denom", str(int(row["denominator"]))))
        macros.append((f"FalseFeas{m}Rate", pct(row["rate"])))

    # --- false rejection (oracle by planner, distinct denominator) ---
    rej = pd.read_csv(PROCESSED_DIR / "oracle_by_planner.csv")
    for _, row in rej.iterrows():
        m = LEVEL_TO_MACRO[row["planner"]]
        macros.append((f"FalseRej{m}Rejected", str(int(row["rejected"]))))
        macros.append((f"FalseRej{m}Tested", str(int(row["oracle_tested"]))))
        macros.append((f"FalseRej{m}Satisfiable", str(int(row["oracle_satisfiable"]))))
        macros.append((f"FalseRej{m}Rate", pct(row["false_rejection_rate"])))
        macros.append((f"FalseRej{m}CILow", pct(row["ci_low"])))
        macros.append((f"FalseRej{m}CIHigh", pct(row["ci_high"])))

    # --- F04 (kept under a clearly distinct namespace, never "L1") ---
    boundary = pd.read_csv(PROCESSED_DIR / "oracle_purification_boundary.csv").iloc[0]
    macros.append(("F04BoundaryRejected", str(int(boundary["rejected"]))))
    macros.append(("F04BoundaryTested", str(int(boundary["oracle_tested"]))))
    macros.append(("F04BoundarySatisfiable", str(int(boundary["oracle_satisfiable"]))))
    macros.append(("F04BoundaryRate", pct(boundary["rate"])))

    lines = [
        "% Generated by scripts/paper_ibqn/generate_macros.py - DO NOT EDIT BY HAND.",
        "% Source: results/paper_ibqn/processed/*.csv (and, for the F06 cross-check",
        "% and P17 scale macros, the frozen raw files cited inline above).",
        "% Cross-checked against source CSVs by tests/paper_ibqn/test_manuscript_content.py.",
        "",
    ]
    for name, value in macros:
        lines.append(f"\\newcommand{{\\{name}}}{{{value}}}")
    OUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(macros)} macros)")


if __name__ == "__main__":
    main()
