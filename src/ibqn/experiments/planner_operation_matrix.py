"""Fase J5: quantifies the gap between the planner's prediction
(feasible/infeasible) and what actually happened operationally
(SATISFIED/VIOLATED/REJECTED/FAILED) - see docs/planner_operational_gap.md.

A pure analysis module over already-persisted `TrialRecord` rows (like
`validation.py`/`aggregation.py`) - `final_status`/`accepted` already
encode everything needed for the base classification, since
`runner.execute_trial` only ever produces `final_status="REJECTED"` from
`IntentPlanner`'s OWN pre-simulation feasibility check (never after
simulating), and `"FAILED"` only from SeQUeNCe's OWN reservation
admission rejecting a plan the planner itself thought was feasible
(`IntentRequestApp.get_reservation_result(result=False)`) - a materially
different (and, in this project's campaigns so far, unobserved) failure
mode from planner infeasibility. No new TrialRecord fields were needed
for this classification.
"""
from __future__ import annotations

import pandas as pd

FEASIBLE_AND_SATISFIED = "FEASIBLE_AND_SATISFIED"
FEASIBLE_BUT_VIOLATED = "FEASIBLE_BUT_VIOLATED"
INFEASIBLE_AND_REJECTED = "INFEASIBLE_AND_REJECTED"
INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE = "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE"
EXECUTION_FAILED = "EXECUTION_FAILED"

_CATEGORY_BY_STATUS = {
    "SATISFIED": FEASIBLE_AND_SATISFIED,
    "VIOLATED": FEASIBLE_BUT_VIOLATED,
    "REJECTED": INFEASIBLE_AND_REJECTED,
    "FAILED": EXECUTION_FAILED,
}


def classify_trials(df: pd.DataFrame) -> pd.Series:
    """Maps each row's `final_status` to one of the five operational
    categories (section 7.2) - every `REJECTED` row starts as
    `INFEASIBLE_AND_REJECTED`; use `upgrade_rejected_with_oracle` to
    reclassify the subset an oracle run shows was actually satisfiable."""
    unknown = set(df["final_status"].unique()) - _CATEGORY_BY_STATUS.keys()
    if unknown:
        raise ValueError(f"unknown final_status value(s): {sorted(unknown)}")
    return df["final_status"].map(_CATEGORY_BY_STATUS)


def upgrade_rejected_with_oracle(
    categories: pd.Series, df: pd.DataFrame, oracle_satisfied_by_trial_id: dict[str, bool],
) -> pd.Series:
    """Reclassifies `INFEASIBLE_AND_REJECTED` rows to
    `INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE` wherever
    `oracle_satisfied_by_trial_id[trial_id]` is `True` - i.e. an
    oracle run (same topology/intent/seed, no feasibility pre-check,
    see `experiments.baselines.run_offline_oracle_baseline`) reached
    `SATISFIED` despite the planner rejecting the intent outright: a
    genuine false negative. Rows whose `trial_id` isn't in the mapping
    (no oracle was run for them) keep their original classification -
    never inferred, never assumed."""
    updated = categories.copy()
    for trial_id, oracle_satisfied in oracle_satisfied_by_trial_id.items():
        if not oracle_satisfied:
            continue
        mask = (df["trial_id"] == trial_id) & (categories == INFEASIBLE_AND_REJECTED)
        updated.loc[mask] = INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE
    return updated


def build_matrix(df: pd.DataFrame, categories: pd.Series | None = None) -> pd.DataFrame:
    """Planner x Operation contingency table (section 7.3): one row per
    operational category, with counts and a human-readable
    interpretation - the same five rows as the project brief's example
    table, populated from real data instead of illustrative blanks."""
    categories = categories if categories is not None else classify_trials(df)
    counts = categories.value_counts()
    interpretations = {
        FEASIBLE_AND_SATISFIED: "previsão correta",
        FEASIBLE_BUT_VIOLATED: "falsa viabilidade operacional",
        INFEASIBLE_AND_REJECTED: "rejeição prevista (nunca testada contra oracle)",
        INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE: "falso negativo do planner (oracle confirma satisfazível)",
        EXECUTION_FAILED: "reserva rejeitada pelo próprio SeQUeNCe, apesar do planner achar viável",
    }
    rows = [
        {"category": category, "count": int(counts.get(category, 0)), "interpretation": interpretation}
        for category, interpretation in interpretations.items()
    ]
    return pd.DataFrame(rows)


def compute_gap_metrics(
    df: pd.DataFrame, categories: pd.Series | None = None, *, oracle_tested_trial_ids: set[str] | None = None,
) -> dict:
    """Section 7.4's metrics, computed straight from persisted
    `TrialRecord` columns - `None` (never `0`) wherever the denominator
    would be zero (no such trials exist in `df`), consistent with this
    project's rule of never substituting a missing measurement with a
    fabricated zero.

    - `operational_success_rate`: SATISFIED / all trials - "of every
      request submitted to the system (including ones the planner
      itself rejected), how many were actually satisfied end to end."
    - `false_feasibility_rate`: FEASIBLE_BUT_VIOLATED / all
      planner-feasible trials (SATISFIED + VIOLATED + FAILED).
    - `false_rejection_rate`: INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE /
      `len(oracle_tested_trial_ids)` - i.e. only over the subset of
      rejected trials an oracle was ACTUALLY run against (see
      `upgrade_rejected_with_oracle`). `oracle_tested_trial_ids` must be
      passed explicitly: it is the only way to distinguish "every
      oracle-tested rejection turned out to be a true rejection" (rate
      0.0, a real finding) from "no oracle comparison was ever performed"
      (rate `None`) - the category labels alone are indistinguishable
      between those two cases once an upgrade finds nothing to upgrade.
    - `fidelity_prediction_error`: mean absolute fidelity error
      (`TrialRecord.absolute_fidelity_error`, Fase J1) over trials where
      it's available.
    - `delivery_deficit`: mean `max(0, min_delivered_pairs - delivered_pairs)`
      over trials that declare `min_delivered_pairs` and have delivery
      evidence - how far short of the declared delivery goal, on
      average, among trials that fell short (0 counted for trials that
      met or exceeded it).
    - `throughput_deficit`: mean `max(0, min_delivered_pairs/duration_s -
      throughput_active_window)` over the same trials - the analogous
      gap in rate terms.
    """
    categories = categories if categories is not None else classify_trials(df)
    n_total = len(df)

    def _rate(numerator: int, denominator: int) -> float | None:
        return (numerator / denominator) if denominator > 0 else None

    n_feasible = int((categories.isin([FEASIBLE_AND_SATISFIED, FEASIBLE_BUT_VIOLATED, EXECUTION_FAILED])).sum())
    n_satisfied = int((categories == FEASIBLE_AND_SATISFIED).sum())
    n_false_feasible = int((categories == FEASIBLE_BUT_VIOLATED).sum())
    n_infeasible_upgraded = int((categories == INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE).sum())
    n_oracle_tested = len(oracle_tested_trial_ids) if oracle_tested_trial_ids else 0

    fidelity_errors = df["absolute_fidelity_error"].dropna().abs() if "absolute_fidelity_error" in df.columns else pd.Series(dtype=float)

    deficits, throughput_deficits = [], []
    if "min_delivered_pairs" in df.columns and "delivered_pairs" in df.columns:
        goal_rows = df[df["min_delivered_pairs"].notna() & df["delivered_pairs"].notna()]
        for _, row in goal_rows.iterrows():
            deficits.append(max(0.0, row["min_delivered_pairs"] - row["delivered_pairs"]))
            if "throughput_active_window" in df.columns and pd.notna(row.get("throughput_active_window")) and pd.notna(row.get("duration_s")):
                required_rate = row["min_delivered_pairs"] / row["duration_s"]
                throughput_deficits.append(max(0.0, required_rate - row["throughput_active_window"]))

    return {
        "n_total": n_total,
        "operational_success_rate": _rate(n_satisfied, n_total),
        "false_feasibility_rate": _rate(n_false_feasible, n_feasible),
        "false_rejection_rate": _rate(n_infeasible_upgraded, n_oracle_tested),
        "fidelity_prediction_error": float(fidelity_errors.mean()) if len(fidelity_errors) else None,
        "delivery_deficit": (sum(deficits) / len(deficits)) if deficits else None,
        "throughput_deficit": (sum(throughput_deficits) / len(throughput_deficits)) if throughput_deficits else None,
    }
