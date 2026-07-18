"""L1 - conservative one-round analytical planner (planner study, M2).

This is a WRAPPER around the existing, already-tested `planning.planner.
IntentPlanner` + `planning.fidelity_estimation.ConservativeMinEstimator` +
`planning.purification.PurifyUntilTarget` - not a re-implementation. L1
must reproduce the historical F01-F08 planning decisions exactly (see
`tests/planning/planners/test_l1_regression.py`), and delegating to the
real `IntentPlanner.plan()` call is the only way to GUARANTEE that: any
reimplementation, however careful, risks silent behavioral drift.

`IntentPlanner.plan()` regenerates its own candidate routes internally
(from the same `context.routing_strategy` instance passed to it) rather
than accepting a pre-computed list - so `candidate_paths` here is used
only to populate this decision's `candidate_evaluations` for analysis,
never re-passed into `IntentPlanner`. Since route generation is a
deterministic, pure function of the topology and routing strategy, the
routes `IntentPlanner` regenerates are identical to `candidate_paths` by
construction (verified in `tests/planning/planners/test_l1_regression.py`).

L1 predicts feasibility and a single fidelity/latency point estimate -
nothing else. It never predicts delivered pairs, throughput, or a
satisfaction probability (those fields stay `None`, per the planner-study
brief's "never predict where the model has no information" rule) -
predicting them was never part of L1's original behavior and adding them
now would silently change what "L1" has always meant in this project.
"""
from __future__ import annotations

import time

from ...intent.models import EntanglementIntent
from ...network.capabilities import NetworkCapabilities
from ..fidelity_estimation import ConservativeMinEstimator
from ..planner import IntentPlanner
from ..purification import PurifyUntilTarget
from .base import evaluate_candidates, to_candidate_evaluation
from .models import PlannerDecision, PlannerExplanation, PlanningContext


class ConservativeOneRoundPlanner:
    """L1: exactly reproduces `IntentPlanner` + `ConservativeMinEstimator` +
    `PurifyUntilTarget` - the planner active for every F01-F08 campaign."""

    name = "conservative_one_round"
    level = "L1"

    def plan(
        self,
        intent: EntanglementIntent,
        network_state: NetworkCapabilities,
        candidate_paths: list[list[str]],
        context: PlanningContext,
    ) -> PlannerDecision:
        t0 = time.perf_counter()
        purification_strategy = context.purification_strategy or PurifyUntilTarget()
        fidelity_estimator = context.fidelity_estimator or ConservativeMinEstimator()

        inner_planner = IntentPlanner(
            network_state, routing_strategy=context.routing_strategy,
            purification_strategy=purification_strategy, fidelity_estimator=fidelity_estimator,
        )
        execution_plan = inner_planner.plan(intent)
        planning_wall_time_s = time.perf_counter() - t0

        evaluations = evaluate_candidates(
            network_state, candidate_paths, intent,
            purification_strategy=purification_strategy, fidelity_estimator=fidelity_estimator,
        )
        candidate_evaluations = [to_candidate_evaluation(e) for e in evaluations]

        if not execution_plan.feasible:
            explanation = PlannerExplanation(
                summary=f"rejected: {execution_plan.infeasibility_reason}",
                decisive_factors=["single-swap fidelity estimate", "one-round purification ceiling (if attempted)"],
                limiting_constraints=[execution_plan.infeasibility_reason or ""],
                counterfactuals=_rejection_counterfactuals(),
            )
            return PlannerDecision(
                planner_name=self.name, planner_level=self.level, feasible=False, selected_plan=execution_plan,
                candidate_evaluations=candidate_evaluations, rejection_reason=execution_plan.infeasibility_reason,
                assumptions=(
                    "conservative_min hop-fidelity model (min of endpoint raw_fidelity per hop); at most one "
                    "analytical purification round (BBPSSWCircuit.improved_fidelity applied once)"
                ),
                planning_wall_time_s=planning_wall_time_s, explanation=explanation,
            )

        estimated_fidelity = execution_plan.estimated_metrics.fidelity if execution_plan.estimated_metrics else None
        explanation = PlannerExplanation(
            summary=f"accepted route {' -> '.join(execution_plan.route)}, estimated fidelity {estimated_fidelity}",
            decisive_factors=[
                execution_plan.route_rationale,
                "purification attempted" if execution_plan.requires_purification else "no purification needed",
            ],
            limiting_constraints=["one analytical purification round maximum (L1's defining limitation)"],
        )
        return PlannerDecision(
            planner_name=self.name, planner_level=self.level, feasible=True, selected_plan=execution_plan,
            candidate_evaluations=candidate_evaluations,
            predicted_average_fidelity=estimated_fidelity, predicted_minimum_fidelity=estimated_fidelity,
            assumptions=(
                "conservative_min hop-fidelity model (min of endpoint raw_fidelity per hop); at most one "
                "analytical purification round (BBPSSWCircuit.improved_fidelity applied once) - see "
                "docs/false_rejection_root_cause.md for the known consequence of this limitation"
            ),
            planning_wall_time_s=planning_wall_time_s, explanation=explanation,
        )


def _rejection_counterfactuals() -> list[str]:
    return [
        "increase duration_s (more time for elementary generation attempts, does not change the fidelity ceiling)",
        "increase reserved_memory_slots (resource capacity only, does not change the fidelity ceiling)",
        "reduce min_fidelity below the one-round purification ceiling",
        "try a different route (may change swap-only fidelity, but the one-round ceiling still applies)",
    ]
