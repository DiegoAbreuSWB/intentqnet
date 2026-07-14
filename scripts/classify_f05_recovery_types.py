"""Fase K3 (section 8): classifies each F05 reconciliation action by
what it actually changes about the intent's contract - never lumping
together a route change (internal, no contract impact), a resource
increase (more reserved_memory_slots, same SLA), and a duration increase
(a temporal/SLA element) under one undifferentiated "recovered" label.

recovery_type:
- strict_recovery: same SLA, same declared resources - only the
  internal execution plan (route) changed. (action == "route_change")
- resource_adjusted_recovery: reserved_memory_slots increased, SLA
  (min_delivered_pairs, duration_s) preserved. (action == "slot_increase")
- sla_relaxed_recovery: a temporal/contractual element (duration_s)
  changed. (action == "duration_increase")
- not_applicable: no reconciliation action was taken (already
  SATISFIED/REJECTED_OR_FAILED, or the policy decided no_action).

Applies regardless of whether the attempt actually succeeded
(`recovered`) - a failed duration_increase attempt (severe_loss_attempt)
is still classified sla_relaxed_recovery, just with recovered=False.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"

RECOVERY_TYPE_BY_ACTION = {
    "route_change": "strict_recovery",
    "slot_increase": "resource_adjusted_recovery",
    "duration_increase": "sla_relaxed_recovery",
}


def classify(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["recovery_type"] = df["action"].map(RECOVERY_TYPE_BY_ACTION).fillna("not_applicable")
    df["original_requirements_preserved"] = df["recovery_type"] == "strict_recovery"
    df["resource_adjustment"] = df["recovery_type"] == "resource_adjusted_recovery"
    df["sla_adjustment"] = df["recovery_type"] == "sla_relaxed_recovery"
    return df


def main() -> None:
    raw_path = RESULTS_DIR / "raw" / "F05_reconciliation" / "trials.csv"
    df = pd.read_csv(raw_path)
    classified = classify(df)

    out_dir = RESULTS_DIR / "processed" / "F05_reconciliation"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "trials_with_recovery_type.csv"
    classified.to_csv(out_path, index=False)

    print(classified.groupby(["case", "recovery_type"])["recovered"].agg(["count", "mean"]))
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()
