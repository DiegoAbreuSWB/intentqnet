"""Runs a parameter-grid campaign entirely in-memory - no YAML scenario/
campaign files on disk (Fase J10's F02/F03/F07/F08 final campaigns use
topologies from `experiments.topology_catalog`/`demos.topologies`
directly, not checked-in scenario fixtures).

Deliberately a thin, separate entry point rather than a refactor of
`CampaignRunner.run()`: that method is heavily tested against real YAML
campaign files (`tests/experiments/test_*.py`), and this project's own
rule is to prefer a small, clearly-documented amount of duplication over
risking a core, well-tested module for a variant only this phase needs.
Every building block reused here (`execute_trial`, `TrialIdentity`,
`expand_parameter_grid`, `apply_parameters`, `append_trial_record`,
manifest functions) is the exact same one `CampaignRunner` uses - only
the "where do topology/intents come from" step differs.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..demos.environment import collect_environment_info
from ..intent.models import EntanglementIntent
from ..network.topology import NetworkTopologySpec
from ..utils.logging import get_logger
from .manifests import _now_iso, manifest_path, read_manifest, update_manifest_progress, write_manifest
from .persistence import append_error_record, append_trial_record, errors_jsonl_path, read_trial_ids, trials_csv_path
from .records import TrialIdentity
from .runner import CampaignRunSummary, execute_trial
from .sweeps import apply_parameters, compute_parameter_hash, expand_parameter_grid

logger = get_logger(__name__)


def run_programmatic_campaign(
    *,
    campaign_name: str,
    scenario_name: str,
    base_topology: NetworkTopologySpec,
    base_intents: list[EntanglementIntent],
    parameter_grid: dict,
    seeds: list[int],
    output_directory: str | Path,
    routing_strategy_name: str = "shortest_hop_count",
    purification_policy_name: str = "automatic",
    reconciliation_enabled: bool = False,
    fidelity_estimator_name: str = "conservative_min",
    continue_on_error: bool = True,
) -> CampaignRunSummary:
    """Same trial-generation/execution/persistence logic as
    `CampaignRunner.run()`, but `base_topology`/`base_intents` are passed
    directly instead of loaded from a `CampaignSpec`'s YAML file paths."""
    start = time.perf_counter()
    combinations = expand_parameter_grid(parameter_grid)
    expected_trials = len(combinations) * len(seeds) * len(base_intents)

    trials_path = trials_csv_path(output_directory, campaign_name)
    errors_path = errors_jsonl_path(output_directory, campaign_name)
    manifest_file = manifest_path(output_directory, campaign_name)

    known_trial_ids = read_trial_ids(trials_path)

    if read_manifest(manifest_file) is None:
        env = collect_environment_info()
        write_manifest(manifest_file, {
            "campaign": campaign_name, "description": f"Fase J10 final campaign: {campaign_name}",
            "created_at": _now_iso(), "updated_at": _now_iso(),
            "project_git_commit": env.project_commit, "sequence_git_commit": env.sequence_commit,
            "python_version": env.python_version, "platform": env.platform, "dependencies": env.dependency_versions,
            "campaign_file": None, "scenario_files": [scenario_name], "intent_files": [i.id for i in base_intents],
            "parameter_grid": parameter_grid, "strategies": {
                "routing": [routing_strategy_name], "purification": [purification_policy_name],
                "fidelity_estimator": [fidelity_estimator_name],
            },
            "seeds": seeds, "expected_trials": expected_trials,
            "completed_trials": 0, "skipped_trials": 0, "failed_trials": 0, "output_files": [],
        })

    env = collect_environment_info()
    skipped_trials = 0
    completed_trials = 0
    failed_trials = 0

    for combination in combinations:
        parameter_hash = compute_parameter_hash(combination)
        for base_intent in base_intents:
            params = apply_parameters(
                base_topology, base_intent, combination,
                routing_strategy_name=routing_strategy_name, purification_policy_name=purification_policy_name,
                reconciliation_enabled=reconciliation_enabled, fidelity_estimator_name=fidelity_estimator_name,
            )
            for seed in seeds:
                identity = TrialIdentity(
                    campaign=campaign_name, scenario=scenario_name, parameter_hash=parameter_hash,
                    strategy=f"{params.routing_strategy_name}__{params.purification_policy_name}__{params.fidelity_estimator_name}",
                    seed=seed, intent_id=base_intent.id,
                )
                if identity.trial_id in known_trial_ids:
                    skipped_trials += 1
                    continue

                try:
                    record = execute_trial(identity, params, project_commit=env.project_commit, sequence_commit=env.sequence_commit)
                except Exception as exc:
                    failed_trials += 1
                    logger.warning("trial %s failed: %s: %s", identity.trial_id, type(exc).__name__, exc)
                    append_error_record(
                        errors_path, trial_id=identity.trial_id, campaign=campaign_name, scenario=scenario_name,
                        parameter_hash=parameter_hash, strategy=identity.strategy, seed=seed, intent_id=base_intent.id,
                        error_type=type(exc).__name__, error_message=str(exc), timestamp=_now_iso(),
                    )
                    update_manifest_progress(
                        manifest_file, completed_trials=completed_trials, skipped_trials=skipped_trials,
                        failed_trials=failed_trials, output_files=[str(trials_path), str(errors_path)],
                    )
                    if not continue_on_error:
                        return CampaignRunSummary(
                            campaign=campaign_name, expected_trials=expected_trials, completed_trials=completed_trials,
                            skipped_trials=skipped_trials, failed_trials=failed_trials,
                            duration_s=time.perf_counter() - start,
                            output_files=[str(trials_path), str(errors_path), str(manifest_file)],
                        )
                    continue

                append_trial_record(trials_path, record, known_trial_ids=known_trial_ids)
                completed_trials += 1
                update_manifest_progress(
                    manifest_file, completed_trials=completed_trials, skipped_trials=skipped_trials,
                    failed_trials=failed_trials, output_files=[str(trials_path), str(errors_path)],
                )

    return CampaignRunSummary(
        campaign=campaign_name, expected_trials=expected_trials, completed_trials=completed_trials,
        skipped_trials=skipped_trials, failed_trials=failed_trials, duration_s=time.perf_counter() - start,
        output_files=[str(trials_path), str(errors_path), str(manifest_file)],
    )
