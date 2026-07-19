"""Record schema and persistence for the predictability-limits study (M9).

Deliberately separate from `planner_study_records.PlannerStudyTrialRecord`
(P01-P02B's schema) - never touches those files/campaigns, and adds one
outcome this new phase specifically needs: `TIMEOUT` (see
`scripts/run_predictability_trial_worker.py`'s module docstring for why a
hard per-trial wall-clock cap is mandatory here - the P02B campaign
produced one real trial that took ~48723s / ~13.5h of wall time; M9's
retry-storm and critical-region sweeps deliberately probe the same
parameter region and must not repeat that).
"""
from __future__ import annotations

import csv
import os
import shutil
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class PredictabilityTrialRecord:
    campaign: str
    trial_id: str
    scenario: str
    parameter_hash: str
    seed: int
    intent_id: str
    planner_level: str
    planner_name: str

    reserved_memory_slots: int
    min_delivered_pairs: int | None
    requested_fidelity: float
    duration_s: float
    attenuation_db_per_m: float | None

    route: str
    hop_count: int | None
    feasible: bool
    rejection_reason: str | None
    predicted_satisfaction_probability: float | None
    predicted_delivered_pairs: float | None
    predicted_average_fidelity: float | None
    purification_rounds_estimate: int | None
    planning_time_s: float | None

    final_status: str  # REJECTED | SATISFIED | VIOLATED | SIMULATION_ERROR | TIMEOUT
    satisfied: bool | None
    delivered_pairs: int | None
    average_fidelity: float | None
    observed_fidelity: float | None
    absolute_fidelity_error: float | None
    simulation_wall_time_s: float | None
    """For `TIMEOUT` rows, this is the enforced cap - a CENSORED value
    (the true time would have been >= this), never the actual time SeQUeNCe
    would have taken if left uninterrupted."""
    timed_out: bool

    eg_attempts: float | None
    eg_success: float | None
    ep_attempts: float | None
    ep_success: float | None
    es_attempts: float | None
    es_success: float | None

    project_git_commit: str | None
    sequence_git_commit: str | None
    python_version: str
    timestamp: str

    @classmethod
    def fieldnames(cls) -> list[str]:
        return [f.name for f in fields(cls)]


def trials_csv_path(output_directory: str | Path, campaign: str) -> Path:
    return Path(output_directory) / "raw" / campaign / "trials.csv"


def read_trial_ids(path: str | Path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {row["trial_id"] for row in csv.DictReader(f)}


def append_trial_record(path: str | Path, record: PredictabilityTrialRecord) -> None:
    """Same atomic-write-with-retry pattern as
    `planner_study_records.append_trial_record` (M6e found a transient
    Windows PermissionError on `os.replace` mid-campaign - reused here
    directly rather than re-derived)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    tmp_path = path.with_suffix(".csv.tmp")
    row = {f.name: getattr(record, f.name) for f in fields(record)}
    if is_new:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PredictabilityTrialRecord.fieldnames())
            writer.writeheader()
            writer.writerow(row)
        return

    shutil.copyfile(path, tmp_path)
    with open(tmp_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PredictabilityTrialRecord.fieldnames())
        writer.writerow(row)

    import time

    last_error: OSError | None = None
    for attempt in range(10):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.1 * (attempt + 1))
    raise last_error
