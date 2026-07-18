"""P02B analysis (planner-family study, M6e/checkpoint 2B): L1 vs. L2 vs.
L2-R vs. L3-original vs. L3-R. Reads only
results/planner_study/raw/P02b_resource_aware_planners/trials.csv - never
re-runs a campaign.

Threshold selection protocol, reused from P02 (docs/planner_comparison_
methodology.md): seeds 0-9 = validation, seeds 10-19 = test - a candidate
admission threshold is never chosen from the test set. L3/L3-R were
collected with admission_threshold=0.0, so every candidate threshold's
counterfactual decision is derivable from the one recorded probability.

Oracle proxy (explicitly NOT a true offline oracle - see docs/planner_
threats_to_validity.md): for a given (scenario, parameter_hash, seed) key,
the intent is treated as "empirically satisfiable" if ANY of the 5 paired
planner runs on that exact key reached final_status=="SATISFIED". This
lets false-rejection / rejected-but-satisfiable metrics be computed
without a dedicated always-accept oracle planner, at the cost of being a
lower bound (a route no planner in this family tried might still have
worked) - disclosed, not hidden.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "results" / "planner_study" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "results" / "planner_study" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

VALIDATION_SEEDS = set(range(5))
TEST_SEEDS = set(range(5, 10))
CANDIDATE_THRESHOLDS = [0.50, 0.75, 0.90, 0.95]
PLANNER_LEVELS = ["L1", "L2", "L2-R", "L3", "L3-R"]
PROBABILISTIC_LEVELS = ["L3", "L3-R"]
CALIBRATION_BIN_EDGES = [0.0, 0.1, 0.3, 0.7, 0.9, 1.0]
CALIBRATION_BIN_LABELS = ["p<0.1", "0.1<=p<0.3", "0.3<=p<0.7", "0.7<=p<0.9", "p>=0.9"]


def _wilson_ci(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Same formula as `planning.planners.l4_simulation._wilson_ci` -
    reused, not re-derived."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def load() -> pd.DataFrame:
    path = RAW_DIR / "P02b_resource_aware_planners" / "trials.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run scripts/run_p02b_resource_aware_planners.py first")
    df = pd.read_csv(path)
    df["key"] = list(zip(df["scenario"], df["parameter_hash"], df["seed"]))
    return df


def add_oracle_column(df: pd.DataFrame) -> pd.DataFrame:
    satisfiable_keys = set(df.loc[df["final_status"] == "SATISFIED", "key"])
    df = df.copy()
    df["oracle_satisfiable"] = df["key"].isin(satisfiable_keys)
    return df


def decision_quality_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for level in PLANNER_LEVELS:
        sub = df[df["planner_level"] == level]
        n = len(sub)
        if n == 0:
            continue
        admitted = sub["feasible"].astype(bool)
        violated = sub["final_status"] == "VIOLATED"
        satisfied = sub["final_status"] == "SATISFIED"
        simulation_error = sub["final_status"] == "SIMULATION_ERROR"
        rejected = ~admitted
        oracle_pos = sub["oracle_satisfiable"].astype(bool)

        tp = int((admitted & oracle_pos).sum())
        fn = int((rejected & oracle_pos).sum())
        fp = int((admitted & ~oracle_pos).sum())
        tn = int((rejected & ~oracle_pos).sum())
        tpr = tp / (tp + fn) if (tp + fn) else float("nan")
        tnr = tn / (tn + fp) if (tn + fp) else float("nan")
        balanced_accuracy = (
            float(np.nanmean([tpr, tnr])) if not (np.isnan(tpr) and np.isnan(tnr)) else float("nan")
        )

        rows.append({
            "planner_level": level, "n": n,
            "rejection_rate": float(rejected.sum() / n),
            "false_feasibility_rate": float((admitted & violated).sum() / admitted.sum()) if admitted.sum() else 0.0,
            "operational_satisfaction_rate": float(satisfied.sum() / n),
            "rejected_but_oracle_satisfiable_rate": float(fn / rejected.sum()) if rejected.sum() else 0.0,
            "rejected_and_oracle_unsatisfiable_rate": float(tn / rejected.sum()) if rejected.sum() else 0.0,
            "balanced_accuracy_vs_oracle_proxy": balanced_accuracy,
            "simulation_error_rate": float(simulation_error.sum() / n),
            "tp": tp, "fn": fn, "fp": fp, "tn": tn,
        })
    return pd.DataFrame(rows)


def mcnemar_test(b: int, c: int) -> dict:
    """Exact two-sided McNemar test via the binomial distribution
    (`scipy.stats.binomtest`) - appropriate for the discordant-pair counts
    this campaign's sample sizes produce, rather than the chi-square
    approximation (which needs larger b+c to be reliable)."""
    n = b + c
    if n == 0:
        return {"b": 0, "c": 0, "n_discordant": 0, "p_value": 1.0}
    p_value = float(stats.binomtest(min(b, c), n, 0.5).pvalue)
    return {"b": b, "c": c, "n_discordant": n, "p_value": p_value}


def mcnemar_pairwise(df: pd.DataFrame) -> pd.DataFrame:
    pivot = df.pivot_table(index="key", columns="planner_level", values="satisfied", aggfunc="first")
    pivot = pivot.reindex(columns=PLANNER_LEVELS)
    rows = []
    for i, level_a in enumerate(PLANNER_LEVELS):
        for level_b in PLANNER_LEVELS[i + 1:]:
            paired = pivot[[level_a, level_b]].dropna()
            if paired.empty:
                continue
            a_sat = paired[level_a].astype(bool)
            b_sat = paired[level_b].astype(bool)
            b_count = int((a_sat & ~b_sat).sum())  # A satisfied, B did not
            c_count = int((~a_sat & b_sat).sum())  # B satisfied, A did not
            result = mcnemar_test(b_count, c_count)
            result.update({"planner_a": level_a, "planner_b": level_b, "n_paired": len(paired)})
            rows.append(result)
    return pd.DataFrame(rows)


def delivery_prediction_table(df: pd.DataFrame) -> pd.DataFrame:
    sub = df.dropna(subset=["predicted_delivered_pairs", "delivered_pairs"])
    rows = []
    for level in PLANNER_LEVELS:
        s = sub[sub["planner_level"] == level]
        if s.empty:
            continue
        error = s["predicted_delivered_pairs"] - s["delivered_pairs"]
        ratio = s["predicted_delivered_pairs"] / s["delivered_pairs"].replace(0, np.nan)
        rows.append({
            "planner_level": level, "n": len(s),
            "mae": float(error.abs().mean()), "rmse": float(np.sqrt((error ** 2).mean())),
            "mean_signed_error": float(error.mean()),
            "mean_predicted_over_observed_ratio": float(ratio.mean(skipna=True)),
            "underprediction_rate": float((error < 0).mean()), "overprediction_rate": float((error > 0).mean()),
        })
    return pd.DataFrame(rows)


def fidelity_prediction_table(df: pd.DataFrame) -> pd.DataFrame:
    sub = df.dropna(subset=["predicted_average_fidelity", "observed_fidelity"])
    rows = []
    for level in PLANNER_LEVELS:
        s = sub[sub["planner_level"] == level]
        if s.empty:
            continue
        error = s["predicted_average_fidelity"] - s["observed_fidelity"]
        predicted_crosses = s["predicted_average_fidelity"] >= s["requested_fidelity"]
        observed_crosses = s["observed_fidelity"] >= s["requested_fidelity"]
        rows.append({
            "planner_level": level, "n": len(s),
            "mae": float(error.abs().mean()), "mean_signed_error": float(error.mean()),
            "threshold_crossing_accuracy": float((predicted_crosses == observed_crosses).mean()),
        })
    return pd.DataFrame(rows)


def brier_score(sub: pd.DataFrame) -> float:
    actual = (sub["final_status"] == "SATISFIED").astype(float)
    return float(np.mean((sub["predicted_satisfaction_probability"] - actual) ** 2))


def log_loss(sub: pd.DataFrame) -> float:
    p = sub["predicted_satisfaction_probability"].clip(1e-6, 1 - 1e-6)
    actual = (sub["final_status"] == "SATISFIED").astype(float)
    return float(-np.mean(actual * np.log(p) + (1 - actual) * np.log(1 - p)))


def calibration_by_region(sub: pd.DataFrame) -> pd.DataFrame:
    sub = sub.dropna(subset=["predicted_satisfaction_probability"]).copy()
    sub["bin"] = pd.cut(
        sub["predicted_satisfaction_probability"], bins=CALIBRATION_BIN_EDGES,
        labels=CALIBRATION_BIN_LABELS, include_lowest=True,
    )
    actual = (sub["final_status"] == "SATISFIED").astype(float)
    sub["actual_satisfied"] = actual
    rows = []
    for label in CALIBRATION_BIN_LABELS:
        region = sub[sub["bin"] == label]
        n = len(region)
        if n == 0:
            rows.append({
                "bin": label, "n": 0, "mean_predicted": None, "empirical_satisfaction_rate": None,
                "ci_low": None, "ci_high": None, "empty_region": True,
            })
            continue
        successes = int(region["actual_satisfied"].sum())
        lo, hi = _wilson_ci(successes, n)
        rows.append({
            "bin": label, "n": n, "mean_predicted": float(region["predicted_satisfaction_probability"].mean()),
            "empirical_satisfaction_rate": float(successes / n), "ci_low": lo, "ci_high": hi, "empty_region": False,
        })
    return pd.DataFrame(rows)


def expected_calibration_error(curve: pd.DataFrame, n_total: int) -> float:
    valid = curve[curve["n"] > 0]
    if n_total == 0 or valid.empty:
        return float("nan")
    return float(sum(row["n"] / n_total * abs(row["mean_predicted"] - row["empirical_satisfaction_rate"]) for _, row in valid.iterrows()))


def threshold_metrics(sub: pd.DataFrame, threshold: float) -> dict:
    predicted_admit = sub["predicted_satisfaction_probability"] >= threshold
    outcomes = np.where(predicted_admit, sub["final_status"], "REJECTED")
    n = len(outcomes)
    admitted = outcomes != "REJECTED"
    satisfied = outcomes == "SATISFIED"
    violated = outcomes == "VIOLATED"
    false_feasibility = float((admitted & violated).sum() / admitted.sum()) if admitted.sum() else 0.0
    always_admit_satisfied = (sub["final_status"] == "SATISFIED").to_numpy()
    rejected_here = ~admitted
    false_rejection = (
        float((rejected_here & always_admit_satisfied).sum() / rejected_here.sum()) if rejected_here.sum() else 0.0
    )
    return {
        "threshold": threshold, "n": n, "admission_rate": float(admitted.sum() / n) if n else 0.0,
        "false_feasibility": false_feasibility, "false_rejection": false_rejection,
        "operational_satisfaction": float(satisfied.sum() / n) if n else 0.0,
    }


def threshold_sensitivity_table(df: pd.DataFrame) -> pd.DataFrame:
    """Verifies whether different candidate thresholds actually produce
    different admission decisions (P02's Discovery B found L3 made
    IDENTICAL decisions at every threshold - saturated near 0/1)."""
    rows = []
    for level in PROBABILISTIC_LEVELS:
        sub = df[df["planner_level"] == level].dropna(subset=["predicted_satisfaction_probability"])
        for threshold in CANDIDATE_THRESHOLDS:
            m = threshold_metrics(sub, threshold)
            m["planner_level"] = level
            rows.append(m)
    result = pd.DataFrame(rows)
    # decisions_vary_across_thresholds: does admission_rate actually change across thresholds per level?
    variance_by_level = result.groupby("planner_level")["admission_rate"].nunique()
    print("\nDistinct admission_rate values across thresholds (>1 means decisions are NOT saturated):")
    print(variance_by_level.to_string())
    return result


def cost_table(df: pd.DataFrame) -> pd.DataFrame:
    """Reports both mean and median simulation wall time - the mean alone
    is misleading here: a single four_node/L3 trial took ~48723s (~13.5h,
    vs. a median of well under 1s), evidently a real BBPSSW retry storm
    triggered by L3-original's overoptimistic attempt-rate admitting a
    plan real SeQUeNCe struggled to complete. This single-outlier
    catastrophic-cost risk is itself a checkpoint-2B finding, not just a
    statistical nuisance to average away."""
    rows = []
    for level in PLANNER_LEVELS:
        sub = df[df["planner_level"] == level]
        simulated = sub.dropna(subset=["simulation_wall_time_s"])
        rows.append({
            "planner_level": level, "n": len(sub),
            "mean_planning_time_s": float(sub["planning_time_s"].mean()),
            "mean_simulation_wall_time_s": float(simulated["simulation_wall_time_s"].mean()) if len(simulated) else None,
            "median_simulation_wall_time_s": float(simulated["simulation_wall_time_s"].median()) if len(simulated) else None,
            "max_simulation_wall_time_s": float(simulated["simulation_wall_time_s"].max()) if len(simulated) else None,
            "n_simulated": len(simulated),
        })
    return pd.DataFrame(rows)


def main() -> None:
    df = load()
    df = add_oracle_column(df)
    print(f"loaded {len(df)} trials")
    print(df["planner_level"].value_counts().to_string())

    decision_df = decision_quality_table(df)
    print("\n=== Decision quality (all trials, oracle-proxy based) ===")
    print(decision_df.to_string(index=False))

    mcnemar_df = mcnemar_pairwise(df)
    print("\n=== Pairwise McNemar test (paired on scenario+parameter_hash+seed) ===")
    print(mcnemar_df.to_string(index=False))

    delivery_df = delivery_prediction_table(df)
    print("\n=== Delivery-pairs prediction error ===")
    print(delivery_df.to_string(index=False))

    fidelity_df = fidelity_prediction_table(df)
    print("\n=== Fidelity prediction error ===")
    print(fidelity_df.to_string(index=False))

    calibration_rows = []
    probability_summary_rows = []
    for level in PROBABILISTIC_LEVELS:
        sub_all = df[df["planner_level"] == level].dropna(subset=["predicted_satisfaction_probability"])
        sub_val = sub_all[sub_all["seed"].isin(VALIDATION_SEEDS)]
        sub_test = sub_all[sub_all["seed"].isin(TEST_SEEDS)]

        curve = calibration_by_region(sub_all)
        curve["planner_level"] = level
        calibration_rows.append(curve)

        ece = expected_calibration_error(curve, len(sub_all))
        brier = brier_score(sub_all)
        logloss = log_loss(sub_all)
        print(f"\n=== {level} calibration-by-region (all seeds) ===")
        print(curve.to_string(index=False))
        print(f"{level}: Brier={brier:.4f}, log_loss={logloss:.4f}, ECE={ece:.4f}, n={len(sub_all)}")

        # threshold selection on validation, final metrics on test (same protocol as P02)
        validation_results = pd.DataFrame([threshold_metrics(sub_val, t) for t in CANDIDATE_THRESHOLDS])
        validation_results["combined_error"] = validation_results["false_feasibility"] + validation_results["false_rejection"]
        best_threshold = float(validation_results.loc[validation_results["combined_error"].idxmin(), "threshold"]) if len(validation_results) else None
        test_metrics = threshold_metrics(sub_test, best_threshold) if best_threshold is not None else {}

        probability_summary_rows.append({
            "planner_level": level, "n": len(sub_all), "brier_score": brier, "log_loss": logloss, "ece": ece,
            "selected_threshold_on_validation": best_threshold, "test_metrics_at_selected_threshold": test_metrics,
        })

    calibration_df = pd.concat(calibration_rows, ignore_index=True) if calibration_rows else pd.DataFrame()
    print("\n=== Threshold sensitivity (does admission_rate vary across thresholds?) ===")
    threshold_df = threshold_sensitivity_table(df)
    print(threshold_df.to_string(index=False))

    cost_df = cost_table(df)
    print("\n=== Planning/simulation cost by planner level ===")
    print(cost_df.to_string(index=False))

    decision_df.to_csv(PROCESSED_DIR / "P02b_decision_quality.csv", index=False)
    mcnemar_df.to_csv(PROCESSED_DIR / "P02b_mcnemar_pairwise.csv", index=False)
    delivery_df.to_csv(PROCESSED_DIR / "P02b_delivery_prediction.csv", index=False)
    fidelity_df.to_csv(PROCESSED_DIR / "P02b_fidelity_prediction.csv", index=False)
    calibration_df.to_csv(PROCESSED_DIR / "P02b_calibration_by_region.csv", index=False)
    threshold_df.to_csv(PROCESSED_DIR / "P02b_threshold_sensitivity.csv", index=False)
    cost_df.to_csv(PROCESSED_DIR / "P02b_cost.csv", index=False)

    summary = {
        "n_trials_total": len(df),
        "n_trials_by_planner_level": df["planner_level"].value_counts().to_dict(),
        "probability_calibration_summary": probability_summary_rows,
    }
    (PROCESSED_DIR / "P02b_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote processed outputs to {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
