"""M10.8: tail-event study trial execution - wraps
`predictability_m10_runner.execute_predictability_m10_trial`'s exact
pipeline with `heartbeat_monitor.HeartbeatMonitor` around the outer
deployment's `executor.run()` call, and classifies the result via
`heartbeat_monitor.classify_termination` (TIMEOUT/NO_PROGRESS/
MAX_RETRIES/SIMULATION_COMPLETE/ERROR - section 13's exact vocabulary).

A SEPARATE runner from `execute_predictability_m10_trial` (not a
modification of it) because heartbeat instrumentation adds real overhead
(a background thread + disk writes every `interval_s`) that every other
M10 campaign should not pay for a question specific to this one study.
"""
from __future__ import annotations

import time
from pathlib import Path

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
from .heartbeat_monitor import HeartbeatMonitor, classify_termination, read_heartbeats
from .predictability_m10_records import PredictabilityM10TrialRecord, compute_trajectory_hash
from .records import TrialIdentity


def execute_tail_event_trial(
    identity: TrialIdentity,
    intent: EntanglementIntent,
    topology_spec: NetworkTopologySpec,
    policy,
    context,
    *,
    env: EnvironmentInfo,
    determinism: DeterminismConfig,
    heartbeat_path: str | Path,
    heartbeat_interval_s: float = 2.0,
    max_events: int | None = None,
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
    decision = policy.plan(intent, capabilities, candidate_paths, context)
    planning_time_s = time.perf_counter() - t0
    attenuation = topology_spec.quantum_links[0].attenuation_db_per_m if topology_spec.quantum_links else None

    def _base_fields(**overrides) -> dict:
        base = dict(
            campaign=identity.campaign, trial_id=f"{identity.trial_id}:0", scenario=identity.scenario,
            parameter_hash=identity.parameter_hash, seed=identity.seed, intent_id=identity.intent_id,
            planner_level=decision.planner_level, planner_name=decision.planner_name, replay_index=0,
            reserved_memory_slots=intent.requirements.reserved_memory_slots,
            min_delivered_pairs=intent.requirements.min_delivered_pairs,
            requested_fidelity=intent.requirements.min_fidelity, duration_s=intent.requirements.duration_s,
            attenuation_db_per_m=attenuation, distance_m=None, allow_purification=intent.policy.allow_purification,
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
            hostname=rng_manifest.hostname, timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            termination_reason=None, heartbeat_final_sim_time_s=None, heartbeat_final_run_counter=None,
            heartbeat_n_samples=None,
        )
        base.update(overrides)
        return base

    if not decision.feasible:
        fields = _base_fields(final_status="REJECTED", termination_reason="SIMULATION_COMPLETE")
        return PredictabilityM10TrialRecord(**fields)

    repository = IntentRepository()
    adapter = SequenceAdapter(topology_spec, seed=effective_seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, decision.selected_plan)
    timeline = adapter.get_timeline()

    t0 = time.perf_counter()
    exc: Exception | None = None
    try:
        with HeartbeatMonitor(timeline, heartbeat_path, interval_s=heartbeat_interval_s, max_events=max_events):
            executor.run()
    except Exception as e:  # noqa: BLE001
        exc = e
    simulation_wall_time_s = time.perf_counter() - t0

    heartbeats = read_heartbeats(heartbeat_path)
    heartbeat_summary = dict(
        heartbeat_final_sim_time_s=heartbeats[-1]["sim_time_s"] if heartbeats else None,
        heartbeat_final_run_counter=heartbeats[-1]["run_counter"] if heartbeats else None,
        heartbeat_n_samples=len(heartbeats),
    )

    if exc is not None:
        final_status = "SIMULATION_ERROR"
        termination_reason = classify_termination(heartbeat_path, final_status=final_status, timed_out=False)
        fields = _base_fields(
            final_status=final_status, rejection_reason=f"{type(exc).__name__}: {exc}",
            simulation_wall_time_s=round(simulation_wall_time_s, 6), termination_reason=termination_reason,
            **heartbeat_summary,
        )
        return PredictabilityM10TrialRecord(**fields)

    timeline_end_time_s = timeline.now() / SECOND
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
        final_status = record_status.value
        termination_reason = classify_termination(heartbeat_path, final_status=final_status, timed_out=False)
        fields = _base_fields(
            final_status=final_status, simulation_wall_time_s=round(simulation_wall_time_s, 6),
            timeline_end_time_s=timeline_end_time_s, termination_reason=termination_reason,
            **telemetry_fields, **heartbeat_summary,
        )
        return PredictabilityM10TrialRecord(**fields)

    evaluation = evaluate_intent(intent, evidence)
    final_status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
    reason = "all success conditions met" if evaluation.satisfied else "; ".join(evaluation.violations)
    repository.transition(intent.id, final_status, reason, sim_time=timeline.now() / SECOND)

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
    trajectory_hash = compute_trajectory_hash(
        final_status=final_status.value, delivered_pairs=delivered_pairs, average_fidelity=average_fidelity,
        route=" -> ".join(decision.selected_plan.route), eg_attempts=telemetry_fields.get("eg_attempts"),
        eg_success=telemetry_fields.get("eg_success"), ep_attempts=telemetry_fields.get("ep_attempts"),
        ep_success=telemetry_fields.get("ep_success"), es_attempts=telemetry_fields.get("es_attempts"),
        es_success=telemetry_fields.get("es_success"), timeline_end_time_s=timeline_end_time_s,
    )
    termination_reason = classify_termination(heartbeat_path, final_status=final_status.value, timed_out=False)
    fields = _base_fields(
        final_status=final_status.value, satisfied=evaluation.satisfied, delivered_pairs=delivered_pairs,
        average_fidelity=average_fidelity, observed_fidelity=average_fidelity,
        absolute_fidelity_error=absolute_error, simulation_wall_time_s=round(simulation_wall_time_s, 6),
        timeline_end_time_s=timeline_end_time_s, trajectory_hash=trajectory_hash,
        termination_reason=termination_reason, **telemetry_fields, **heartbeat_summary,
    )
    return PredictabilityM10TrialRecord(**fields)
