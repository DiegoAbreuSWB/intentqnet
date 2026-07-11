"""Incremental persistence for campaign trials (Fase H3, see
docs/campaign_architecture.md, sections 4/6/7/12-13).

`trials.csv` is appended to one row at a time (never buffered in memory
for a whole campaign) so a killed process loses at most the one trial in
flight - never previously-completed ones. `errors.jsonl` is a plain
append-only log, one JSON object per line. Both are read back with
standard library `csv`/`json`, which tolerate a ragged/partial last line
(the exact scenario `resume` needs to survive) without raising.
"""
from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from .records import TrialRecord


def trials_csv_path(output_directory: str | Path, campaign: str) -> Path:
    return Path(output_directory) / "raw" / campaign / "trials.csv"


def errors_jsonl_path(output_directory: str | Path, campaign: str) -> Path:
    return Path(output_directory) / "raw" / campaign / "errors.jsonl"


def read_trial_ids(path: str | Path) -> set[str]:
    """Returns every `trial_id` already present in `trials.csv`, or an
    empty set if the file doesn't exist yet. Tolerates a truncated last
    row (its `trial_id` cell is still read as-is if present; a wholly
    empty/missing final row is simply skipped by `csv.DictReader`)."""
    csv_path = Path(path)
    if not csv_path.exists():
        return set()
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return {row["trial_id"] for row in reader if row.get("trial_id")}


def read_trials_dataframe(path: str | Path) -> pd.DataFrame:
    """Reads `trials.csv` back as a `DataFrame` for aggregation/validation/
    notebooks - returns an empty (but correctly-columned) `DataFrame` if
    the file doesn't exist yet."""
    csv_path = Path(path)
    if not csv_path.exists():
        return pd.DataFrame(columns=TrialRecord.fieldnames())
    return pd.read_csv(csv_path)


def append_trial_record(path: str | Path, record: TrialRecord, *, known_trial_ids: set[str]) -> bool:
    """Appends `record` to `trials.csv` (creating it with a header if
    needed), skipping it if `record.trial_id` is already in
    `known_trial_ids` (defense in depth against a caller accidentally
    running the same trial twice in one process - `CampaignRunner` itself
    already filters completed trials out before this is ever called).
    Returns whether the row was actually written. Mutates
    `known_trial_ids` on success, so callers can pass the same set across
    many calls without re-reading the file each time."""
    if record.trial_id in known_trial_ids:
        return False

    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists() or csv_path.stat().st_size == 0

    with csv_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TrialRecord.fieldnames())
        if write_header:
            writer.writeheader()
        writer.writerow(asdict(record))

    known_trial_ids.add(record.trial_id)
    return True


def append_error_record(
    path: str | Path,
    *,
    trial_id: str,
    campaign: str,
    scenario: str,
    parameter_hash: str,
    strategy: str,
    seed: int,
    intent_id: str,
    error_type: str,
    error_message: str,
    timestamp: str,
) -> None:
    errors_path = Path(path)
    errors_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "trial_id": trial_id,
        "campaign": campaign,
        "scenario": scenario,
        "parameter_hash": parameter_hash,
        "strategy": strategy,
        "seed": seed,
        "intent_id": intent_id,
        "error_type": error_type,
        "error_message": error_message,
        "timestamp": timestamp,
    }
    with errors_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def read_errors(path: str | Path) -> list[dict]:
    errors_path = Path(path)
    if not errors_path.exists():
        return []
    entries = []
    with errors_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a truncated last line after a killed process
    return entries
