"""IBQN Validation-A: mechanically derives every number the architectural-
validation documents (docs/paper_ibqn_validation/) cite, directly from
existing, frozen campaign data - no new simulations are run here.

Sources used (all pre-existing, unmodified by this script):
  - results/planner_study/raw/P02b_resource_aware_planners/trials.csv
      (L1, L2, L2-R, L3, L3-R - the planner-family study, one common
      schema, one intent template, 240 trials/planner)
  - results/planner_study/raw/P03_l4_cost/trials.csv and
    results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv
      (L4 - combined, since P03 alone has no REJECTED/VIOLATED outcomes)
  - results/processed/F04_planner_vs_operation/{matrix.csv,gap_metrics.json}
      (offline-oracle false-rejection/false-feasibility analysis - NOTE:
      this campaign classifies trials by `routing_strategy`/
      `purification_policy`, not by the L1-L6 planner_name/planner_level
      used elsewhere; it is a distinct, earlier feasibility-check
      pipeline that shares the same single-round purification estimator
      documented in docs/false_rejection_root_cause.md. Never conflate
      its counts with a specific L1-L6 planner's counts.)
  - results/raw/F05_reconciliation/trials.csv (two-episode reconciliation
      outcomes: initial_status, action, recovered)
  - results/raw/F06_overhead/trials.csv (stage-level wall-time
      decomposition: parsing/validation/capability/planning/deployment/
      assurance/reconciliation_decision/simulation)

Run: python scripts/audit_ibqn_architectural_claims.py
Writes: results/ibqn_validation/audit_report.json and .txt
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]

P02B_PATH = PROJECT_ROOT / "results/planner_study/raw/P02b_resource_aware_planners/trials.csv"
P03_PATH = PROJECT_ROOT / "results/planner_study/raw/P03_l4_cost/trials.csv"
P13_PATH = PROJECT_ROOT / "results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv"
F04_MATRIX_PATH = PROJECT_ROOT / "results/processed/F04_planner_vs_operation/matrix.csv"
F04_METRICS_PATH = PROJECT_ROOT / "results/processed/F04_planner_vs_operation/gap_metrics.json"
F05_PATH = PROJECT_ROOT / "results/raw/F05_reconciliation/trials.csv"
F06_PATH = PROJECT_ROOT / "results/raw/F06_overhead/trials.csv"

OUT_DIR = PROJECT_ROOT / "results" / "ibqn_validation"

PLANNER_FAMILY_ORDER = [
    "conservative_one_round",  # L1
    "iterative_analytical",  # L2
    "iterative_resource_aware",  # L2-R
    "probabilistic",  # L3
    "probabilistic_resource_aware",  # L3-R
]
PLANNER_LEVEL_LABEL = {
    "conservative_one_round": "L1",
    "iterative_analytical": "L2",
    "iterative_resource_aware": "L2-R",
    "probabilistic": "L3",
    "probabilistic_resource_aware": "L3-R",
    "simulation_in_the_loop": "L4",
}


def planner_family_lifecycle_counts() -> list[dict]:
    df = pd.read_csv(P02B_PATH)
    rows = []
    for planner_name in PLANNER_FAMILY_ORDER:
        grp = df[df["planner_name"] == planner_name]
        n = len(grp)
        rejected = int((grp["final_status"] == "REJECTED").sum())
        admitted = n - rejected
        satisfied = int((grp["final_status"] == "SATISFIED").sum())
        violated = int((grp["final_status"] == "VIOLATED").sum())
        sim_error = int((grp["final_status"] == "SIMULATION_ERROR").sum())
        timeout = int((grp["final_status"] == "TIMEOUT").sum())
        rows.append({
            "planner_level": PLANNER_LEVEL_LABEL[planner_name],
            "planner_name": planner_name,
            "campaign": "P02b_resource_aware_planners",
            "submitted": n,
            "admitted": admitted,
            "rejected": rejected,
            "satisfied": satisfied,
            "violated": violated,
            "simulation_error": sim_error,
            "timeout": timeout,
            "false_feasibility_rate_among_admitted": round(violated / admitted, 4) if admitted else None,
        })

    l4_frames = []
    for path, campaign in [(P03_PATH, "P03_l4_cost"), (P13_PATH, "P13_l4_boundary_reference")]:
        d = pd.read_csv(path)
        d = d.assign(_campaign=campaign)
        l4_frames.append(d)
    l4 = pd.concat(l4_frames, ignore_index=True)
    n = len(l4)
    rejected = int((l4["final_status"] == "REJECTED").sum())
    admitted = n - rejected
    satisfied = int((l4["final_status"] == "SATISFIED").sum())
    violated = int((l4["final_status"] == "VIOLATED").sum())
    sim_error = int((l4["final_status"] == "SIMULATION_ERROR").sum())
    timeout = int((l4["final_status"] == "TIMEOUT").sum())
    rows.append({
        "planner_level": "L4",
        "planner_name": "simulation_in_the_loop",
        "campaign": "P03_l4_cost + P13_l4_boundary_reference (combined - neither alone spans admit/reject/satisfy/violate)",
        "submitted": n,
        "admitted": admitted,
        "rejected": rejected,
        "satisfied": satisfied,
        "violated": violated,
        "simulation_error": sim_error,
        "timeout": timeout,
        "false_feasibility_rate_among_admitted": round(violated / admitted, 4) if admitted else None,
    })
    return rows


def assurance_correctness_check() -> dict:
    """Mechanically verifies that the persisted `satisfied` boolean agrees
    with `final_status`, and that REJECTED (never-executed) trials carry
    no assurance evaluation - i.e., assurance is scoped to EXECUTED
    intents only, exactly as the code (evaluator.py) requires."""
    df = pd.read_csv(P02B_PATH)
    satisfied_mismatch = int(((df["final_status"] == "SATISFIED") & (df["satisfied"] != True)).sum())  # noqa: E712
    true_mismatch = int(((df["satisfied"] == True) & (df["final_status"] != "SATISFIED")).sum())  # noqa: E712
    rejected = df[df["final_status"] == "REJECTED"]
    rejected_with_evaluation = int(rejected["satisfied"].notna().sum())
    return {
        "campaign": "P02b_resource_aware_planners",
        "n_trials": len(df),
        "satisfied_flag_disagrees_with_final_status_SATISFIED": satisfied_mismatch,
        "satisfied_flag_true_but_final_status_not_SATISFIED": true_mismatch,
        "n_rejected_trials": len(rejected),
        "rejected_trials_with_an_assurance_evaluation": rejected_with_evaluation,
        "correct": satisfied_mismatch == 0 and true_mismatch == 0 and rejected_with_evaluation == 0,
    }


def false_rejection_false_feasibility_oracle() -> dict:
    matrix = pd.read_csv(F04_MATRIX_PATH)
    metrics = json.loads(F04_METRICS_PATH.read_text(encoding="utf-8"))
    return {
        "source": "F02_routing + F03_purification, three_node_1_repeater only, "
                  "classified by routing_strategy/purification_policy (NOT the L1-L6 planner_name axis)",
        "matrix": matrix.to_dict(orient="records"),
        "gap_metrics": metrics,
    }


def reconciliation_counts() -> dict:
    df = pd.read_csv(F05_PATH)
    by_action = (
        df[df["action"].notna()]
        .groupby("action")["recovered"]
        .value_counts()
        .unstack(fill_value=0)
        .to_dict(orient="index")
    )
    return {
        "campaign": "F05_reconciliation",
        "n_trials": len(df),
        "initial_status_counts": df["initial_status"].value_counts().to_dict(),
        "n_violated_entering_reconciliation": int((df["initial_status"] == "VIOLATED").sum()),
        "recovered_by_action": by_action,
        "n_recovered_true": int((df["recovered"] == True).sum()),  # noqa: E712
        "n_recovered_false": int((df["recovered"] == False).sum()),  # noqa: E712
    }


def overhead_breakdown() -> dict:
    df = pd.read_csv(F06_PATH)
    stage_cols = [
        "intent_parsing_wall_time_s", "intent_validation_wall_time_s",
        "capability_extraction_wall_time_s", "planning_wall_time_s",
        "deployment_wall_time_s", "assurance_wall_time_s",
        "reconciliation_decision_wall_time_s", "simulation_wall_time_s",
        "total_orchestration_wall_time_s", "total_trial_wall_time_s",
    ]
    means = df[stage_cols].mean().round(6).to_dict()
    return {
        "campaign": "F06_overhead",
        "n_trials": len(df),
        "mean_stage_wall_time_s": means,
        "mean_orchestration_overhead_ratio": round(df["orchestration_overhead_ratio"].mean(), 6),
        "mean_planning_overhead_ratio": round(df["planning_overhead_ratio"].mean(), 6),
        "note": "route_application_wall_time_s and persistence_wall_time_s are not isolated "
                "in this instrumentation (see src/ibqn/experiments/overhead.py) - not a computed 0, "
                "a genuine measurement gap.",
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "planner_family_lifecycle_counts": planner_family_lifecycle_counts(),
        "assurance_correctness_check": assurance_correctness_check(),
        "false_rejection_false_feasibility_oracle": false_rejection_false_feasibility_oracle(),
        "reconciliation_counts": reconciliation_counts(),
        "overhead_breakdown": overhead_breakdown(),
    }

    (OUT_DIR / "audit_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines = ["IBQN ARCHITECTURAL VALIDATION - DERIVED METRICS", "=" * 60, ""]
    lines.append("Planner-family lifecycle counts (P02b + P03/P13 for L4):")
    for row in report["planner_family_lifecycle_counts"]:
        lines.append(
            f"  {row['planner_level']:5s} submitted={row['submitted']:4d} admitted={row['admitted']:4d} "
            f"rejected={row['rejected']:4d} satisfied={row['satisfied']:4d} violated={row['violated']:4d} "
            f"sim_error={row['simulation_error']:3d} timeout={row['timeout']:2d} "
            f"false_feasibility_rate={row['false_feasibility_rate_among_admitted']}"
        )
    lines.append("")
    ac = report["assurance_correctness_check"]
    lines.append(f"Assurance correctness check: {'PASS' if ac['correct'] else 'FAIL'} "
                 f"(0 mismatches expected; got satisfied-vs-status={ac['satisfied_flag_disagrees_with_final_status_SATISFIED']}, "
                 f"true-vs-status={ac['satisfied_flag_true_but_final_status_not_SATISFIED']}, "
                 f"rejected-with-evaluation={ac['rejected_trials_with_an_assurance_evaluation']})")
    lines.append("")
    ff = report["false_rejection_false_feasibility_oracle"]["gap_metrics"]
    lines.append(f"F04 offline-oracle: false_rejection_rate={ff['false_rejection_rate']}, "
                 f"false_feasibility_rate={ff['false_feasibility_rate']}, n_total={ff['n_total']}")
    lines.append("")
    rc = report["reconciliation_counts"]
    lines.append(f"F05 reconciliation: {rc['n_violated_entering_reconciliation']} VIOLATED trials entered "
                 f"reconciliation; recovered=True: {rc['n_recovered_true']}, recovered=False: {rc['n_recovered_false']}")
    lines.append(f"  by action: {rc['recovered_by_action']}")
    lines.append("")
    ov = report["overhead_breakdown"]
    lines.append(f"F06 overhead: mean orchestration_overhead_ratio={ov['mean_orchestration_overhead_ratio']}, "
                 f"mean planning_overhead_ratio={ov['mean_planning_overhead_ratio']}")
    lines.append("")
    lines.append("FINAL: DERIVED (informational - this script has no PASS/FAIL gate; it computes")
    lines.append("numbers for the architectural_validation_matrix.md tables to cite, and the")
    lines.append("assurance-correctness check above is the one internal consistency check it runs).")

    (OUT_DIR / "audit_report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
