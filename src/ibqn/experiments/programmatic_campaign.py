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

**Multi-block manifests** (Fase K1): a single logical campaign is often
executed as more than one call to `run_programmatic_campaign` under the
same `campaign_name` - one call per topology/scenario (e.g. F02's
`diamond_heterogeneous` then `small_mesh`). Found empirically (Fase K1
audit) that the original manifest writer only wrote the manifest once,
on the very first call, and every subsequent call's progress updates
overwrote (rather than accumulated onto) `completed_trials` - so a
two-scenario campaign's manifest silently reported only the LAST
scenario's own trial count and topology, while `trials.csv` correctly
held every trial from every call. The manifest now tracks one `blocks`
entry per `scenario_name` ever passed for this `campaign_name`, and the
top-level `scenario_files`/`expected_trials`/`completed_trials`/
`skipped_trials`/`failed_trials`/`intent_files`/`seeds` fields are always
recomputed as the union/sum across all blocks - correct regardless of
how many calls (or processes/sessions) contributed to the campaign.

Each block also replaces the old, ambiguous `strategies: {routing:
[...]}` field (which held only this call's kwarg *default* even when
that same dimension was actually being swept via `parameter_grid`, self-
contradicting it) with an explicit `base_configuration` (the strategy
kwargs that are NOT swept in this block, i.e. genuinely fixed) and
`swept_factors` (exactly `parameter_grid`, the dimensions that vary).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..demos.environment import collect_environment_info
from ..intent.models import EntanglementIntent
from ..network.topology import NetworkTopologySpec
from ..utils.logging import get_logger
from .manifests import _now_iso, manifest_path, read_manifest, write_manifest
from .parallel import TrialJob, execute_jobs
from .persistence import append_error_record, append_trial_record, errors_jsonl_path, read_trial_ids, trials_csv_path
from .records import TrialIdentity
from .runner import CampaignRunSummary
from .sweeps import apply_parameters, compute_parameter_hash, expand_parameter_grid

logger = get_logger(__name__)


def _upsert_campaign_manifest_block(
    manifest_file: Path,
    *,
    campaign_name: str,
    scenario_name: str,
    intent_files: list[str],
    base_configuration: dict[str, Any],
    swept_factors: dict[str, Any],
    seeds: list[int],
    completed_trials: int,
    failed_trials: int,
    output_files: list[str],
) -> dict[str, Any]:
    """Creates or updates this `scenario_name`'s block within the
    campaign's manifest, then recomputes every top-level rolled-up field
    from the full set of blocks - see the module docstring.

    `skipped_trials` is deliberately NOT a parameter: it is *derived* as
    `expected_trials - completed_trials - failed_trials` for the block
    (never negative), so `expected == completed + failed + skipped`
    holds by construction instead of by convention. A session-local
    "trials skipped because already known" counter would double-count
    against `completed_trials` (which is itself ground truth from
    trials.csv, so it already includes trials completed in an earlier
    session) - found while auditing this exact double-count (Fase K1).

    A call for a `scenario_name` that already has a block MERGES
    `swept_factors` (union of values per key) and `seeds`/`intent_files`
    into the existing block instead of overwriting them, and
    `expected_trials` is recomputed from the merged grid - not just
    this call's own `expected_trials` - so a later call that only adds
    a few new grid values to an existing scenario (e.g. denser
    thresholds in part of an existing range) correctly extends the
    block instead of shrinking its recorded scope down to just the new
    values (found while designing F03's purification-density
    supplementary campaign, Fase K2)."""
    manifest = read_manifest(manifest_file)
    if manifest is None:
        env = collect_environment_info()
        manifest = {
            "campaign": campaign_name, "description": f"Fase J10 final campaign: {campaign_name}",
            "created_at": _now_iso(),
            "project_git_commit": env.project_commit, "sequence_git_commit": env.sequence_commit,
            "python_version": env.python_version, "platform": env.platform, "dependencies": env.dependency_versions,
            "campaign_file": None, "blocks": [],
        }

    manifest["updated_at"] = _now_iso()
    blocks: list[dict[str, Any]] = manifest.setdefault("blocks", [])
    block = next((b for b in blocks if b["scenario"] == scenario_name), None)
    if block is None:
        block = {"scenario": scenario_name, "intent_files": [], "swept_factors": {}, "seeds": []}
        blocks.append(block)

    merged_intent_files = sorted(set(block["intent_files"]) | set(intent_files))
    merged_seeds = sorted(set(block["seeds"]) | set(seeds))
    merged_swept_factors = {
        key: sorted(set(block["swept_factors"].get(key, [])) | set(swept_factors.get(key, [])))
        for key in set(block["swept_factors"]) | set(swept_factors)
    }
    merged_expected_trials = (
        len(expand_parameter_grid(merged_swept_factors)) * len(merged_seeds) * len(merged_intent_files)
    )

    block.update({
        "intent_files": merged_intent_files, "base_configuration": base_configuration,
        "swept_factors": merged_swept_factors, "seeds": merged_seeds, "expected_trials": merged_expected_trials,
        "completed_trials": completed_trials,
        "skipped_trials": max(0, merged_expected_trials - completed_trials - failed_trials), "failed_trials": failed_trials,
    })
    blocks.sort(key=lambda b: b["scenario"])

    manifest["scenario_files"] = [b["scenario"] for b in blocks]
    manifest["intent_files"] = sorted({name for b in blocks for name in b["intent_files"]})
    manifest["seeds"] = sorted({seed for b in blocks for seed in b["seeds"]})
    manifest["expected_trials"] = sum(b["expected_trials"] for b in blocks)
    manifest["completed_trials"] = sum(b["completed_trials"] for b in blocks)
    manifest["skipped_trials"] = sum(b["skipped_trials"] for b in blocks)
    manifest["failed_trials"] = sum(b["failed_trials"] for b in blocks)
    manifest["output_files"] = output_files
    write_manifest(manifest_file, manifest)
    return manifest


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
    workers: int = 1,
) -> CampaignRunSummary:
    """Same trial-generation/execution/persistence logic as
    `CampaignRunner.run()`, but `base_topology`/`base_intents` are passed
    directly instead of loaded from a `CampaignSpec`'s YAML file paths.

    The manifest tracks this call's `scenario_name` as its own block (see
    the module docstring) - safe to call more than once with the same
    `campaign_name` and a different `scenario_name`/`base_topology`/
    `base_intents` (e.g. one call per topology in a multi-topology final
    campaign); each call's own trial counts are correctly folded into the
    manifest's rolled-up totals instead of overwriting them.

    `workers > 1` runs the pending trials in that many worker processes
    (`experiments.parallel`); results are identical trial for trial, only
    the row order in `trials.csv` differs."""
    start = time.perf_counter()
    combinations = expand_parameter_grid(parameter_grid)
    expected_trials = len(combinations) * len(seeds) * len(base_intents)

    strategy_kwargs = {
        "routing_strategy": routing_strategy_name, "purification_policy": purification_policy_name,
        "fidelity_estimator": fidelity_estimator_name, "reconciliation_enabled": reconciliation_enabled,
    }
    base_configuration = {name: value for name, value in strategy_kwargs.items() if name not in parameter_grid}
    swept_factors = dict(parameter_grid)
    intent_files = [i.id for i in base_intents]

    trials_path = trials_csv_path(output_directory, campaign_name)
    errors_path = errors_jsonl_path(output_directory, campaign_name)
    manifest_file = manifest_path(output_directory, campaign_name)

    known_trial_ids = read_trial_ids(trials_path)
    block_prefix = f"{campaign_name}:{scenario_name}:"

    def count_completed() -> int:
        # Ground truth from trials.csv, not a session-local counter: a
        # trial completed in an earlier call/session (and therefore
        # already in known_trial_ids when this call started) must still
        # count as completed here - found necessary while regenerating
        # F02/F03's manifests (Fase K1), where a "replay" call over
        # already-persisted trials would otherwise report 0 completed.
        return sum(1 for trial_id in known_trial_ids if trial_id.startswith(block_prefix))

    def upsert_manifest(*, failed_trials: int) -> None:
        _upsert_campaign_manifest_block(
            manifest_file, campaign_name=campaign_name, scenario_name=scenario_name,
            intent_files=intent_files, base_configuration=base_configuration, swept_factors=swept_factors,
            seeds=seeds, completed_trials=count_completed(),
            failed_trials=failed_trials, output_files=[str(trials_path), str(errors_path)],
        )

    upsert_manifest(failed_trials=0)

    env = collect_environment_info()
    skipped_trials = 0
    completed_trials = 0
    failed_trials = 0

    pending: list[TrialJob] = []
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
                pending.append(TrialJob(identity, params, env.project_commit, env.sequence_commit))

    # `workers <= 1` executes the jobs inline and in order (the original
    # sequential behavior); more workers run them in separate processes and
    # deliver results in completion order - see experiments.parallel.
    outcomes = execute_jobs(pending, workers=workers)
    try:
        for job, outcome in outcomes:
            identity = job.identity
            if outcome.failed:
                failed_trials += 1
                logger.warning("trial %s failed: %s: %s", identity.trial_id, outcome.error_type, outcome.error_message)
                append_error_record(
                    errors_path, trial_id=identity.trial_id, campaign=campaign_name, scenario=scenario_name,
                    parameter_hash=identity.parameter_hash, strategy=identity.strategy, seed=identity.seed,
                    intent_id=identity.intent_id,
                    error_type=outcome.error_type, error_message=outcome.error_message, timestamp=_now_iso(),
                )
                upsert_manifest(failed_trials=failed_trials)
                if not continue_on_error:
                    return CampaignRunSummary(
                        campaign=campaign_name, expected_trials=expected_trials, completed_trials=completed_trials,
                        skipped_trials=skipped_trials, failed_trials=failed_trials,
                        duration_s=time.perf_counter() - start,
                        output_files=[str(trials_path), str(errors_path), str(manifest_file)],
                    )
                continue

            append_trial_record(trials_path, outcome.record, known_trial_ids=known_trial_ids)
            completed_trials += 1
            upsert_manifest(failed_trials=failed_trials)
    finally:
        outcomes.close()

    # Unconditional final upsert so the manifest reflects the fully
    # up-to-date ground truth even if the loop's last action was neither
    # a success nor a failure (e.g. every remaining combination was
    # already known).
    upsert_manifest(failed_trials=failed_trials)

    return CampaignRunSummary(
        campaign=campaign_name, expected_trials=expected_trials, completed_trials=completed_trials,
        skipped_trials=skipped_trials, failed_trials=failed_trials, duration_s=time.perf_counter() - start,
        output_files=[str(trials_path), str(errors_path), str(manifest_file)],
    )
