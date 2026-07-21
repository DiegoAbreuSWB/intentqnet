"""Trial execution for the M10 robust-predictability-validation phase -
SEPARATE from `planner_study_runner` (P01-P02B, frozen) and
`predictability_runner` (M9, frozen). Adds:

1. Optional `DeterministicExecutionContext` application
   (`deterministic_context.apply_determinism`) - a no-op unless the
   campaign's own config explicitly enables it (`determinism.enabled:
   true`), never applied retroactively to any existing campaign.
2. Full environment/dependency-version provenance (reuses
   `demos.environment.collect_environment_info` - not re-derived).
3. `trajectory_hash` computation (wall-clock-free logical-outcome
   fingerprint - see `predictability_m10_records.compute_trajectory_hash`).

Otherwise reuses the exact same deployment/simulation/assurance pipeline
every other runner in this project uses (`SequenceExecutor`,
`IntentRepository`, `collect_intent_evidence`, `evaluate_intent`).
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from sequence.constants import SECOND
from sequence.utils import metrics

from ..assurance.evaluator import evaluate_intent
from ..assurance.telemetry import collect_intent_evidence
from ..demos.environment import EnvironmentInfo
from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import NetworkTopologySpec
from .deterministic_context import DeterminismConfig, apply_determinism
from .predictability_m10_records import PredictabilityM10TrialRecord, compute_trajectory_hash
from .records import TrialIdentity


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_predictability_m10_trial(
    identity: TrialIdentity,
    intent: EntanglementIntent,
    topology_spec: NetworkTopologySpec,
    policy,
    context,
    *,
    env: EnvironmentInfo,
    determinism: DeterminismConfig,
    replay_index: int = 0,
    distance_m: float | None = None,
) -> PredictabilityM10TrialRecord:
    import json

    from ..planning.planners.base import generate_candidate_paths

    execution_seed, rng_manifest = apply_determinism(
        campaign_id=identity.campaign, trial_id=identity.trial_id, config=determinism,
        project_commit=env.project_commit, sequence_commit=env.sequence_commit,
    )
    effective_seed = execution_seed if execution_seed is not None else identity.seed

    metrics.configure()
    capabilities = NetworkCapabilities(topology_spec)
    candidate_paths = generate_candidate_paths(intent, capabilities, context)

    t0 = time.perf_counter()
    try:
        decision = policy.plan(intent, capabilities, candidate_paths, context)
    except Exception as exc:  # noqa: BLE001
        # L4's planning step runs REAL internal simulations
        # (planning.planners.l4_simulation.run_internal_simulations) - it
        # can hit the same genuine SeQUeNCe protocol assertions the outer
        # deployment can (e.g. BBPSSW's `kept_memo.fidelity > 0.5` check,
        # first found in P02B's real deployment, M6e) - but planning
        # itself was never wrapped, because L1-L3-R's purely analytical
        # planning never raises. Found exercising L4 for the first time
        # in M10 (P13, small_mesh at a low-fidelity boundary
        # configuration). Recorded as SIMULATION_ERROR (same convention
        # as the outer deployment's own exception handling) rather than
        # crashing the whole campaign - never modifies L4's own frozen code.
        planning_time_s = time.perf_counter() - t0
        return PredictabilityM10TrialRecord(
            campaign=identity.campaign, trial_id=f"{identity.trial_id}:{replay_index}", scenario=identity.scenario,
            parameter_hash=identity.parameter_hash, seed=identity.seed, intent_id=identity.intent_id,
            planner_level=getattr(policy, "level", "unknown"), planner_name=getattr(policy, "name", "unknown"),
            replay_index=replay_index, reserved_memory_slots=intent.requirements.reserved_memory_slots,
            min_delivered_pairs=intent.requirements.min_delivered_pairs,
            requested_fidelity=intent.requirements.min_fidelity, duration_s=intent.requirements.duration_s,
            attenuation_db_per_m=(topology_spec.quantum_links[0].attenuation_db_per_m if topology_spec.quantum_links else None),
            distance_m=distance_m, allow_purification=intent.policy.allow_purification,
            route="", hop_count=None, feasible=False, rejection_reason=f"{type(exc).__name__}: {exc}",
            predicted_satisfaction_probability=None, predicted_delivered_pairs=None,
            predicted_average_fidelity=None, purification_rounds_estimate=None,
            planning_time_s=round(planning_time_s, 6), final_status="SIMULATION_ERROR", satisfied=None,
            delivered_pairs=None, average_fidelity=None, observed_fidelity=None, absolute_fidelity_error=None,
            simulation_wall_time_s=None, timed_out=False, timeout_s=None,
            eg_attempts=None, eg_success=None, ep_attempts=None, ep_success=None, es_attempts=None, es_success=None,
            timeline_end_time_s=None, trajectory_hash=None,
            determinism_enabled=rng_manifest.determinism_enabled, master_seed=rng_manifest.master_seed,
            execution_seed_used=rng_manifest.execution_seed_used_by_sequence_adapter,
            namespace_seeds_json=json.dumps(rng_manifest.namespace_seeds) if rng_manifest.namespace_seeds else None,
            python_random_reseeded=rng_manifest.python_random_reseeded,
            python_hash_seed_env_value=rng_manifest.python_hash_seed_env_value,
            project_git_commit=env.project_commit, sequence_git_commit=env.sequence_commit,
            python_version=env.python_version, numpy_version=env.dependency_versions.get("numpy", "unknown"),
            dependency_versions_json=json.dumps(env.dependency_versions),
            platform_system=rng_manifest.platform_system, platform_release=rng_manifest.platform_release,
            hostname=rng_manifest.hostname, timestamp=_now_iso(),
        )
    planning_time_s = time.perf_counter() - t0

    attenuation = topology_spec.quantum_links[0].attenuation_db_per_m if topology_spec.quantum_links else None

    def _record(**overrides) -> PredictabilityM10TrialRecord:
        base = dict(
            campaign=identity.campaign, trial_id=f"{identity.trial_id}:{replay_index}", scenario=identity.scenario,
            parameter_hash=identity.parameter_hash, seed=identity.seed, intent_id=identity.intent_id,
            planner_level=decision.planner_level, planner_name=decision.planner_name, replay_index=replay_index,
            reserved_memory_slots=intent.requirements.reserved_memory_slots,
            min_delivered_pairs=intent.requirements.min_delivered_pairs,
            requested_fidelity=intent.requirements.min_fidelity,
            duration_s=intent.requirements.duration_s, attenuation_db_per_m=attenuation, distance_m=distance_m,
            allow_purification=intent.policy.allow_purification,
            route=" -> ".join(decision.selected_plan.route), hop_count=max(len(decision.selected_plan.route) - 1, 0),
            feasible=decision.feasible, rejection_reason=decision.rejection_reason,
            predicted_satisfaction_probability=decision.predicted_satisfaction_probability,
            predicted_delivered_pairs=decision.predicted_delivered_pairs,
            predicted_average_fidelity=decision.predicted_average_fidelity,
            purification_rounds_estimate=decision.selected_plan.purification_rounds_estimate,
            planning_time_s=round(planning_time_s, 6),
            final_status="REJECTED", satisfied=None, delivered_pairs=None, average_fidelity=None,
            observed_fidelity=None, absolute_fidelity_error=None, simulation_wall_time_s=None,
            timed_out=False, timeout_s=None,
            eg_attempts=None, eg_success=None, ep_attempts=None, ep_success=None, es_attempts=None, es_success=None,
            timeline_end_time_s=None, trajectory_hash=None,
            determinism_enabled=rng_manifest.determinism_enabled, master_seed=rng_manifest.master_seed,
            execution_seed_used=rng_manifest.execution_seed_used_by_sequence_adapter,
            namespace_seeds_json=json.dumps(rng_manifest.namespace_seeds) if rng_manifest.namespace_seeds else None,
            python_random_reseeded=rng_manifest.python_random_reseeded,
            python_hash_seed_env_value=rng_manifest.python_hash_seed_env_value,
            project_git_commit=env.project_commit, sequence_git_commit=env.sequence_commit,
            python_version=env.python_version, numpy_version=env.dependency_versions.get("numpy", "unknown"),
            dependency_versions_json=json.dumps(env.dependency_versions),
            platform_system=rng_manifest.platform_system, platform_release=rng_manifest.platform_release,
            hostname=rng_manifest.hostname, timestamp=_now_iso(),
        )
        base.update(overrides)
        if base["final_status"] in ("SATISFIED", "VIOLATED"):
            base["trajectory_hash"] = compute_trajectory_hash(
                final_status=base["final_status"], delivered_pairs=base["delivered_pairs"],
                average_fidelity=base["average_fidelity"], route=base["route"],
                eg_attempts=base["eg_attempts"], eg_success=base["eg_success"],
                ep_attempts=base["ep_attempts"], ep_success=base["ep_success"],
                es_attempts=base["es_attempts"], es_success=base["es_success"],
                timeline_end_time_s=base["timeline_end_time_s"],
            )
        return PredictabilityM10TrialRecord(**base)

    if not decision.feasible:
        return _record(final_status="REJECTED")

    repository = IntentRepository()
    adapter = SequenceAdapter(topology_spec, seed=effective_seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, decision.selected_plan)

    t0 = time.perf_counter()
    try:
        executor.run()
    except Exception as exc:  # noqa: BLE001
        simulation_wall_time_s = time.perf_counter() - t0
        return _record(
            final_status="SIMULATION_ERROR", rejection_reason=f"{type(exc).__name__}: {exc}",
            simulation_wall_time_s=round(simulation_wall_time_s, 6),
        )
    simulation_wall_time_s = time.perf_counter() - t0
    timeline_end_time_s = adapter.get_timeline().now() / SECOND

    record_status = repository.get(intent.id).lifecycle.status
    evidence = collect_intent_evidence(intent)
    telemetry = evidence.source_node_metrics if evidence else {}
    telemetry_fields = {}
    for prefix in ("eg", "ep", "es"):
        success = telemetry.get(f"{prefix}_success")
        failures = telemetry.get(f"{prefix}_failures")
        if success is None or failures is None:
            telemetry_fields[f"{prefix}_attempts"] = None
            telemetry_fields[f"{prefix}_success"] = None
        else:
            telemetry_fields[f"{prefix}_attempts"] = int(success) + int(failures)
            telemetry_fields[f"{prefix}_success"] = int(success)

    if record_status != IntentStatus.ACTIVE:
        return _record(
            final_status=record_status.value, simulation_wall_time_s=round(simulation_wall_time_s, 6),
            timeline_end_time_s=timeline_end_time_s, **telemetry_fields,
        )

    evaluation = evaluate_intent(intent, evidence)
    final_status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
    reason = "all success conditions met" if evaluation.satisfied else "; ".join(evaluation.violations)
    repository.transition(intent.id, final_status, reason, sim_time=adapter.get_timeline().now() / SECOND)

    delivered_pairs = len(evidence.delivered_pairs) if evidence else 0
    average_fidelity = (
        sum(p.fidelity for p in evidence.delivered_pairs) / delivered_pairs
        if evidence and delivered_pairs else None
    )
    estimated_fidelity = decision.predicted_average_fidelity
    absolute_error = (
        average_fidelity - estimated_fidelity if average_fidelity is not None and estimated_fidelity is not None
        else None
    )

    return _record(
        final_status=final_status.value, satisfied=evaluation.satisfied, delivered_pairs=delivered_pairs,
        average_fidelity=average_fidelity, observed_fidelity=average_fidelity,
        absolute_fidelity_error=absolute_error, simulation_wall_time_s=round(simulation_wall_time_s, 6),
        timeline_end_time_s=timeline_end_time_s, **telemetry_fields,
    )
