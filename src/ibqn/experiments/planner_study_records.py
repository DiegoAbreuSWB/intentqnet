"""Record schema and lightweight CSV persistence for planner-family study
campaigns (P02+) - deliberately SEPARATE from `experiments.records.
TrialRecord`/`experiments.persistence` (F01-F08's schema), because L3 (and
later L4/L5) carry prediction fields (`predicted_satisfaction_probability`,
etc.) that do not exist on the F01-F08 schema and must never be bolted
onto it (docs/planner_study_baseline.md: F01-F08 stay byte-identical).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class PlannerStudyTrialRecord:
    """One row for a planner-family study campaign (P02+). Fields with no
    real evidence are `None`, never `0`/`0.0` - same convention as
    `experiments.records.TrialRecord`."""

    # --- identity ---
    campaign: str
    trial_id: str
    scenario: str
    parameter_hash: str
    seed: int
    intent_id: str
    planner_level: str
    planner_name: str

    # --- requested parameters ---
    reserved_memory_slots: int
    min_delivered_pairs: int | None
    requested_fidelity: float
    duration_s: float
    attenuation_db_per_m: float | None

    # --- plan / prediction (always known before simulating; None if the level doesn't predict it) ---
    route: str
    hop_count: int | None
    feasible: bool
    rejection_reason: str | None
    predicted_satisfaction_probability: float | None
    predicted_delivered_pairs: float | None
    predicted_average_fidelity: float | None
    purification_rounds_estimate: int | None
    planning_time_s: float | None

    # --- outcome (only if deployed) ---
    final_status: str
    satisfied: bool | None
    delivered_pairs: int | None
    average_fidelity: float | None
    observed_fidelity: float | None
    absolute_fidelity_error: float | None
    simulation_wall_time_s: float | None

    # --- provenance ---
    project_git_commit: str | None
    sequence_git_commit: str | None
    python_version: str
    timestamp: str

    # --- physical model / calibrated suite (docs/physical_model.md,
    # docs/parameter_calibration.md) - declared with defaults, and therefore
    # last, so rows persisted before the revision still load ---
    formalism: str | None = None
    platform: str | None = None
    purification_mode: str | None = None
    """Policy actually executed for the deployed plan; None when rejected."""
    regime: str | None = None
    """Campaign-declared label of the parameter combination (e.g.
    `generous`, `marginal`) - carried on the row so analysis never has to
    re-derive it from `parameter_hash`."""
    allow_purification: bool | None = None
    minimum_fidelity: float | None = None
    discarded_pairs: int | None = None
    eg_attempts: int | None = None
    eg_success: int | None = None
    ep_attempts: int | None = None
    ep_success: int | None = None
    es_attempts: int | None = None
    es_success: int | None = None
    """Source-node native counters (diagnostic, not per-intent) - same
    convention as `experiments.records.TrialRecord`."""

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


def append_trial_record(path: str | Path, record: PlannerStudyTrialRecord) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    tmp_path = path.with_suffix(".csv.tmp")
    row = {f.name: getattr(record, f.name) for f in fields(record)}
    if is_new:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PlannerStudyTrialRecord.fieldnames())
            writer.writeheader()
            writer.writerow(row)
        return
    # atomic append: copy existing + new row to a tmp file, then replace -
    # matches the project's standing atomic-write convention
    # (src/ibqn/experiments/export.py) as a defense against partial writes.
    import shutil

    shutil.copyfile(path, tmp_path)
    with open(tmp_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PlannerStudyTrialRecord.fieldnames())
        writer.writerow(row)
    import os
    import time

    # `os.replace` can transiently fail on Windows with PermissionError
    # (WinError 5) when another process (antivirus, OneDrive/cloud sync on
    # a synced Desktop folder, a search indexer) briefly holds a read
    # handle on a just-written file - observed during the P02B campaign
    # (a 1200-trial run failing outright at trial 187 on an otherwise
    # correct write). This is a transient OS-level lock, not a data
    # correctness issue - retry with a short backoff rather than losing
    # an entire long-running campaign to one flaky rename.
    last_error: OSError | None = None
    for attempt in range(10):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.1 * (attempt + 1))
    raise last_error
