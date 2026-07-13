"""First planner version (see docs/sequence_code_analysis.md, section 4.8
"Plano de implementação revisado" and the project brief, section 9):

1. find candidate routes (`RoutingStrategy`, best-first per its own criterion)
2. estimate feasibility of each (`feasibility.evaluate_route`)
3. exclude routes that fail memory/fidelity requirements
4. pick the first feasible route (i.e., the routing strategy's own best
   viable choice - no separate, strategy-independent cost function)
9. reject the intent if no candidate route is feasible

There is no notion of a single globally-optimal plan: swapping the
`RoutingStrategy`/`PurificationStrategy` changes which plan comes out, by
design (see docs/architecture.md).
"""
from __future__ import annotations

from ..intent.models import EntanglementIntent
from ..network.capabilities import NetworkCapabilities
from ..utils.logging import get_logger
from .feasibility import estimate_latency_s, evaluate_route
from .fidelity_estimation import ConservativeMinEstimator, LinkFidelityEstimator
from .models import EstimatedMetrics, ExecutionPlan
from .purification import PurificationStrategy, PurifyUntilTarget
from .routing import RoutingStrategy, ShortestHopCountRouting
from .swapping import DefaultSequenceSwappingStrategy, SwappingStrategy

logger = get_logger(__name__)


class IntentPlanner:
    def __init__(
        self,
        capabilities: NetworkCapabilities,
        *,
        routing_strategy: RoutingStrategy | None = None,
        purification_strategy: PurificationStrategy | None = None,
        swapping_strategy: SwappingStrategy | None = None,
        fidelity_estimator: LinkFidelityEstimator | None = None,
    ):
        self._capabilities = capabilities
        self._routing_strategy = routing_strategy or ShortestHopCountRouting()
        self._purification_strategy = purification_strategy or PurifyUntilTarget()
        self._swapping_strategy = swapping_strategy or DefaultSequenceSwappingStrategy()
        self._fidelity_estimator = fidelity_estimator or ConservativeMinEstimator()

    def plan(self, intent: EntanglementIntent) -> ExecutionPlan:
        source, destination = intent.endpoints.source, intent.endpoints.destination
        candidates = self._routing_strategy.find_candidate_paths(self._capabilities, source, destination)
        if not candidates:
            reason = f"no path found from '{source}' to '{destination}'"
            logger.info("planning failed: %s", reason, extra={"intent_id": intent.id})
            return ExecutionPlan.infeasible(intent.id, reason)

        evaluated = [
            evaluate_route(
                self._capabilities, route, intent, purification_strategy=self._purification_strategy,
                fidelity_estimator=self._fidelity_estimator,
            )
            for route in candidates
        ]
        feasible = [result for result in evaluated if result.feasible]
        if not feasible:
            reason = "no candidate route is feasible: " + "; ".join(
                f"{'->'.join(result.route)} ({result.reason})" for result in evaluated
            )
            logger.info("planning failed: %s", reason, extra={"intent_id": intent.id})
            return ExecutionPlan.infeasible(intent.id, reason)

        best = feasible[0]
        latency_s = estimate_latency_s(self._capabilities, best.route)
        estimated_fidelity = best.purified_fidelity_estimate if best.requires_purification else best.swap_only_fidelity

        plan = ExecutionPlan(
            intent_id=intent.id,
            feasible=True,
            route=best.route,
            route_rationale=(
                f"selected by {type(self._routing_strategy).__name__}; "
                f"hop fidelities {[round(f, 4) for f in best.hop_fidelities]}"
            ),
            reservations=best.reservations,
            requires_purification=best.requires_purification,
            purification_rounds_estimate=best.purification_rounds_estimate,
            swapping_strategy_note=self._swapping_strategy.describe(best.route),
            estimated_metrics=EstimatedMetrics(fidelity=estimated_fidelity, latency_s=latency_s),
            fidelity_estimator=self._fidelity_estimator.name,
            fallback_routes=[result.route for result in feasible[1:]],
        )
        logger.info(
            "planned route %s, estimated_fidelity=%.4f, purification=%s",
            "->".join(plan.route), estimated_fidelity, plan.requires_purification,
            extra={"intent_id": intent.id},
        )
        return plan
