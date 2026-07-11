"""Runs a real two-episode reconciliation demo end-to-end for notebooks 15
and 19: episode 1 (deploy + run + evaluate, expected to end VIOLATED) and
episode 2 (`assurance.reconciliation.reconcile`, a fresh `Timeline` reusing
the *same* `IntentRepository` so lifecycle history survives across
episodes).

Mirrors `tests/integration/test_reconciliation.py::
test_diamond_scenario_violated_then_reconciled` step by step - that test is
the calibration this helper reuses, not a new one invented for the
notebooks (see `demos.topologies.diamond_spec`/`demos.intents.diamond_intent`).

Kept separate from `demos.scenarios.ad_hoc_scenario`/`run_scenario`
because `reconcile()` requires the caller to hold on to the same
`IntentRepository` across both episodes - `run_scenario` builds and
discards its own repository internally, so it cannot be reused here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sequence.constants import SECOND
from sequence.utils import metrics

from ..assurance.evaluator import IntentEvaluation, evaluate_intent
from ..assurance.reconciliation import reconcile
from ..assurance.telemetry import collect_intent_evidence
from ..assurance.violations import Violation, classify_violations
from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import NetworkTopologySpec
from ..planning.planner import IntentPlanner
from ..planning.routing import RoutingStrategy, ShortestHopCountRouting


@dataclass(frozen=True)
class ReconciliationEpisode:
    episode: int
    strategy_name: str
    route: list[str]
    final_status: IntentStatus
    evaluation: IntentEvaluation | None


@dataclass(frozen=True)
class ReconciliationDemo:
    intent_id: str
    episodes: list[ReconciliationEpisode] = field(default_factory=list)
    trigger_violations: list[Violation] = field(default_factory=list)
    repository: IntentRepository | None = None


def run_two_episode_reconciliation(
    topology_spec: NetworkTopologySpec,
    intent: EntanglementIntent,
    *,
    first_seed: int,
    second_seed: int,
    first_routing_strategy: RoutingStrategy | None = None,
    second_routing_strategy: RoutingStrategy | None = None,
) -> ReconciliationDemo:
    """Runs episode 1 with `first_routing_strategy` (default
    `ShortestHopCountRouting`, SeQUeNCe's own auto-routing default). If it
    ends VIOLATED, runs episode 2 via `reconcile()` with
    `second_routing_strategy`. Returns both episodes plus the shared
    `IntentRepository` (its `.lifecycle.history` spans both episodes)."""
    metrics.configure()
    capabilities = NetworkCapabilities(topology_spec)
    repository = IntentRepository()

    planner_1 = IntentPlanner(capabilities, routing_strategy=first_routing_strategy)
    plan_1 = planner_1.plan(intent)
    adapter_1 = SequenceAdapter(topology_spec, seed=first_seed)
    executor_1 = SequenceExecutor(adapter_1, repository)
    executor_1.deploy(intent, plan_1)
    executor_1.run()

    record = repository.get(intent.id)
    if record.lifecycle.status != IntentStatus.ACTIVE:
        raise ValueError(
            f"episode 1 did not reach ACTIVE (status={record.lifecycle.status.value}); "
            "cannot demonstrate reconciliation without a real VIOLATED episode first"
        )

    evidence_1 = collect_intent_evidence(intent)
    evaluation_1 = evaluate_intent(intent, evidence_1)
    status_1 = IntentStatus.SATISFIED if evaluation_1.satisfied else IntentStatus.VIOLATED
    reason_1 = "all success conditions met" if evaluation_1.satisfied else "; ".join(evaluation_1.violations)
    repository.transition(intent.id, status_1, reason_1, sim_time=adapter_1.get_timeline().now() / SECOND)

    episode_1 = ReconciliationEpisode(
        episode=1,
        strategy_name=type(first_routing_strategy).__name__ if first_routing_strategy else type(ShortestHopCountRouting()).__name__,
        route=plan_1.route, final_status=status_1, evaluation=evaluation_1,
    )

    if status_1 != IntentStatus.VIOLATED:
        return ReconciliationDemo(intent_id=intent.id, episodes=[episode_1], repository=repository)

    trigger_violations = classify_violations(evaluation_1)
    result = reconcile(
        intent, topology_spec, repository, evaluation_1,
        seed=second_seed, routing_strategy=second_routing_strategy,
    )
    episode_2 = ReconciliationEpisode(
        episode=2,
        strategy_name=type(second_routing_strategy).__name__ if second_routing_strategy else type(ShortestHopCountRouting()).__name__,
        route=result.new_plan.route, final_status=result.final_status, evaluation=result.new_evaluation,
    )
    return ReconciliationDemo(
        intent_id=intent.id, episodes=[episode_1, episode_2],
        trigger_violations=trigger_violations, repository=repository,
    )
