"""P01 analysis (planner-family study, M4/checkpoint 1): L1 vs. L2 on the
three-node and four-node chains. Reads only persisted `results/planner_study/
raw/P01_*/trials.csv` - never re-runs a campaign (docs/planner_study_baseline.md).

Computes, per topology and planner level (L1=automatic, L2=iterative_analytical):
- false rejection rate proxy: since P01 doesn't re-run an offline oracle,
  "false rejection eliminated by L2" is measured directly as "L1 REJECTED at
  this (scenario, min_fidelity) cell but L2 reached SATISFIED" - a stronger,
  more direct signal than an oracle re-test for this specific L1-vs-L2
  comparison, because L2's own real SeQUeNCe execution IS the ground truth
  check here (see docs/l2_iterative_model.md).
- fidelity estimation error (estimated vs. observed, where defined);
- planning_time_s (planning cost);
- satisfaction rate.

Writes results/planner_study/processed/P01_l1_l2_comparison.csv and prints
the checkpoint-1 summary table.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "results" / "planner_study" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "results" / "planner_study" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

PLANNER_LEVEL_BY_POLICY = {"automatic": "L1", "iterative_analytical": "L2"}

CAMPAIGNS = {
    "three_node": "P01_l1_l2_purification_three_node",
    "four_node": "P01_l1_l2_purification_four_node",
}


def load_campaign(name: str) -> pd.DataFrame:
    path = RAW_DIR / name / "trials.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found - has the P01 campaign been run? (scripts/analyze_p01_l1_l2.py)")
    df = pd.read_csv(path)
    df["planner_level"] = df["purification_policy"].map(PLANNER_LEVEL_BY_POLICY)
    return df


def per_cell_summary(df: pd.DataFrame, topology: str) -> pd.DataFrame:
    rows = []
    for level in ["L1", "L2"]:
        sub = df[df["planner_level"] == level]
        for min_fidelity, cell in sub.groupby("requested_fidelity"):
            n = len(cell)
            satisfied = int((cell["final_status"] == "SATISFIED").sum())
            rejected = int((cell["final_status"] == "REJECTED").sum())
            violated = int((cell["final_status"] == "VIOLATED").sum())
            fidelity_errors = cell["absolute_fidelity_error"].dropna()
            planning_times = cell["planning_time_s"].dropna()
            rows.append({
                "topology": topology, "planner_level": level, "min_fidelity": min_fidelity, "n": n,
                "satisfied": satisfied, "rejected": rejected, "violated": violated,
                "satisfaction_rate": satisfied / n if n else None,
                "rejection_rate": rejected / n if n else None,
                "mean_abs_fidelity_error": fidelity_errors.mean() if len(fidelity_errors) else None,
                "mean_planning_time_s": planning_times.mean() if len(planning_times) else None,
            })
    return pd.DataFrame(rows)


def false_rejections_eliminated(df: pd.DataFrame, topology: str) -> pd.DataFrame:
    """Per (min_fidelity, seed) cell where L1 REJECTED: did L2 reach
    SATISFIED on the SAME seed (i.e. the same random elementary-generation
    draws)? This is the direct, paired comparison P01 exists to make -
    stronger than an oracle re-test since L2's own real execution result is
    itself the empirical check."""
    l1 = df[df["planner_level"] == "L1"][["requested_fidelity", "seed", "final_status"]].rename(
        columns={"final_status": "l1_status"}
    )
    l2 = df[df["planner_level"] == "L2"][["requested_fidelity", "seed", "final_status"]].rename(
        columns={"final_status": "l2_status"}
    )
    paired = l1.merge(l2, on=["requested_fidelity", "seed"], how="inner")
    paired["topology"] = topology
    rejected_by_l1 = paired[paired["l1_status"] == "REJECTED"]
    summary = (
        rejected_by_l1.groupby("requested_fidelity")["l2_status"]
        .apply(lambda s: (s == "SATISFIED").mean())
        .rename("l2_resolution_rate")
        .reset_index()
    )
    summary["topology"] = topology
    summary["n_rejected_by_l1"] = rejected_by_l1.groupby("requested_fidelity").size().values
    return summary


def main() -> None:
    all_cells = []
    all_resolutions = []
    for topology, campaign_name in CAMPAIGNS.items():
        df = load_campaign(campaign_name)
        all_cells.append(per_cell_summary(df, topology))
        all_resolutions.append(false_rejections_eliminated(df, topology))

    cells = pd.concat(all_cells, ignore_index=True)
    resolutions = pd.concat(all_resolutions, ignore_index=True)

    cells_path = PROCESSED_DIR / "P01_l1_l2_comparison.csv"
    cells.to_csv(cells_path, index=False)
    resolutions_path = PROCESSED_DIR / "P01_l1_l2_false_rejection_resolution.csv"
    resolutions.to_csv(resolutions_path, index=False)

    print(f"wrote {cells_path} ({len(cells)} rows)")
    print(f"wrote {resolutions_path} ({len(resolutions)} rows)")
    print()
    print("=== Per-cell summary (satisfaction rate, fidelity error, planning time) ===")
    print(cells.to_string(index=False))
    print()
    print("=== L2 resolution rate among cells L1 REJECTED (paired by seed) ===")
    print(resolutions.to_string(index=False))

    overall = {
        "three_node_l1_rejection_rate_overall": float(
            cells[(cells.topology == "three_node") & (cells.planner_level == "L1")]["rejected"].sum()
            / cells[(cells.topology == "three_node") & (cells.planner_level == "L1")]["n"].sum()
        ),
        "three_node_l2_rejection_rate_overall": float(
            cells[(cells.topology == "three_node") & (cells.planner_level == "L2")]["rejected"].sum()
            / cells[(cells.topology == "three_node") & (cells.planner_level == "L2")]["n"].sum()
        ),
        "four_node_l1_rejection_rate_overall": float(
            cells[(cells.topology == "four_node") & (cells.planner_level == "L1")]["rejected"].sum()
            / cells[(cells.topology == "four_node") & (cells.planner_level == "L1")]["n"].sum()
        ),
        "four_node_l2_rejection_rate_overall": float(
            cells[(cells.topology == "four_node") & (cells.planner_level == "L2")]["rejected"].sum()
            / cells[(cells.topology == "four_node") & (cells.planner_level == "L2")]["n"].sum()
        ),
    }
    summary_path = PROCESSED_DIR / "P01_l1_l2_overall_summary.json"
    summary_path.write_text(json.dumps(overall, indent=2), encoding="utf-8")
    print()
    print(f"wrote {summary_path}")
    print(json.dumps(overall, indent=2))


if __name__ == "__main__":
    main()
