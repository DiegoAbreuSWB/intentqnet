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

from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import NetworkTopologySpec
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
) -> ReconciliationResult:
    """Attempts to satisfy `intent` again, on a fresh episode.

    `intent` must already be registered in `repository` with lifecycle
    status `VIOLATED` (the outcome of a prior `evaluate_intent` call,
    `trigger_evaluation`). Builds a brand-new `SequenceAdapter` (new
    `Timeline`, simulation time restarts at 0) over the same `topology_spec`,
    replans `intent` (optionally with different strategies), and - if a
    feasible plan exists - deploys and runs it, then evaluates the outcome
    the same way `experiments.runner.run_scenario` does.

    Does not retry more than once: if the new plan is infeasible or the new
    run is still violated, `reconcile` returns that outcome directly rather
    than searching further (see docs/assurance_design.md, section 11).
    """
    trigger_violations = classify_violations(trigger_evaluation)
    reason = "; ".join(str(v.metric) for v in trigger_violations) or "unspecified violation"

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
    )
    new_plan = planner.plan(intent)

    adapter = SequenceAdapter(topology_spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)
    executor.redeploy(intent, new_plan)

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

    evidence = collect_intent_evidence(intent)
    new_evaluation = evaluate_intent(intent, evidence)
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
