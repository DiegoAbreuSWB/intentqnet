"""Record schema and persistence for the M10 robust-predictability-
validation phase - SEPARATE from `planner_study_records` (P01-P02B,
frozen) and `predictability_records` (M9, frozen). Adds full
determinism/environment provenance (project commit, SeQUeNCe commit,
Python/NumPy versions, operational seed, RNG namespace seeds,
PYTHONHASHSEED, hostname/platform, determinism mode) and a
`trajectory_hash` (event/counter-based, excludes wall-clock time) - see
`docs/predictability_m10/randomness_audit.md` and section 5 of the
governing M10 brief for why wall time is never used as replay evidence.
"""
from __future__ import annotations

import csv
import hashlib
import os
from dataclasses import dataclass, fields
from pathlib import Path


@dataclass
class PredictabilityM10TrialRecord:
    # --- identity ---
    campaign: str
    trial_id: str
    scenario: str
    parameter_hash: str
    seed: int
    intent_id: str
    planner_level: str
    planner_name: str
    replay_index: int
    """Which of the N repeated replays of the same nominal trial this row
    is (0-indexed) - `0` for every non-replay campaign."""

    # --- requested parameters ---
    reserved_memory_slots: int
    min_delivered_pairs: int | None
    requested_fidelity: float
    duration_s: float
    attenuation_db_per_m: float | None
    distance_m: float | None
    allow_purification: bool

    # --- plan / prediction ---
    route: str
    hop_count: int | None
    feasible: bool
    rejection_reason: str | None
    predicted_satisfaction_probability: float | None
    predicted_delivered_pairs: float | None
    predicted_average_fidelity: float | None
    purification_rounds_estimate: int | None
    planning_time_s: float | None

    # --- outcome ---
    final_status: str  # REJECTED | SATISFIED | VIOLATED | SIMULATION_ERROR | TIMEOUT
    satisfied: bool | None
    delivered_pairs: int | None
    average_fidelity: float | None
    observed_fidelity: float | None
    absolute_fidelity_error: float | None
    simulation_wall_time_s: float | None
    """Explicitly NOT used as replay evidence (see module docstring) -
    reported for cost analysis only."""
    timed_out: bool
    timeout_s: float | None

    # --- attempt telemetry ---
    eg_attempts: float | None
    eg_success: float | None
    ep_attempts: float | None
    ep_success: float | None
    es_attempts: float | None
    es_success: float | None
    timeline_end_time_s: float | None
    """Simulation time (not wall-clock) at which the trial's timeline
    stopped processing - a reproducible, deterministic quantity, unlike
    wall time."""

    # --- trajectory hash (replay evidence - section 5) ---
    trajectory_hash: str | None
    """SHA-256 over a canonical, wall-clock-free summary of the trial's
    logical trajectory (final_status, delivered_pairs, fidelity, route,
    attempt/success counters, timeline_end_time_s) - see
    `compute_trajectory_hash`. Two replays of the same nominal trial with
    identical `trajectory_hash` are LOGICALLY_IDENTICAL by construction."""

    # --- determinism / RNG manifest (M10.2) ---
    determinism_enabled: bool
    master_seed: int | None
    execution_seed_used: int | None
    namespace_seeds_json: str | None
    python_random_reseeded: bool
    python_hash_seed_env_value: str | None

    # --- provenance ---
    project_git_commit: str | None
    sequence_git_commit: str | None
    python_version: str
    numpy_version: str
    dependency_versions_json: str | None
    platform_system: str | None
    platform_release: str | None
    hostname: str | None
    timestamp: str

    # --- tail-event diagnostics (M10.8) ---
    termination_reason: str | None = None
    """One of TIMEOUT/NO_PROGRESS/MAX_RETRIES/SIMULATION_COMPLETE/ERROR
    (section 13's vocabulary) - populated only by P14_tail_event_study;
    `None` for every other M10 campaign. Distinct from `final_status`:
    this classifies WHY/HOW a trial's execution ended (a safety-limit
    diagnosis), never re-labels a genuine SATISFIED/VIOLATED outcome."""
    heartbeat_final_sim_time_s: float | None = None
    heartbeat_final_run_counter: int | None = None
    heartbeat_n_samples: int | None = None

    @classmethod
    def fieldnames(cls) -> list[str]:
        return [f.name for f in fields(cls)]


def compute_trajectory_hash(
    *, final_status: str, delivered_pairs: int | None, average_fidelity: float | None,
    route: str, eg_attempts, eg_success, ep_attempts, ep_success, es_attempts, es_success,
    timeline_end_time_s: float | None,
) -> str:
    """Canonical, wall-clock-free trajectory summary, hashed with
    SHA-256. Floats are rounded to 9 decimal digits before hashing - this
    tolerates harmless last-bit floating-point representation noise
    (e.g. platform-dependent `libm` rounding in the final digit of a
    `repr()`) without masking a genuine logical difference, which would
    show up at a much coarser precision than 1e-9 for anything this
    project's physics produces (fidelities and rates in [0, 1], not
    values relying on catastrophic cancellation)."""
    def _round(x):
        return round(x, 9) if isinstance(x, float) else x

    parts = [
        str(final_status), str(delivered_pairs), str(_round(average_fidelity)), str(route),
        str(_round(eg_attempts)), str(_round(eg_success)), str(_round(ep_attempts)), str(_round(ep_success)),
        str(_round(es_attempts)), str(_round(es_success)), str(_round(timeline_end_time_s)),
    ]
    canonical = "|".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def trials_csv_path(output_directory: str | Path, campaign: str) -> Path:
    return Path(output_directory) / "raw" / campaign / "trials.csv"


def read_trial_ids(path: str | Path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    with open(path, newline="", encoding="utf-8") as f:
        return {row["trial_id"] for row in csv.DictReader(f)}


def append_trial_record(path: str | Path, record: PredictabilityM10TrialRecord) -> None:
    """Same atomic-write-with-retry pattern as `planner_study_records`/
    `predictability_records` (M6e found a transient Windows
    PermissionError on `os.replace` mid-campaign - reused, not re-derived)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not path.exists()
    tmp_path = path.with_suffix(".csv.tmp")
    row = {f.name: getattr(record, f.name) for f in fields(record)}
    if is_new:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PredictabilityM10TrialRecord.fieldnames())
            writer.writeheader()
            writer.writerow(row)
        return

    import shutil

    shutil.copyfile(path, tmp_path)
    with open(tmp_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PredictabilityM10TrialRecord.fieldnames())
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
