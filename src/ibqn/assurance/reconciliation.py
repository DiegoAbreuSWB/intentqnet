"""Reconciliation between episodes (see docs/sequence_code_analysis.md,
section 4.7: SeQUeNCe does not support rerouting an already-active
reservation, and docs/assurance_design.md, section 10).

`reconcile()` continues the *same* intent's lifecycle in the *original*
`IntentRepository` (so its history stays intact across the attempt), but
runs the retry on a brand-new `SequenceAdapter`/`Timeline` - a new episode,
not a live modification of the failed one.
"""
from __future__ import annotations

from dataclasses import dataclass

from sequence.constants import SECOND
from sequence.utils import metrics

from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import NetworkTopologySpec
from ..planning.fidelity_estimation import LinkFidelityEstimator
from ..planning.models import ExecutionPlan
from ..planning.planner import IntentPlanner
from ..planning.purification import PurificationStrategy
from ..planning.routing import RoutingStrategy
from ..planning.swapping import SwappingStrategy
from ..execution.sequence_executor import SequenceExecutor
from ..utils.logging import get_logger
from .evaluator import IntentEvaluation, evaluate_intent
from .telemetry import collect_intent_evidence
from .violations import Violation, classify_violations

logger = get_logger(__name__)


@dataclass
class ReconciliationResult:
    intent_id: str
    trigger_violations: list[Violation]
    new_plan: ExecutionPlan
    new_evaluation: IntentEvaluation | None
    final_status: IntentStatus


def reconcile(
    intent: EntanglementIntent,
    topology_spec: NetworkTopologySpec,
    repository: IntentRepository,
    trigger_evaluation: IntentEvaluation,
    *,
    seed: int,
    routing_strategy: RoutingStrategy | None = None,
    purification_strategy: PurificationStrategy | None = None,
    swapping_strategy: SwappingStrategy | None = None,
    fidelity_estimator: LinkFidelityEstimator | None = None,
    intent_override: EntanglementIntent | None = None,
) -> ReconciliationResult:
    """Attempts to satisfy `intent` again, on a fresh episode.

    `intent` must already be registered in `repository` with lifecycle
    status `VIOLATED` (the outcome of a prior `evaluate_intent` call,
    `trigger_evaluation`). Builds a brand-new `SequenceAdapter` (new
    `Timeline`, simulation time restarts at 0) over the same `topology_spec`,
    replans (optionally with different strategies), and - if a feasible
    plan exists - deploys and runs it, then evaluates the outcome the
    same way `experiments.runner.run_scenario` does.

    `intent_override` (Fase J6, see
    `assurance.reconciliation_policy.apply_reconciliation_decision`): when
    a `ReconciliationDecision` calls for a duration or reserved-slot
    increase rather than a route change, episode 2 needs to plan/deploy/
    evaluate against a MODIFIED intent (same `id`, different
    `requirements.duration_s`/`reserved_memory_slots`) - `intent_override`
    must share `intent`'s `id` if given; everything downstream (planning,
    deployment, evidence collection, evaluation) uses it instead of
    `intent`, while repository bookkeeping stays keyed by the same `id`.
    Defaults to `None` (use `intent` unchanged), preserving this
    function's exact prior behavior for every existing caller.

    Does not retry more than once: if the new plan is infeasible or the new
    run is still violated, `reconcile` returns that outcome directly rather
    than searching further (see docs/assurance_design.md, section 11).

    Resets `sequence.utils.metrics` before running episode 2 (the same
    process-wide singleton every other independent simulation run in this
    project resets first - see docs/sequence_code_analysis.md, section 4.1,
    and notebook 06 of Fase H1). Without this, `collect_intent_evidence`
    below would still see episode 1's `DELIVERY` records: since a new
    episode's `IntentRequestApp` restarts `pair_number` at 1, a handful of
    episode 1's records collide with episode 2's by `pair_number` and win
    the dedup (they were inserted first) - silently mixing a few stale
    episode-1 pairs into what should be episode 2's evidence only. Found
    empirically while building the Fase H3 campaign runner, which reuses
    this function directly.
    """
    if intent_override is not None and intent_override.id != intent.id:
        raise ValueError(
            f"intent_override.id ({intent_override.id!r}) must match intent.id ({intent.id!r}) - "
            f"reconciliation continues the SAME intent's lifecycle, it never starts a new one"
        )
    working_intent = intent_override if intent_override is not None else intent

    trigger_violations = classify_violations(trigger_evaluation)
    reason = "; ".join(str(v.metric) for v in trigger_violations) or "unspecified violation"

    metrics.configure()
    repository.transition(intent.id, IntentStatus.RECONCILING, f"violation detected: {reason}", sim_time=0.0)
    repository.transition(
        intent.id, IntentStatus.PLANNING, "recompiling with a new plan for a new episode", sim_time=0.0
    )

    capabilities = NetworkCapabilities(topology_spec)
    planner = IntentPlanner(
        capabilities,
        routing_strategy=routing_strategy,
        purification_strategy=purification_strategy,
        swapping_strategy=swapping_strategy,
        fidelity_estimator=fidelity_estimator,
    )
    new_plan = planner.plan(working_intent)

    adapter = SequenceAdapter(topology_spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)
    executor.redeploy(working_intent, new_plan)

    if not new_plan.feasible:
        logger.info("reconciliation found no feasible plan", extra={"intent_id": intent.id})
        return ReconciliationResult(
            intent_id=intent.id, trigger_violations=trigger_violations, new_plan=new_plan,
            new_evaluation=None, final_status=repository.get(intent.id).lifecycle.status,
        )

    executor.run()

    record = repository.get(intent.id)
    if record.lifecycle.status != IntentStatus.ACTIVE:
        # the reservation itself was rejected in the new episode too (FAILED)
        return ReconciliationResult(
            intent_id=intent.id, trigger_violations=trigger_violations, new_plan=new_plan,
            new_evaluation=None, final_status=record.lifecycle.status,
        )

    evidence = collect_intent_evidence(working_intent)
    new_evaluation = evaluate_intent(working_intent, evidence)
    final_status = IntentStatus.SATISFIED if new_evaluation.satisfied else IntentStatus.VIOLATED
    reason = "all success conditions met after reconciliation" if new_evaluation.satisfied else "; ".join(new_evaluation.violations)
    repository.transition(intent.id, final_status, reason, sim_time=adapter.get_timeline().now() / SECOND)

    logger.info(
        "reconciliation outcome: %s (route=%s)", final_status.value, "->".join(new_plan.route),
        extra={"intent_id": intent.id},
    )
    return ReconciliationResult(
        intent_id=intent.id, trigger_violations=trigger_violations, new_plan=new_plan,
        new_evaluation=new_evaluation, final_status=final_status,
    )
