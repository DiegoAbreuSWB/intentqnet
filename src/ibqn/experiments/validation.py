"""Scientific invariant checks over persisted `TrialRecord` rows (Fase H3,
see docs/campaign_architecture.md and the project brief's Fase H3,
section 15).

Two invariants are enforced *before* a row is ever written, not here:
- "the accepted route matches the planned route" - checked inside
  `runner.execute_trial` right after `SequenceExecutor.run()` (mirroring
  notebooks 11/12 of Fase H2); a mismatch raises, which `CampaignRunner`
  records as a trial failure rather than a silently-wrong row.
- "no duplicated pair per trial" - guaranteed by
  `assurance.telemetry.collect_intent_evidence`'s own `pair_number` dedup
  (Etapa G), and by `persistence.append_trial_record`'s `trial_id` dedup
  at the row level.

Everything else - ranges, status/field consistency, derived-metric
consistency - is checked here, over a `pandas.DataFrame` read back from
`trials.csv` (`persistence.read_trials_dataframe`). Invalid rows are
*reported*, never silently dropped or coerced (see section 15: "Trials
inválidos devem ser registrados como erro de validação, não silenciosamente
agregados").
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

_FIDELITY_FIELDS = ("requested_fidelity", "average_fidelity", "minimum_fidelity")
_NONNEGATIVE_INT_FIELDS = (
    "delivered_pairs", "excess_delivery_pairs", "hop_count", "requested_pairs",
    "eg_attempts", "eg_success", "ep_attempts", "ep_success", "es_attempts", "es_success",
)
_NONNEGATIVE_FLOAT_FIELDS = ("throughput_active_window", "throughput_delivery_interval")


@dataclass(frozen=True)
class ValidationIssue:
    trial_id: str
    check: str
    message: str


def _is_present(value) -> bool:
    return value is not None and not (isinstance(value, float) and pd.isna(value))


def _validate_row(row: pd.Series) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    trial_id = row.get("trial_id", "<unknown>")

    def flag(check: str, message: str) -> None:
        issues.append(ValidationIssue(trial_id=trial_id, check=check, message=message))

    for field_name in _FIDELITY_FIELDS:
        value = row.get(field_name)
        if _is_present(value) and not (0.0 <= float(value) <= 1.0):
            flag("fidelity_range", f"{field_name}={value} is outside [0, 1]")

    for field_name in _NONNEGATIVE_INT_FIELDS:
        value = row.get(field_name)
        if _is_present(value):
            if float(value) < 0:
                flag("nonnegative_count", f"{field_name}={value} is negative")
            if float(value) != int(float(value)):
                flag("integer_count", f"{field_name}={value} is not an integer")

    for field_name in _NONNEGATIVE_FLOAT_FIELDS:
        value = row.get(field_name)
        if _is_present(value) and float(value) < 0:
            flag("nonnegative_throughput", f"{field_name}={value} is negative")

    final_status = row.get("final_status")
    satisfied = row.get("satisfied")
    accepted = row.get("accepted")
    violations = row.get("violations")
    delivered_pairs = row.get("delivered_pairs")
    requested_pairs = row.get("requested_pairs")
    excess = row.get("excess_delivery_pairs")
    completion_time = row.get("completion_time_s")
    recovered = row.get("recovered")

    if final_status == "SATISFIED" and not bool(satisfied):
        flag("satisfied_status_consistency", "final_status is SATISFIED but satisfied is not True")

    if final_status == "VIOLATED" and not (_is_present(violations) and str(violations).strip()):
        flag("violated_has_violations", "final_status is VIOLATED but no violations were recorded")

    if final_status == "REJECTED":
        if bool(accepted):
            flag("rejected_not_accepted", "final_status is REJECTED but accepted is True")
        if _is_present(delivered_pairs):
            flag("rejected_no_evidence", "final_status is REJECTED but delivered_pairs has a value")

    if _is_present(recovered) and bool(recovered) and final_status != "SATISFIED":
        flag("recovered_implies_satisfied", f"recovered is True but final_status is {final_status!r}, not SATISFIED")

    if _is_present(delivered_pairs) and _is_present(requested_pairs) and _is_present(excess):
        expected_excess = max(0.0, float(delivered_pairs) - float(requested_pairs))
        if float(excess) != expected_excess:
            flag("excess_delivery_consistency", f"excess_delivery_pairs={excess}, expected {expected_excess}")

    if _is_present(completion_time) and _is_present(delivered_pairs) and _is_present(requested_pairs):
        if float(delivered_pairs) < float(requested_pairs):
            flag("completion_time_requires_full_delivery", "completion_time_s is set but delivered_pairs < requested_pairs")

    return issues


def validate_trials(df: pd.DataFrame) -> list[ValidationIssue]:
    """Runs every row-level invariant check over `df` (as returned by
    `persistence.read_trials_dataframe`), returning every violation found -
    an empty list means every row passed every check."""
    issues: list[ValidationIssue] = []
    for _, row in df.iterrows():
        issues.extend(_validate_row(row))
    return issues


def issues_to_dataframe(issues: list[ValidationIssue]) -> pd.DataFrame:
    if not issues:
        return pd.DataFrame(columns=["trial_id", "check", "message"])
    return pd.DataFrame([{"trial_id": i.trial_id, "check": i.check, "message": i.message} for i in issues])
