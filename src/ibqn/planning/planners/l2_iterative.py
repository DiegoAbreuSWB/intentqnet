"""L2 - iterative analytical planner (planner study, M3).

Extends `planning.purification.PurificationStrategy` - the exact interface
`planning.feasibility.evaluate_route` already consumes - with
`IterativeAnalyticalPurification`, which repeats
`BBPSSWCircuit.improved_fidelity` (the same formula L1/`PurifyUntilTarget`
calls once) until the target is reached, a round cap is hit, or the
projected pair cost stops being worth modeling further. Because it is a
drop-in `PurificationStrategy`, L2 reuses `planning.planner.IntentPlanner`
and `planning.feasibility.evaluate_route` exactly like L1 does - candidate
generation, resource validation, and the base fidelity model are NOT
duplicated (see `docs/l2_iterative_model.md`).

This is a planning-side ANALYTICAL approximation of what SeQUeNCe's real
`purification_mode='until_target'` does at execution time - not a port of
its internal retry loop (`planning.purification`'s module docstring
explains why that would require bypassing the reservation API). Two
rounds analytically estimated is not automatically "closer to the truth"
than one; whether L2 actually reduces the false-rejection rate P01 exists
to reproduce is an empirical question this campaign answers, never assumed
here.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ...intent.models import EntanglementIntent
from ...network.capabilities import NetworkCapabilities
from ...physics import IDEAL_BBPSSW, PurificationPhysics
from ..fidelity_estimation import ConservativeMinEstimator
from ..planner import IntentPlanner
from ..purification import PurificationDecision, PurificationStrategy
from .base import evaluate_candidates, to_candidate_evaluation
from .models import PlannerDecision, PlannerExplanation, PlanningContext

PAIR_CONSUMPTION_PER_ROUND = 2
"""BBPSSW consumes two input (lower-fidelity) memory pairs to produce one
higher-fidelity output pair per successful round (see
`bbpssw_circuit.BBPSSWCircuit.received_message`: one `kept_memo` improved,
one `meas_memo` measured/discarded) - the analytical planning-side
assumption L2 uses, not a re-derivation of SeQUeNCe's internal retry/
failure-recovery accounting (see the module docstring)."""


@dataclass(frozen=True)
class PurificationRoundEstimate:
    round_index: int
    input_fidelity: float
    output_fidelity: float
    required_input_pairs: int
    cumulative_pair_cost: int
    estimated_success_probability: float | None = None
    """`None` at L2 - a round's real success probability depends on the
    quantum state/measurement statistics SeQUeNCe's circuit simulation
    resolves, which this analytical model does not attempt to predict (L3
    introduces an approximate probability model - see
    docs/l3_probabilistic_model.md, added after checkpoint 1)."""


@dataclass(frozen=True)
class IterativePurificationEstimate:
    initial_fidelity: float
    rounds: list[PurificationRoundEstimate] = field(default_factory=list)
    target_reached: bool = False
    resource_feasible: bool = True
    stopping_reason: str = ""


class IterativeAnalyticalPurification(PurificationStrategy):
    """Repeats `BBPSSWCircuit.improved_fidelity` analytically until the
    target fidelity is reached, `max_rounds` is hit, or the projected
    cumulative pair cost exceeds `max_pair_cost` (if set) - see
    `docs/l2_iterative_model.md` for the exact stopping conditions and
    their justification."""

    name = "iterative_analytical"

    def __init__(self, *, max_rounds: int = 8, max_pair_cost: int | None = None):
        self._max_rounds = max_rounds
        self._max_pair_cost = max_pair_cost
        self._last_estimate: IterativePurificationEstimate | None = None

    @property
    def last_estimate(self) -> IterativePurificationEstimate | None:
        """The full round-by-round breakdown from the most recent
        `decide()` call. `l2_iterative.IterativeAnalyticalPlanner` reads
        this immediately after `feasibility.evaluate_route` calls
        `decide()` internally, so the detailed estimate is never
        recomputed - each `IterativeAnalyticalPurification` instance must
        be used for exactly one `evaluate_route` call before its
        `last_estimate` is read (see `l2_iterative.IterativeAnalyticalPlanner.plan`,
        which constructs a fresh instance per candidate route for exactly
        this reason)."""
        return self._last_estimate

    def decide(
        self, swap_only_fidelity: float, target_fidelity: float, allow_purification: bool,
        *, physics: PurificationPhysics | None = None,
    ) -> PurificationDecision:
        estimate = self._estimate(swap_only_fidelity, target_fidelity, allow_purification, physics=physics)
        self._last_estimate = estimate
        if not estimate.rounds:
            return PurificationDecision(
                attempt=False, fidelity_estimate=estimate.initial_fidelity, rounds_estimate=0,
                note=estimate.stopping_reason, execution_mode=self.execution_mode,
            )
        last = estimate.rounds[-1]
        return PurificationDecision(
            attempt=True, fidelity_estimate=last.output_fidelity, rounds_estimate=len(estimate.rounds),
            note=estimate.stopping_reason, execution_mode=self.execution_mode,
        )

    def _estimate(
        self, swap_only_fidelity: float, target_fidelity: float, allow_purification: bool,
        *, physics: PurificationPhysics | None = None,
    ) -> IterativePurificationEstimate:
        one_round = physics or IDEAL_BBPSSW
        if swap_only_fidelity >= target_fidelity:
            return IterativePurificationEstimate(
                initial_fidelity=swap_only_fidelity, rounds=[], target_reached=True, resource_feasible=True,
                stopping_reason="single swap already meets target_fidelity",
            )
        if not allow_purification:
            return IterativePurificationEstimate(
                initial_fidelity=swap_only_fidelity, rounds=[], target_reached=False, resource_feasible=True,
                stopping_reason="target_fidelity exceeds the single-swap estimate and allow_purification is False",
            )

        rounds: list[PurificationRoundEstimate] = []
        current_fidelity = swap_only_fidelity
        cumulative_pairs = 1
        for round_index in range(1, self._max_rounds + 1):
            _, output_fidelity = one_round.improve(current_fidelity)
            cumulative_pairs *= PAIR_CONSUMPTION_PER_ROUND

            if self._max_pair_cost is not None and cumulative_pairs > self._max_pair_cost:
                return IterativePurificationEstimate(
                    initial_fidelity=swap_only_fidelity, rounds=rounds, target_reached=False,
                    resource_feasible=False,
                    stopping_reason=(
                        f"projected cumulative pair cost {cumulative_pairs} exceeds max_pair_cost="
                        f"{self._max_pair_cost} at round {round_index}"
                    ),
                )

            rounds.append(PurificationRoundEstimate(
                round_index=round_index, input_fidelity=current_fidelity, output_fidelity=output_fidelity,
                required_input_pairs=PAIR_CONSUMPTION_PER_ROUND, cumulative_pair_cost=cumulative_pairs,
            ))

            if output_fidelity >= target_fidelity:
                return IterativePurificationEstimate(
                    initial_fidelity=swap_only_fidelity, rounds=rounds, target_reached=True, resource_feasible=True,
                    stopping_reason=f"target reached after {round_index} round(s)",
                )
            if output_fidelity <= current_fidelity + 1e-12:
                # BBPSSW's fixed point: gains shrink to numerical noise as
                # fidelity approaches 1 - a real stopping condition, not an
                # early truncation before a reachable target (see
                # docs/l2_iterative_model.md).
                return IterativePurificationEstimate(
                    initial_fidelity=swap_only_fidelity, rounds=rounds, target_reached=False, resource_feasible=True,
                    stopping_reason=f"no further gain after round {round_index} (fixed point reached)",
                )
            current_fidelity = output_fidelity

        return IterativePurificationEstimate(
            initial_fidelity=swap_only_fidelity, rounds=rounds, target_reached=False, resource_feasible=True,
            stopping_reason=f"exceeded max_rounds={self._max_rounds} without reaching target_fidelity",
        )


class IterativeAnalyticalPlanner:
    """L2: same routing/resource machinery as L1 (via `IntentPlanner`), an
    iterative analytical purification estimate instead of L1's one-round
    ceiling."""

    name = "iterative_analytical"
    level = "L2"

    def __init__(self, *, max_rounds: int = 8, max_pair_cost: int | None = None):
        self._max_rounds = max_rounds
        self._max_pair_cost = max_pair_cost

    def plan(
        self,
        intent: EntanglementIntent,
        network_state: NetworkCapabilities,
        candidate_paths: list[list[str]],
        context: PlanningContext,
    ) -> PlannerDecision:
        t0 = time.perf_counter()
        fidelity_estimator = context.fidelity_estimator or ConservativeMinEstimator()
        # A fresh instance per plan() call: `last_estimate` reflects exactly
        # one `decide()` call (see the class docstring) - `IntentPlanner`
        # calls `evaluate_route` once per candidate route internally, so a
        # single instance would only ever expose the LAST candidate's
        # estimate. `_planning_purification` below (used for `IntentPlanner`)
        # and the per-candidate instances used for `candidate_evaluations`
        # are therefore deliberately separate objects.
        planning_purification = IterativeAnalyticalPurification(
            max_rounds=self._max_rounds, max_pair_cost=self._max_pair_cost,
        )

        inner_planner = IntentPlanner(
            network_state, routing_strategy=context.routing_strategy,
            purification_strategy=planning_purification, fidelity_estimator=fidelity_estimator,
        )
        execution_plan = inner_planner.plan(intent)
        planning_wall_time_s = time.perf_counter() - t0

        candidate_evaluations = []
        best_estimate: IterativePurificationEstimate | None = None
        for route in candidate_paths:
            per_route_purification = IterativeAnalyticalPurification(
                max_rounds=self._max_rounds, max_pair_cost=self._max_pair_cost,
            )
            evaluations = evaluate_candidates(
                network_state, [route], intent,
                purification_strategy=per_route_purification, fidelity_estimator=fidelity_estimator,
            )
            result = evaluations[0]
            candidate_evaluations.append(to_candidate_evaluation(result))
            if execution_plan.feasible and route == execution_plan.route:
                best_estimate = per_route_purification.last_estimate

        assumptions = (
            f"conservative_min hop-fidelity model; iterative analytical purification, up to "
            f"{self._max_rounds} rounds of BBPSSWCircuit.improved_fidelity, stopping early on target/fixed-point/"
            f"pair-cost limit (see docs/l2_iterative_model.md)"
        )

        if not execution_plan.feasible:
            explanation = PlannerExplanation(
                summary=f"rejected: {execution_plan.infeasibility_reason}",
                decisive_factors=["iterative purification estimate did not reach target within max_rounds/max_pair_cost"],
                limiting_constraints=[execution_plan.infeasibility_reason or ""],
                counterfactuals=[
                    "increase reserved_memory_slots or a permitted max_pair_cost (more purification rounds affordable)",
                    "reduce min_fidelity below the projected achievable ceiling",
                    "try a different route (changes the swap-only starting fidelity)",
                ],
            )
            return PlannerDecision(
                planner_name=self.name, planner_level=self.level, feasible=False, selected_plan=execution_plan,
                candidate_evaluations=candidate_evaluations, rejection_reason=execution_plan.infeasibility_reason,
                assumptions=assumptions, planning_wall_time_s=planning_wall_time_s, explanation=explanation,
            )

        estimated_fidelity = execution_plan.estimated_metrics.fidelity if execution_plan.estimated_metrics else None
        rounds_used = len(best_estimate.rounds) if best_estimate else 0
        explanation = PlannerExplanation(
            summary=(
                f"accepted route {' -> '.join(execution_plan.route)}, estimated fidelity {estimated_fidelity} "
                f"after {rounds_used} iterative purification round(s)"
            ),
            decisive_factors=[execution_plan.route_rationale, f"{rounds_used} purification round(s) estimated"],
            limiting_constraints=[f"max_rounds={self._max_rounds}" + (
                f", max_pair_cost={self._max_pair_cost}" if self._max_pair_cost is not None else ""
            )],
        )
        return PlannerDecision(
            planner_name=self.name, planner_level=self.level, feasible=True, selected_plan=execution_plan,
            candidate_evaluations=candidate_evaluations,
            predicted_average_fidelity=estimated_fidelity, predicted_minimum_fidelity=estimated_fidelity,
            assumptions=assumptions, planning_wall_time_s=planning_wall_time_s, explanation=explanation,
        )
