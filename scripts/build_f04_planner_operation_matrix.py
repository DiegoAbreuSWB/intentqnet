"""Builds F04's planner-vs-operation matrix/gap metrics from F02+F03's
current trials.csv (Fase J10; extended in Fase K2 when F03's purification
thresholds were densified - see docs/results_provenance.md). Re-run this
whenever F02 or F03's raw data changes; it always reads the full current
trials.csv, never a cached row count, so it stays correct after either
campaign is extended.

Oracle-tests every REJECTED trial from F03's `three_node_1_repeater`
scenario (single-route topology, so the oracle has exactly one candidate
- matching the planner's own route by construction, still a genuine
simulation, not an assumption) - `linear_chain_2_repeaters`'s rejections
are not reconstructed/tested (no equally simple, unambiguous topology
spec to rebuild from the persisted row alone).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.baselines import run_offline_oracle_baseline
from ibqn.experiments.persistence import read_trials_dataframe, trials_csv_path
from ibqn.experiments.planner_operation_matrix import (
    build_matrix,
    classify_trials,
    compute_gap_metrics,
    upgrade_rejected_with_oracle,
)
from ibqn.intent.models import SuccessCondition

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"


def main() -> None:
    frames = []
    for campaign in ["F02_routing", "F03_purification"]:
        df = read_trials_dataframe(trials_csv_path(RESULTS_DIR, campaign))
        df["source_campaign"] = campaign
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)

    categories = classify_trials(combined)
    print("Category counts:")
    print(categories.value_counts())

    rejected_rows = combined[categories == "INFEASIBLE_AND_REJECTED"]
    oracle_satisfied_by_trial_id: dict[str, bool] = {}
    oracle_tested_trial_ids: set[str] = set()

    for _, row in rejected_rows.iterrows():
        if row["source_campaign"] != "F03_purification" or row["scenario"] != "three_node_1_repeater":
            continue
        min_fidelity = row["requested_fidelity"]
        spec = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
        intent = simple_intent(
            intent_id=f"f04-oracle-{row['trial_id']}", source="a", destination="b", min_fidelity=min_fidelity,
            requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
            success_conditions=[
                SuccessCondition(metric="delivered_pairs", operator=">=", expected=10),
                SuccessCondition(metric="average_fidelity", operator=">=", expected=min_fidelity),
            ],
        )
        oracle_result = run_offline_oracle_baseline(spec, intent, seed=int(row["seed"]))
        oracle_tested_trial_ids.add(row["trial_id"])
        oracle_satisfied_by_trial_id[row["trial_id"]] = bool(oracle_result.satisfied)

    print(f"\nOracle-tested {len(oracle_tested_trial_ids)} rejected trials")
    upgraded_categories = upgrade_rejected_with_oracle(categories, combined, oracle_satisfied_by_trial_id)
    print("Category counts after oracle upgrade:")
    print(upgraded_categories.value_counts())

    matrix = build_matrix(combined, upgraded_categories)
    metrics = compute_gap_metrics(combined, upgraded_categories, oracle_tested_trial_ids=oracle_tested_trial_ids)

    out_dir = RESULTS_DIR / "processed" / "F04_planner_vs_operation"
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix.to_csv(out_dir / "matrix.csv", index=False)
    (out_dir / "gap_metrics.json").write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")

    combined_with_categories = combined.copy()
    combined_with_categories["category"] = upgraded_categories
    combined_with_categories.to_csv(out_dir / "combined_trials_with_categories.csv", index=False)

    print("\nMatrix:")
    print(matrix)
    print("\nGap metrics:")
    print(json.dumps(metrics, indent=2, default=str))
    print("DONE")


if __name__ == "__main__":
    main()
