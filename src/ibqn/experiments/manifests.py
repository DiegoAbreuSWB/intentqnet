"""Per-campaign manifest: metadata + live progress, updated incrementally
during a run (Fase H3, see docs/campaign_architecture.md, section 14 and
the project brief's manifest schema).

Written atomically (temp file + `os.replace`) so a manifest read mid-write
is never a half-written JSON document - unlike `trials.csv`/`errors.jsonl`
(safe append), the manifest is a single small JSON object rewritten in
full on every update.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..demos.environment import collect_environment_info
from .campaigns import CampaignSpec


def manifest_path(output_directory: str | Path, campaign: str) -> Path:
    return Path(output_directory) / "manifests" / f"{campaign}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_initial_manifest(spec: CampaignSpec, *, campaign_file: str | Path, expected_trials: int) -> dict[str, Any]:
    now = _now_iso()
    env = collect_environment_info()
    return {
        "campaign": spec.name,
        "description": spec.description,
        "created_at": now,
        "updated_at": now,
        "project_git_commit": env.project_commit,
        "sequence_git_commit": env.sequence_commit,
        "python_version": env.python_version,
        "platform": env.platform,
        "dependencies": env.dependency_versions,
        "campaign_file": str(campaign_file),
        "scenario_files": [spec.scenario_file],
        "intent_files": list(spec.intents),
        "parameter_grid": spec.effective_parameter_grid(),
        "strategies": spec.strategies,
        "seeds": list(spec.seeds),
        "expected_trials": expected_trials,
        "completed_trials": 0,
        "skipped_trials": 0,
        "failed_trials": 0,
        "output_files": [],
    }


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    manifest_file = Path(path)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = manifest_file.with_suffix(manifest_file.suffix + ".tmp")
    tmp_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.replace(tmp_file, manifest_file)


def read_manifest(path: str | Path) -> dict[str, Any] | None:
    manifest_file = Path(path)
    if not manifest_file.exists():
        return None
    return json.loads(manifest_file.read_text(encoding="utf-8"))


def update_manifest_progress(
    path: str | Path,
    *,
    completed_trials: int,
    skipped_trials: int,
    failed_trials: int,
    output_files: list[str],
) -> dict[str, Any]:
    manifest = read_manifest(path)
    if manifest is None:
        raise FileNotFoundError(f"no manifest at {path} to update - call build_initial_manifest/write_manifest first")
    manifest["updated_at"] = _now_iso()
    manifest["completed_trials"] = completed_trials
    manifest["skipped_trials"] = skipped_trials
    manifest["failed_trials"] = failed_trials
    manifest["output_files"] = output_files
    write_manifest(path, manifest)
    return manifest
