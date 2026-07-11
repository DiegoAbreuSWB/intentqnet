"""Campaign progress reporting for the `status`/`plan` CLI commands (Fase
H3) - read-only: never runs a trial, only inspects `trials.csv`/
`errors.jsonl`/the manifest already on disk.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .campaigns import CampaignSpec
from .manifests import manifest_path, read_manifest
from .persistence import errors_jsonl_path, read_errors, read_trial_ids, trials_csv_path
from .sweeps import expand_parameter_grid


@dataclass(frozen=True)
class CampaignStatus:
    campaign: str
    expected_trials: int
    completed_trials: int
    failed_trials: int
    remaining_trials: int
    manifest: dict[str, Any] | None


def expected_trial_count(spec: CampaignSpec, *, campaign_file: str | Path) -> int:
    """`campaign_file` is accepted for interface symmetry with
    `compute_campaign_status`/the CLI, even though only `spec`'s own
    fields (already validated to reference real files by
    `campaigns.load_campaign_file`) are needed for this count."""
    n_intents = len(spec.intents)
    n_combinations = len(expand_parameter_grid(spec.effective_parameter_grid()))
    return n_combinations * len(spec.seeds) * n_intents


def compute_campaign_status(spec: CampaignSpec, *, campaign_file: str | Path) -> CampaignStatus:
    expected = expected_trial_count(spec, campaign_file=campaign_file)
    completed = len(read_trial_ids(trials_csv_path(spec.output_directory, spec.name)))
    failed = len(read_errors(errors_jsonl_path(spec.output_directory, spec.name)))
    manifest = read_manifest(manifest_path(spec.output_directory, spec.name))
    return CampaignStatus(
        campaign=spec.name, expected_trials=expected, completed_trials=completed,
        failed_trials=failed, remaining_trials=max(0, expected - completed), manifest=manifest,
    )
