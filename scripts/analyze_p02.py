"""P02 analysis (planner-family study, M6/checkpoint 2): L1 vs. L2 vs. L3
admission accuracy and calibration. Reads only persisted
`results/planner_study/raw/P02_l1_l2_l3/trials.csv` - never re-runs a
campaign.

Threshold selection protocol (docs/planner_comparison_methodology.md):
seeds 0-9 = validation (choose the admission threshold here), seeds 10-19
= test (report final metrics here, untouched until this point) - the
planner-study brief's explicit "never choose the threshold from the test
set" requirement.

L3 was collected with admission_threshold=0.0 (always deploys when any
route is feasible), so every trial's REAL outcome is known regardless of
what a stricter threshold would have decided - a candidate threshold T's
counterfactual decision is: admit (use the real recorded outcome) if
predicted_satisfaction_probability >= T, else REJECTED. This lets every
candidate threshold be evaluated from ONE campaign run, no re-simulation
needed per threshold.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "results" / "planner_study" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "results" / "planner_study" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

VALIDATION_SEEDS = set(range(10))
TEST_SEEDS = set(range(10, 20))
CANDIDATE_THRESHOLDS = [0.50, 0.75, 0.90, 0.95]


def load() -> pd.DataFrame:
    path = RAW_DIR / "P02_l1_l2_l3" / "trials.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run scripts/run_p02_l1_l2_l3.py first")
    return pd.read_csv(path)


def counterfactual_outcome(row: pd.Series, threshold: float) -> str:
    """What L3's outcome WOULD have been under admission_threshold=`threshold`,
    given the real recorded outcome at threshold=0.0."""
    if row["predicted_satisfaction_probability"] is None or pd.isna(row["predicted_satisfaction_probability"]):
        return row["final_status"]
    if row["predicted_satisfaction_probability"] < threshold:
        return "REJECTED"
    return row["final_status"]


def brier_score(df: pd.DataFrame) -> float:
    """Brier score over L3 rows only: mean (predicted_probability -
    actual_satisfied)^2. Rows with no delivered plan (predicted_probability
    undefined, i.e. no feasible candidate at all) are excluded - there is
    no probability to score."""
    sub = df.dropna(subset=["predicted_satisfaction_probability"])
    actual = (sub["final_status"] == "SATISFIED").astype(float)
    return float(np.mean((sub["predicted_satisfaction_probability"] - actual) ** 2))


def calibration_curve(df: pd.DataFrame, n_bins: int = 5) -> pd.DataFrame:
    sub = df.dropna(subset=["predicted_satisfaction_probability"]).copy()
    sub["bin"] = pd.cut(sub["predicted_satisfaction_probability"], bins=np.linspace(0, 1, n_bins + 1), include_lowest=True)
    actual = (sub["final_status"] == "SATISFIED").astype(float)
    sub["actual_satisfied"] = actual
    grouped = sub.groupby("bin", observed=True).agg(
        n=("actual_satisfied", "size"), mean_predicted=("predicted_satisfaction_probability", "mean"),
        mean_actual=("actual_satisfied", "mean"),
    ).reset_index()
    return grouped


def expected_calibration_error(curve: pd.DataFrame, n_total: int) -> float:
    return float(sum(row["n"] / n_total * abs(row["mean_predicted"] - row["mean_actual"]) for _, row in curve.iterrows()))


def threshold_metrics(l3: pd.DataFrame, threshold: float) -> dict:
    outcomes = l3.apply(lambda row: counterfactual_outcome(row, threshold), axis=1)
    n = len(outcomes)
    admitted = outcomes != "REJECTED"
    satisfied = outcomes == "SATISFIED"
    violated = outcomes == "VIOLATED"
    false_feasibility = float((admitted & violated).sum() / admitted.sum()) if admitted.sum() else 0.0
    # false rejection: rejected here, but at threshold=0 (i.e. always-admit) the real outcome was SATISFIED
    always_admit_satisfied = l3["final_status"] == "SATISFIED"
    rejected_here = ~admitted
    false_rejection = (
        float((rejected_here & always_admit_satisfied).sum() / rejected_here.sum()) if rejected_here.sum() else 0.0
    )
    operational_satisfaction = float(satisfied.sum() / n) if n else 0.0
    return {
        "threshold": threshold, "n": n, "false_feasibility": false_feasibility,
        "false_rejection": false_rejection, "operational_satisfaction": operational_satisfaction,
    }


def main() -> None:
    df = load()
    print(f"loaded {len(df)} trials")

    l3 = df[df["planner_level"] == "L3"].copy()
    validation = l3[l3["seed"].isin(VALIDATION_SEEDS)]
    test = l3[l3["seed"].isin(TEST_SEEDS)]

    print(f"L3 rows: {len(l3)} (validation={len(validation)}, test={len(test)})")

    validation_results = [threshold_metrics(validation, t) for t in CANDIDATE_THRESHOLDS]
    validation_df = pd.DataFrame(validation_results)
    print("\n=== Threshold selection on VALIDATION seeds (0-9) ===")
    print(validation_df.to_string(index=False))

    # select threshold with best (fewest) combined false feasibility + false rejection
    validation_df["combined_error"] = validation_df["false_feasibility"] + validation_df["false_rejection"]
    best_threshold = float(validation_df.loc[validation_df["combined_error"].idxmin(), "threshold"])
    print(f"\nSelected admission_threshold = {best_threshold} (lowest combined error on validation)")

    test_metrics = threshold_metrics(test, best_threshold)
    print("\n=== Final metrics on TEST seeds (10-19), threshold chosen on validation only ===")
    print(json.dumps(test_metrics, indent=2))

    l3_brier = brier_score(l3)
    l3_curve = calibration_curve(l3)
    l3_ece = expected_calibration_error(l3_curve, len(l3.dropna(subset=["predicted_satisfaction_probability"])))
    print(f"\nBrier score (all L3 trials): {l3_brier:.4f}")
    print(f"Expected calibration error (all L3 trials): {l3_ece:.4f}")
    print("\nCalibration curve:")
    print(l3_curve.to_string(index=False))

    # L1/L2/L3 comparison: operational satisfaction, false feasibility (accepted but VIOLATED)
    comparison_rows = []
    for level in ["L1", "L2", "L3"]:
        sub = df[df["planner_level"] == level]
        n = len(sub)
        if n == 0:
            continue
        admitted = sub["final_status"] != "REJECTED"
        violated = sub["final_status"] == "VIOLATED"
        satisfied = sub["final_status"] == "SATISFIED"
        comparison_rows.append({
            "planner_level": level, "n": n,
            "rejection_rate": float((~admitted).sum() / n),
            "false_feasibility": float((admitted & violated).sum() / admitted.sum()) if admitted.sum() else 0.0,
            "operational_satisfaction": float(satisfied.sum() / n),
            "mean_planning_time_s": float(sub["planning_time_s"].mean()),
        })
    comparison_df = pd.DataFrame(comparison_rows)
    print("\n=== L1 vs. L2 vs. L3 (all trials, all combinations) ===")
    print(comparison_df.to_string(index=False))

    comparison_df.to_csv(PROCESSED_DIR / "P02_l1_l2_l3_comparison.csv", index=False)
    validation_df.to_csv(PROCESSED_DIR / "P02_threshold_selection_validation.csv", index=False)
    l3_curve.to_csv(PROCESSED_DIR / "P02_calibration_curve.csv", index=False)
    summary = {
        "selected_admission_threshold": best_threshold,
        "test_metrics_at_selected_threshold": test_metrics,
        "brier_score_all_l3": l3_brier,
        "expected_calibration_error_all_l3": l3_ece,
        "n_trials_total": len(df),
        "n_l3_trials": len(l3),
    }
    (PROCESSED_DIR / "P02_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote processed outputs to {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
