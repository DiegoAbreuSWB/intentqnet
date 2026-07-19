"""Predictability-limits study analysis (M9). Two independent parts:

1. **Information-level comparison** (sections 3-4 of the governing brief):
   reuses ALREADY-FROZEN P02B (results/planner_study/raw/
   P02b_resource_aware_planners/trials.csv) and P03
   (results/planner_study/raw/P03_l4_cost/trials.csv) data, READ-ONLY - no
   new simulation, no modification of those files. Existing planner
   levels are mapped onto four information levels (the brief's own
   framing, not a new planner taxonomy):

   - **Level 0** (topology + resources only): L1, L2, L2-R
   - **Level 1** (statistical rates): L3, L3-R
   - **Level 2** (full simulated network state via an internal batch):
     L4, the Reference Planner (section 8 - no longer called "the best
     planner")
   - **Level 3** (oracle / perfect future knowledge): not implementable;
     represented as the 0-error anchor every other level is measured
     against.

   Prediction error is Brier score: `mean((predicted_probability -
   actual_satisfied)^2)`. Level 0 planners never output a probability
   (predicted_average_fidelity aside) - their HARD admit/reject decision
   is scored as a degenerate probability (1.0 if admitted, 0.0 if
   rejected), which is the standard way to Brier-score a deterministic
   classifier. `actual_satisfied` uses an ORACLE PROXY (checkpoint 2B's
   own convention, reproduced here): for P02B, "was this exact
   (scenario, parameter_hash, seed) satisfied by ANY of the 5 paired
   planners?"; for P03 (only one planner, L4, was ever run per key), the
   proxy narrows to that trial's own outcome - a real, disclosed
   asymmetry between the two data sources, not hidden.

2. **Retry-storm** (section 5, P04_retry_storm) and **intrinsic
   variability** (section 1, P02_variance) analyses, over the new M9
   campaigns in results/predictability/raw/.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLANNER_STUDY_RAW = PROJECT_ROOT / "results" / "planner_study" / "raw"
PREDICTABILITY_RAW = PROJECT_ROOT / "results" / "predictability" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "results" / "predictability" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

INFO_LEVEL_BY_PLANNER = {
    "L1": 0, "L2": 0, "L2-R": 0,
    "L3": 1, "L3-R": 1,
    "L4": 2,
}


def brier_score(predicted: pd.Series, actual: pd.Series) -> float:
    return float(np.mean((predicted.to_numpy(dtype=float) - actual.to_numpy(dtype=float)) ** 2))


def analyze_information_levels() -> pd.DataFrame:
    p02b_path = PLANNER_STUDY_RAW / "P02b_resource_aware_planners" / "trials.csv"
    p03_path = PLANNER_STUDY_RAW / "P03_l4_cost" / "trials.csv"
    if not p02b_path.exists() or not p03_path.exists():
        raise FileNotFoundError("P02B/P03 raw data not found - these are frozen prior-phase results, expected to already exist")

    p02b = pd.read_csv(p02b_path)
    p02b["key"] = list(zip(p02b["scenario"], p02b["parameter_hash"], p02b["seed"]))
    satisfiable_keys = set(p02b.loc[p02b["final_status"] == "SATISFIED", "key"])
    p02b["oracle_satisfiable"] = p02b["key"].isin(satisfiable_keys).astype(float)

    p03 = pd.read_csv(p03_path)
    p03["oracle_satisfiable"] = (p03["final_status"] == "SATISFIED").astype(float)

    rows = []
    for level in ["L1", "L2", "L2-R"]:
        sub = p02b[p02b["planner_level"] == level]
        predicted = sub["feasible"].astype(float)
        rows.append({
            "planner_level": level, "information_level": INFO_LEVEL_BY_PLANNER[level], "n": len(sub),
            "brier_score": brier_score(predicted, sub["oracle_satisfiable"]),
            "prediction_type": "hard_decision (no probability output)",
        })
    for level in ["L3", "L3-R"]:
        sub = p02b[(p02b["planner_level"] == level)].dropna(subset=["predicted_satisfaction_probability"])
        rows.append({
            "planner_level": level, "information_level": INFO_LEVEL_BY_PLANNER[level], "n": len(sub),
            "brier_score": brier_score(sub["predicted_satisfaction_probability"], sub["oracle_satisfiable"]),
            "prediction_type": "predicted_satisfaction_probability",
        })
    l4 = p03[p03["planner_level"] == "L4"].dropna(subset=["predicted_satisfaction_probability"])
    rows.append({
        "planner_level": "L4", "information_level": INFO_LEVEL_BY_PLANNER["L4"], "n": len(l4),
        "brier_score": brier_score(l4["predicted_satisfaction_probability"], l4["oracle_satisfiable"]),
        "prediction_type": "predicted_satisfaction_probability (own-outcome oracle proxy - see module docstring)",
    })
    rows.append({
        "planner_level": "Oracle (theoretical)", "information_level": 3, "n": None,
        "brier_score": 0.0, "prediction_type": "not implementable - anchor only",
    })
    df = pd.DataFrame(rows)
    df.to_csv(PROCESSED_DIR / "information_level_comparison.csv", index=False)
    print("=== Information-level comparison (sections 3-4) ===")
    print(df.to_string(index=False))
    return df


def analyze_retry_storm() -> pd.DataFrame | None:
    path = PREDICTABILITY_RAW / "P04_retry_storm" / "trials.csv"
    if not path.exists():
        print("P04_retry_storm data not found yet - skipping")
        return None
    df = pd.read_csv(path)
    grouped = df.groupby("requested_fidelity").agg(
        n=("simulation_wall_time_s", "size"),
        mean_wall_s=("simulation_wall_time_s", "mean"),
        median_wall_s=("simulation_wall_time_s", "median"),
        max_wall_s=("simulation_wall_time_s", "max"),
        n_timeouts=("timed_out", "sum"),
        n_violated=("final_status", lambda s: (s == "VIOLATED").sum()),
        n_satisfied=("final_status", lambda s: (s == "SATISFIED").sum()),
        purification_rounds=("purification_rounds_estimate", "first"),
    ).reset_index()
    grouped.to_csv(PROCESSED_DIR / "retry_storm_by_fidelity.csv", index=False)
    print("\n=== Retry storm: wall time by target fidelity (P04) ===")
    print(grouped.to_string(index=False))
    return grouped


def analyze_intrinsic_variability() -> pd.DataFrame | None:
    path = PREDICTABILITY_RAW / "P02_variance" / "trials.csv"
    if not path.exists():
        print("P02_variance data not found yet - skipping")
        return None
    df = pd.read_csv(path)
    rows = []
    for intent_hash, group in df.groupby("parameter_hash"):
        for n in [100, 250, 500]:
            sub = group.iloc[:n] if len(group) >= 1 else group
            sub = sub[sub["seed"] < n] if "seed" in sub else sub
            n_actual = len(sub)
            if n_actual == 0:
                continue
            satisfied = (sub["final_status"] == "SATISFIED").mean()
            violated = (sub["final_status"] == "VIOLATED").mean()
            rejected = (sub["final_status"] == "REJECTED").mean()
            delivered = sub["delivered_pairs"].dropna()
            fidelity = sub["average_fidelity"].dropna()
            rows.append({
                "parameter_hash": intent_hash, "seed_count": n, "n_actual": n_actual,
                "p_satisfied": satisfied, "p_violated": violated, "p_rejected": rejected,
                "mean_delivered_pairs": delivered.mean() if len(delivered) else None,
                "std_delivered_pairs": delivered.std() if len(delivered) > 1 else None,
                "mean_fidelity": fidelity.mean() if len(fidelity) else None,
                "std_fidelity": fidelity.std() if len(fidelity) > 1 else None,
            })
    result = pd.DataFrame(rows)
    result.to_csv(PROCESSED_DIR / "intrinsic_variability_by_seed_count.csv", index=False)
    print("\n=== Intrinsic variability by growing seed count (P02) ===")
    print(result.to_string(index=False))
    return result


def eta_squared_one_way(df: pd.DataFrame, factor: str, response: str) -> float:
    """Proportion of total sum-of-squares in `response` explained by
    grouping on `factor` alone (one-way ANOVA effect size, `SS_between /
    SS_total`) - a simplified variance-decomposition approach (section 7)
    that does not require `statsmodels` (not a project dependency): each
    factor is scored independently, not as a joint N-way ANOVA, so
    factors sharing explanatory power are not double-counted correctly -
    a real limitation, disclosed here rather than presented as a full
    orthogonal decomposition."""
    sub = df.dropna(subset=[response, factor])
    if sub[factor].nunique() < 2 or len(sub) < 3:
        return float("nan")
    grand_mean = sub[response].mean()
    ss_total = ((sub[response] - grand_mean) ** 2).sum()
    if ss_total == 0:
        return float("nan")
    ss_between = sum(
        len(group) * (group[response].mean() - grand_mean) ** 2
        for _, group in sub.groupby(factor)
    )
    return float(ss_between / ss_total)


def analyze_variance_decomposition() -> pd.DataFrame:
    """Section 7: which factor dominates the observed result? Reuses
    P02B's already-frozen raw data (read-only, no new simulation) -
    `delivered_pairs` (continuous, only defined for simulated trials) is
    the response; each candidate factor is scored independently via
    one-way eta-squared (see `eta_squared_one_way`'s docstring for why
    this is a simplified, not a joint, decomposition)."""
    p02b_path = PLANNER_STUDY_RAW / "P02b_resource_aware_planners" / "trials.csv"
    df = pd.read_csv(p02b_path).dropna(subset=["delivered_pairs"])
    factors = ["scenario", "requested_fidelity", "duration_s", "reserved_memory_slots", "planner_level", "seed"]
    rows = [{"factor": f, "eta_squared": eta_squared_one_way(df, f, "delivered_pairs"), "n": len(df)} for f in factors]
    result = pd.DataFrame(rows).sort_values("eta_squared", ascending=False)
    result.to_csv(PROCESSED_DIR / "variance_decomposition.csv", index=False)
    print("\n=== Variance decomposition (section 7, one-way eta-squared on delivered_pairs, P02B data) ===")
    print(result.to_string(index=False))
    return result


def main() -> None:
    info_df = analyze_information_levels()
    retry_df = analyze_retry_storm()
    variance_df = analyze_intrinsic_variability()
    decomposition_df = analyze_variance_decomposition()

    summary = {
        "information_levels": info_df.to_dict(orient="records"),
        "retry_storm_available": retry_df is not None,
        "intrinsic_variability_available": variance_df is not None,
        "variance_decomposition": decomposition_df.to_dict(orient="records"),
    }
    (PROCESSED_DIR / "predictability_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote processed outputs to {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
