"""P03 analysis (planner-family study, M8/checkpoint 2): cost of L4's K
internal simulations. Reads only `results/planner_study/raw/P03_l4_cost/
trials.csv` - never re-runs a campaign. See scripts/run_p03_l4_cost.py's
docstring for this run's disclosed, reduced scope (K in {3,5,10}, not the
full {5,10,20,30}).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "results" / "planner_study" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "results" / "planner_study" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    path = RAW_DIR / "P03_l4_cost" / "trials.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - run scripts/run_p03_l4_cost.py first")
    df = pd.read_csv(path)
    # planner_level column holds "L4" (fixed) - K is encoded in the
    # campaign's own strategy name, part of trial_id (see run_p03_l4_cost.py)
    df["k"] = df["trial_id"].str.extract(r"L4_K(\d+)").astype(int)

    print(f"loaded {len(df)} trials")
    rows = []
    for (scenario, k), group in df.groupby(["scenario", "k"]):
        n = len(group)
        satisfied = (group["final_status"] == "SATISFIED").sum()
        rejected = (group["final_status"] == "REJECTED").sum()
        rows.append({
            "scenario": scenario, "k": k, "n": n,
            "satisfaction_rate": satisfied / n if n else None,
            "rejection_rate": rejected / n if n else None,
            "mean_planning_time_s": group["planning_time_s"].mean(),
            "mean_predicted_satisfaction_probability": group["predicted_satisfaction_probability"].mean(),
        })
    summary = pd.DataFrame(rows).sort_values(["scenario", "k"])
    print(summary.to_string(index=False))
    summary.to_csv(PROCESSED_DIR / "P03_l4_cost_summary.csv", index=False)
    print(f"\nwrote {PROCESSED_DIR / 'P03_l4_cost_summary.csv'}")


if __name__ == "__main__":
    main()
