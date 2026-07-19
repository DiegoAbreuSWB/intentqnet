"""Trial execution for the predictability-limits study (M9) - a SEPARATE
runner from `planner_study_runner.execute_trial_with_policy` (P01-P02B's
frozen infra, never modified for this phase), for two reasons specific to
M9's questions:

1. **Retry/attempt telemetry.** M9's retry-storm and critical-region
   analyses (sections 5-6 of the governing brief) need `eg_attempts`/
   `ep_attempts`/`es_attempts` (and their `_success` counterparts) per
   trial - `planner_study_runner` never captures these (P01-P02B never
   needed them). Sourced from `assurance.telemetry.collect_intent_evidence`'s
   `source_node_metrics`, exactly as F02/F03's original campaigns did.
2. **Explicit RNG reseeding.** Investigating the ~48723s P02B outlier
   (trial `P02b_resource_aware_planners:four_node:e961642e2e5e233b:L3:7:
   p02b-intent`) found that re-running the *exact same* (topology, route,
   seed, intent) in a fresh process reproduces neither that wall time nor
   even a stable one (isolated reruns: 3.1s, then three consecutive runs
   at ~10.7s, ~11.2s, ~11.2s, ~7.8s) - because `SequenceAdapter` seeds only
   the per-node/per-link `numpy.random.default_rng` generators
   (`network.topology.NetworkTopologySpec.to_router_net_topo_config`);
   SeQUeNCe's `sequence.kernel.quantum_utils` module (a dependency, never
   modified - `random.random()`/`random.uniform()` at its module level,
   see lines ~429-431) draws from Python's GLOBAL `random` module instead,
   which our adapter never reseeds. In a fresh process this module
   auto-seeds from OS entropy on first use (different every run); in a
   long-running campaign process it keeps advancing across every prior
   trial (order-dependent). Neither is reproducible from `operational_
   seed` alone. This runner reseeds Python's global `random` module
   deterministically from `operational_seed` immediately before each
   trial - a composition-layer mitigation (calling SeQUeNCe's own public
   dependency, `random.seed`, from OUR code), not a modification of
   SeQUeNCe's source - so M9's OWN new trials are as reproducible as this
   dependency allows. This does NOT retroactively make P01-P02B
   reproducible (their trials.csv are frozen, unmodified, and this
   caveat is documented as a limitation of those results, not fixed
   there) - see docs/predictability_study.md's "RNG reproducibility
   caveat" section.

Otherwise reuses exactly the same deployment/simulation/assurance pipeline
`planner_study_runner.execute_trial_with_policy` does (`SequenceExecutor`,
`IntentRepository`, `collect_intent_evidence`, `evaluate_intent`) - no
duplicated simulation logic, only telemetry capture and RNG reseeding
differ.
"""
from __future__ import annotations

import random
import sys
import time
from datetime import datetime, timezone

from sequence.constants import SECOND
from sequence.utils import metrics

from ..assurance.evaluator import evaluate_intent
from ..assurance.telemetry import collect_intent_evidence
from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import NetworkTopologySpec
from .predictability_records import PredictabilityTrialRecord
from .records import TrialIdentity

RNG_RESEED_OFFSET = 900_000_000
"""Added to `operational_seed` before reseeding Python's global `random`
module, so M9's reseed values never collide with this project's other
seed-derivation ranges (`INTERNAL_SEED_BASE_OFFSET=500_000_000` for L4's
internal simulations, `RECONCILIATION_SEED_OFFSET=1_000_000`)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def execute_predictability_trial(
    identity: TrialIdentity,
    intent: EntanglementIntent,
    topology_spec: NetworkTopologySpec,
    policy,
    context,
    *,
    project_commit: str | None,
    sequence_commit: str | None,
) -> PredictabilityTrialRecord:
    from ..planning.planners.base import generate_candidate_paths

    metrics.configure()
    capabilities = NetworkCapabilities(topology_spec)
    candidate_paths = generate_candidate_paths(intent, capabilities, context)

    t0 = time.perf_counter()
    decision = policy.plan(intent, capabilities, candidate_paths, context)
    planning_time_s = time.perf_counter() - t0

    attenuation = topology_spec.quantum_links[0].attenuation_db_per_m if topology_spec.quantum_links else None

    def _record(**overrides) -> PredictabilityTrialRecord:
        base = dict(
            campaign=identity.campaign, trial_id=identity.trial_id, scenario=identity.scenario,
            parameter_hash=identity.parameter_hash, seed=identity.seed, intent_id=identity.intent_id,
            planner_level=decision.planner_level, planner_name=decision.planner_name,
            reserved_memory_slots=intent.requirements.reserved_memory_slots,
            min_delivered_pairs=intent.requirements.min_delivered_pairs,
            requested_fidelity=intent.requirements.min_fidelity,
            duration_s=intent.requirements.duration_s, attenuation_db_per_m=attenuation,
            route=" -> ".join(decision.selected_plan.route), hop_count=max(len(decision.selected_plan.route) - 1, 0),
            feasible=decision.feasible, rejection_reason=decision.rejection_reason,
            predicted_satisfaction_probability=decision.predicted_satisfaction_probability,
            predicted_delivered_pairs=decision.predicted_delivered_pairs,
            predicted_average_fidelity=decision.predicted_average_fidelity,
            purification_rounds_estimate=decision.selected_plan.purification_rounds_estimate,
            planning_time_s=round(planning_time_s, 6),
            final_status="REJECTED", satisfied=None, delivered_pairs=None, average_fidelity=None,
            observed_fidelity=None, absolute_fidelity_error=None, simulation_wall_time_s=None,
            timed_out=False, eg_attempts=None, eg_success=None, ep_attempts=None, ep_success=None,
            es_attempts=None, es_success=None,
            project_git_commit=project_commit, sequence_git_commit=sequence_commit,
            python_version=sys.version.split()[0], timestamp=_now_iso(),
        )
        base.update(overrides)
        return PredictabilityTrialRecord(**base)

    if not decision.feasible:
        return _record(final_status="REJECTED")

    # Composition-layer reseed of Python's global `random` module - see
    # the module docstring. `SequenceAdapter`/`RouterNetTopo` still derive
    # their own per-node/per-link numpy generators from `identity.seed`
    # independently; this reseed only affects the SeQUeNCe dependency code
    # that draws from the bare `random` module without going through a
    # node's `get_generator()`.
    random.seed(identity.seed + RNG_RESEED_OFFSET)

    repository = IntentRepository()
    adapter = SequenceAdapter(topology_spec, seed=identity.seed)
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

    record_status = repository.get(intent.id).lifecycle.status
    evidence = collect_intent_evidence(intent)
    telemetry = evidence.source_node_metrics if evidence else {}
    # `collect_trial_metrics` exposes `{prefix}_success`/`{prefix}_failures`
    # (never `{prefix}_attempts` directly) - derived the same way
    # `experiments.runner._native_counter_metrics` already does for
    # F01-F08 (reused convention, not re-invented).
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
            **telemetry_fields,
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
        **telemetry_fields,
    )
