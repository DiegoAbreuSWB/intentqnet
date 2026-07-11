"""Executes a `Scenario` end-to-end: builds the topology, plans and deploys
every intent it declares, runs the simulation once, and collects results
straight from `IntentRepository`/`sequence.utils.metrics` - never computed
independently of the simulation (see docs/sequence_code_analysis.md,
section 2 constraints).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sequence.utils import metrics

from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import IntentStatus
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..planning.models import ExecutionPlan
from ..planning.planner import IntentPlanner
from ..planning.purification import PurificationStrategy
from ..planning.routing import RoutingStrategy
from ..planning.swapping import SwappingStrategy
from ..utils.logging import get_logger
from .scenarios import Scenario

logger = get_logger(__name__)


@dataclass
class IntentRunResult:
    intent_id: str
    final_status: IntentStatus
    satisfied: bool | None
    plan: ExecutionPlan
    metrics: dict = field(default_factory=dict)


@dataclass
class ScenarioResult:
    scenario_name: str
    seed: int
    intent_results: list[IntentRunResult]

    def get(self, intent_id: str) -> IntentRunResult:
        try:
            return next(r for r in self.intent_results if r.intent_id == intent_id)
        except StopIteration:
            raise KeyError(f"no result for intent '{intent_id}' in this scenario run") from None


def run_scenario(
    scenario: Scenario,
    *,
    seed: int | None = None,
    routing_strategy: RoutingStrategy | None = None,
    purification_strategy: PurificationStrategy | None = None,
    swapping_strategy: SwappingStrategy | None = None,
) -> ScenarioResult:
    """Builds a fresh `SequenceAdapter` + `IntentPlanner` + `SequenceExecutor`
    for `scenario`, plans and deploys every declared intent, runs the
    simulation once, and returns each intent's final status/plan/metrics.

    `sequence.utils.metrics` is a process-wide singleton
    (docs/sequence_code_analysis.md, section 4.1) - reset at the start of
    every call so repeated trials (see `experiments.seeds`) don't leak into
    each other.
    """
    metrics.configure()
    metrics.reset_metrics()

    effective_seed = seed if seed is not None else scenario.spec.simulation.seed
    topology_spec = scenario.topology_spec()
    capabilities = NetworkCapabilities(topology_spec)
    adapter = SequenceAdapter(topology_spec, seed=effective_seed)
    planner = IntentPlanner(
        capabilities,
        routing_strategy=routing_strategy,
        purification_strategy=purification_strategy,
        swapping_strategy=swapping_strategy,
    )
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)

    plans: dict[str, ExecutionPlan] = {}
    for intent in scenario.intents:
        plan = planner.plan(intent)
        plans[intent.id] = plan
        executor.deploy(intent, plan)

    logger.info(
        "running scenario '%s', seed=%d, %d intent(s)",
        scenario.spec.name, effective_seed, len(scenario.intents),
    )
    executor.run()

    results = []
    for intent in scenario.intents:
        record = repository.get(intent.id)
        trial_metrics = metrics.collect_trial_metrics(intent.endpoints.source)
        results.append(
            IntentRunResult(
                intent_id=intent.id,
                final_status=record.lifecycle.status,
                satisfied=record.result.satisfied if record.result else None,
                plan=plans[intent.id],
                metrics=trial_metrics,
            )
        )

    return ScenarioResult(scenario_name=scenario.spec.name, seed=effective_seed, intent_results=results)
