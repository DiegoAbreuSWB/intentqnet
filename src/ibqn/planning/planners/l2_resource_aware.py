"""L2-R - resource-aware iterative analytical planner (planner-family
study, M6b).

Checkpoint 1 found that L2 (`l2_iterative.IterativeAnalyticalPlanner`)
resolves the three-node chain's false rejections completely, but on the
four-node chain trades REJECTED for VIOLATED: it accepts plans whose
analytical purification pair cost was never checked against the
reservation's actual resources, so real execution delivers far fewer
pairs than `min_delivered_pairs` requires. L2-R closes this gap - not by
retrofitting L2 (which stays untouched, byte-for-byte identical to its
checkpoint-1 behavior), but as a separate planner level that extends the
same fidelity-reachability estimate with THREE explicitly distinct
resource checks, never conflated (see `docs/l2_resource_aware_model.md`
for the full derivation):

1. **Peak simultaneous memory occupancy** - how many memories must be
   held at once (kept + measured, for one purification round in flight)
   - a snapshot quantity, NOT a running total.
2. **Cumulative raw-pair consumption** - the total number of elementary
   pairs consumed, across all rounds, to produce ONE final purified pair
   (`2**rounds`, exactly as L2 already computes - audited, not changed;
   see the module docstring's audit note and `docs/l2_iterative_model.md`).
3. **Generation capacity within the reservation window** - how many
   elementary pairs the route can plausibly produce in `duration_s`,
   which bounds how many FINAL pairs can be delivered given (2).

`required_pairs <= reserved_memory_slots` (the naive, conceptually wrong
check the planner-study brief explicitly warns against) conflates all
three - `reserved_memory_slots` is a snapshot pool size that gets reused
many times over the reservation window, not a cap on cumulative
consumption.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from ...intent.models import EntanglementIntent
from ...network.capabilities import NetworkCapabilities
from ..feasibility import estimate_latency_s, estimate_swap_only_fidelity
from ..fidelity_estimation import ConservativeMinEstimator
from ..models import EstimatedMetrics, ExecutionPlan
from .base import evaluate_candidates, to_candidate_evaluation
from .l2_iterative import IterativeAnalyticalPurification
from .l3_probabilistic import _purification_round_success_probability
from .models import PlannerDecision, PlannerExplanation, PlanningContext

BSM_SUCCESS_RATE = 0.5
"""Same constant `l3_probabilistic` uses - see that module's docstring for
the SeQUeNCe source (`sequence.components.bsm`'s `success_rate` default)."""

# Conservative correction factor on the naive attempt-rate model
# (attempt_rate = reserved_memory_slots / (2 * classical_delay_s)), applied
# in the SAFE (capacity-reducing) direction. Derived from comparing that
# naive formula against real F02 campaign data
# (results/raw/F02_routing/trials.csv, eg_attempts/duration_s), which
# showed the naive formula over-predicts attempt rate by roughly 2.4-4.3x
# (docs/l3_probabilistic_model.md). Using the high end of that observed
# range (rounded up) keeps L2-R's capacity estimate conservative rather
# than optimistic - a wrong capacity estimate should fail closed (reject
# a plan that might have worked) rather than open (accept one that won't).
# This is a STOPGAP pending the full audit (docs/l3_attempt_rate_audit.md);
# revisit both L2-R and L3-R's rate models together once that audit lands.
ATTEMPT_RATE_CONSERVATIVE_FACTOR = 4.5


class RejectionReason:
    """Specific rejection reason constants - never a single generic
    string (planner-study brief's explicit requirement)."""

    TARGET_FIDELITY_UNREACHABLE = "TARGET_FIDELITY_UNREACHABLE"
    INSUFFICIENT_PEAK_MEMORY = "INSUFFICIENT_PEAK_MEMORY"
    INSUFFICIENT_GENERATION_CAPACITY = "INSUFFICIENT_GENERATION_CAPACITY"
    DELIVERY_TARGET_EXCEEDS_WINDOW = "DELIVERY_TARGET_EXCEEDS_WINDOW"
    PURIFICATION_COST_TOO_HIGH = "PURIFICATION_COST_TOO_HIGH"
    MODEL_LIMIT_REACHED = "MODEL_LIMIT_REACHED"


@dataclass(frozen=True)
class ResourceAwareEstimate:
    target_fidelity_reachable: bool
    purification_rounds: int
    structural_raw_pairs_per_final_pair: int
    """`2**purification_rounds` - the exact, audited formula (see the
    module docstring) - not an approximation."""
    expected_raw_pairs_per_final_pair: float
    """`structural_raw_pairs_per_final_pair` inflated by the Dur-Briegel
    round success probability, exactly as L3 already computes it
    (`l3_probabilistic._purification_round_success_probability`) - reused,
    not re-derived."""
    peak_memory_slots_required: int
    reserved_memory_slots: int
    estimated_generation_rate: float
    """Elementary-generation attempts per second this route can sustain -
    see `ATTEMPT_RATE_CONSERVATIVE_FACTOR`'s docstring for why this is
    deliberately conservative, not the naive (checkpoint-1-flagged)
    over-estimate."""
    estimated_final_pair_rate: float
    estimated_max_delivered_pairs: int
    requested_delivered_pairs: int
    estimated_completion_time_s: float | None
    reservation_duration_s: float
    fidelity_feasible: bool
    memory_feasible: bool
    duration_feasible: bool
    delivery_feasible: bool
    bottleneck: str
    rejection_reason: str | None = None
    model_limit_hit: bool = False

    @property
    def feasible(self) -> bool:
        return self.fidelity_feasible and self.memory_feasible and self.duration_feasible and self.delivery_feasible


MODEL_MAX_STRUCTURAL_PAIR_COST = 10_000
"""Explicit saturation limit (planner-study brief section 5/8): beyond
this, the structural pair cost is treated as a model-limit case
(`RejectionReason.MODEL_LIMIT_REACHED`), not silently propagated as a
literal (e.g. astronomically large) number - see the audit note in
`docs/l2_iterative_model.md` (a max_rounds=100, near-unity-target case
reached `2**69`, which is not a meaningful physical quantity at this
project's topology scale)."""


def estimate_resource_aware_plan(
    capabilities: NetworkCapabilities,
    route: list[str],
    intent: EntanglementIntent,
    *,
    max_rounds: int = 8,
) -> ResourceAwareEstimate:
    swap_only_fidelity, _ = estimate_swap_only_fidelity(capabilities, route)
    target_fidelity = intent.requirements.min_fidelity
    allow_purification = intent.policy.allow_purification

    purification = IterativeAnalyticalPurification(max_rounds=max_rounds)
    purification.decide(swap_only_fidelity, target_fidelity, allow_purification)
    purification_estimate = purification.last_estimate

    fidelity_feasible = purification_estimate.target_reached
    rounds = len(purification_estimate.rounds)
    structural_pair_cost = purification_estimate.rounds[-1].cumulative_pair_cost if purification_estimate.rounds else 1

    model_limit_hit = structural_pair_cost > MODEL_MAX_STRUCTURAL_PAIR_COST
    if model_limit_hit:
        expected_pair_cost = float(structural_pair_cost)  # kept only for reporting; feasibility is forced False below
    else:
        expected_pair_cost = 1.0
        for round_estimate in purification_estimate.rounds:
            p = max(_purification_round_success_probability(round_estimate.input_fidelity), 1e-6)
            expected_pair_cost *= 2.0 / p

    # --- (1) peak simultaneous memory occupancy ---
    # A purification round needs 2 memories held at once (kept + measured -
    # see bbpssw_circuit.py); with no purification, 1 memory in flight is
    # enough. This is a snapshot requirement, independent of how many
    # rounds run over time (that's cumulative consumption, tracked
    # separately - see the module docstring).
    peak_memory_slots_required = 2 if rounds > 0 else 1
    reserved_memory_slots = intent.requirements.reserved_memory_slots
    memory_feasible = reserved_memory_slots >= peak_memory_slots_required

    # --- (2)/(3): generation capacity within the reservation window ---
    hop_count = len(route) - 1
    per_hop_probabilities = []
    for a, b in zip(route, route[1:]):
        link = capabilities.link(a, b)
        transmission = 10 ** (-(link.distance_m * link.attenuation_db_per_m) / 10)
        per_hop_probabilities.append(transmission * BSM_SUCCESS_RATE)
    raw_pair_probability = math.prod(per_hop_probabilities) if per_hop_probabilities else 0.0

    naive_attempt_rate = reserved_memory_slots / (2 * capabilities.classical_delay_s)
    estimated_generation_rate = naive_attempt_rate / ATTEMPT_RATE_CONSERVATIVE_FACTOR
    estimated_raw_pairs_in_window = estimated_generation_rate * intent.requirements.duration_s * raw_pair_probability

    if model_limit_hit:
        estimated_final_pair_rate = 0.0
        estimated_max_delivered_pairs = 0
    else:
        estimated_final_pair_rate = (
            (estimated_generation_rate * raw_pair_probability) / expected_pair_cost if expected_pair_cost > 0 else 0.0
        )
        estimated_max_delivered_pairs = int(math.floor(estimated_raw_pairs_in_window / expected_pair_cost)) if expected_pair_cost > 0 else 0

    requested_delivered_pairs = intent.requirements.min_delivered_pairs or 1
    duration_feasible = True  # this project's routes have no separate hard timeout beyond duration_s itself
    delivery_feasible = (not model_limit_hit) and (estimated_max_delivered_pairs >= requested_delivered_pairs)

    estimated_completion_time_s = (
        requested_delivered_pairs / estimated_final_pair_rate
        if estimated_final_pair_rate > 0 else None
    )

    bottleneck = "none"
    rejection_reason = None
    if not fidelity_feasible:
        bottleneck = "fidelity"
        rejection_reason = RejectionReason.TARGET_FIDELITY_UNREACHABLE
    elif model_limit_hit:
        bottleneck = "purification_cost"
        rejection_reason = RejectionReason.MODEL_LIMIT_REACHED
    elif not memory_feasible:
        bottleneck = "memory"
        rejection_reason = RejectionReason.INSUFFICIENT_PEAK_MEMORY
    elif not delivery_feasible:
        if estimated_max_delivered_pairs <= 0 and raw_pair_probability <= 0:
            bottleneck = "generation"
            rejection_reason = RejectionReason.INSUFFICIENT_GENERATION_CAPACITY
        else:
            bottleneck = "duration_vs_delivery_target"
            rejection_reason = RejectionReason.DELIVERY_TARGET_EXCEEDS_WINDOW

    return ResourceAwareEstimate(
        target_fidelity_reachable=fidelity_feasible, purification_rounds=rounds,
        structural_raw_pairs_per_final_pair=structural_pair_cost,
        expected_raw_pairs_per_final_pair=expected_pair_cost,
        peak_memory_slots_required=peak_memory_slots_required, reserved_memory_slots=reserved_memory_slots,
        estimated_generation_rate=estimated_generation_rate, estimated_final_pair_rate=estimated_final_pair_rate,
        estimated_max_delivered_pairs=estimated_max_delivered_pairs, requested_delivered_pairs=requested_delivered_pairs,
        estimated_completion_time_s=estimated_completion_time_s, reservation_duration_s=intent.requirements.duration_s,
        fidelity_feasible=fidelity_feasible, memory_feasible=memory_feasible, duration_feasible=duration_feasible,
        delivery_feasible=delivery_feasible, bottleneck=bottleneck, rejection_reason=rejection_reason,
        model_limit_hit=model_limit_hit,
    )


class ResourceAwareIterativePlanner:
    """L2-R: L2's fidelity-reachability estimate, gated by three explicit
    resource checks (peak memory, generation capacity, delivery-vs-window)
    - see the module docstring."""

    name = "iterative_resource_aware"
    level = "L2-R"

    def __init__(self, *, max_rounds: int = 8):
        self._max_rounds = max_rounds

    def plan(
        self,
        intent: EntanglementIntent,
        network_state: NetworkCapabilities,
        candidate_paths: list[list[str]],
        context: PlanningContext,
    ) -> PlannerDecision:
        t0 = time.perf_counter()
        fidelity_estimator = context.fidelity_estimator or ConservativeMinEstimator()
        purification_strategy = context.purification_strategy or IterativeAnalyticalPurification(max_rounds=self._max_rounds)

        candidate_evaluations = []
        estimates: dict[tuple[str, ...], ResourceAwareEstimate] = {}
        feasibility_by_route = {}
        if candidate_paths:
            evaluations = evaluate_candidates(
                network_state, candidate_paths, intent,
                purification_strategy=purification_strategy, fidelity_estimator=fidelity_estimator,
            )
            for route, result in zip(candidate_paths, evaluations):
                candidate_evaluations.append(to_candidate_evaluation(result))
                feasibility_by_route[tuple(route)] = result
                estimates[tuple(route)] = estimate_resource_aware_plan(
                    network_state, route, intent, max_rounds=self._max_rounds,
                )

        planning_wall_time_s = time.perf_counter() - t0
        feasible_routes = [route for route in candidate_paths if estimates[tuple(route)].feasible]

        if not feasible_routes:
            if not candidate_paths:
                reason = f"no path found from '{intent.endpoints.source}' to '{intent.endpoints.destination}'"
                rejection_reason = None
            else:
                best_route = candidate_paths[0]
                best_estimate = estimates[tuple(best_route)]
                rejection_reason = best_estimate.rejection_reason
                reason = (
                    f"{rejection_reason}: bottleneck={best_estimate.bottleneck}, "
                    f"estimated_max_delivered_pairs={best_estimate.estimated_max_delivered_pairs}, "
                    f"requested={best_estimate.requested_delivered_pairs}"
                )
            plan = ExecutionPlan.infeasible(intent.id, reason)
            explanation = PlannerExplanation(
                summary=f"rejected: {reason}",
                decisive_factors=[rejection_reason] if rejection_reason else ["no candidate route"],
                limiting_constraints=[reason],
                counterfactuals=_counterfactuals_for(rejection_reason),
            )
            return PlannerDecision(
                planner_name=self.name, planner_level=self.level, feasible=False, selected_plan=plan,
                candidate_evaluations=candidate_evaluations, rejection_reason=rejection_reason or reason,
                assumptions=(
                    "peak memory occupancy (2 if purifying, else 1) vs. reserved_memory_slots; generation "
                    f"capacity via a conservative attempt-rate estimate (naive rate / {ATTEMPT_RATE_CONSERVATIVE_FACTOR}, "
                    "pending docs/l3_attempt_rate_audit.md); structural pair cost saturates at "
                    f"{MODEL_MAX_STRUCTURAL_PAIR_COST} - see docs/l2_resource_aware_model.md"
                ),
                planning_wall_time_s=planning_wall_time_s, explanation=explanation,
            )

        best_route = max(feasible_routes, key=lambda r: estimates[tuple(r)].estimated_max_delivered_pairs)
        best_estimate = estimates[tuple(best_route)]
        best_feasibility = feasibility_by_route[tuple(best_route)]

        estimated_fidelity = (
            best_feasibility.purified_fidelity_estimate if best_feasibility.requires_purification
            else best_feasibility.swap_only_fidelity
        )
        plan = ExecutionPlan(
            intent_id=intent.id, feasible=True, route=best_route,
            route_rationale=(
                f"selected by L2-R: estimated_max_delivered_pairs={best_estimate.estimated_max_delivered_pairs} "
                f">= requested={best_estimate.requested_delivered_pairs}"
            ),
            reservations=best_feasibility.reservations, requires_purification=best_feasibility.requires_purification,
            purification_rounds_estimate=best_feasibility.purification_rounds_estimate,
            estimated_metrics=EstimatedMetrics(
                fidelity=estimated_fidelity, latency_s=estimate_latency_s(network_state, best_route),
            ),
            fidelity_estimator=fidelity_estimator.name,
            fallback_routes=[r for r in feasible_routes if r != best_route],
        )
        explanation = PlannerExplanation(
            summary=(
                f"accepted route {' -> '.join(best_route)}: fidelity reachable in "
                f"{best_estimate.purification_rounds} round(s), estimated max deliverable "
                f"{best_estimate.estimated_max_delivered_pairs} pairs (requested {best_estimate.requested_delivered_pairs})"
            ),
            decisive_factors=[
                f"peak_memory_slots_required={best_estimate.peak_memory_slots_required}",
                f"estimated_max_delivered_pairs={best_estimate.estimated_max_delivered_pairs}",
            ],
            limiting_constraints=[f"bottleneck={best_estimate.bottleneck}"],
            uncertainty_notes=(
                f"estimated_completion_time_s={best_estimate.estimated_completion_time_s}"
                if best_estimate.estimated_completion_time_s is not None else "completion time not estimable"
            ),
        )
        return PlannerDecision(
            planner_name=self.name, planner_level=self.level, feasible=True, selected_plan=plan,
            candidate_evaluations=candidate_evaluations,
            predicted_delivered_pairs=float(best_estimate.estimated_max_delivered_pairs),
            predicted_average_fidelity=estimated_fidelity, predicted_minimum_fidelity=estimated_fidelity,
            assumptions=(
                "peak memory occupancy (2 if purifying, else 1) vs. reserved_memory_slots; generation "
                f"capacity via a conservative attempt-rate estimate (naive rate / {ATTEMPT_RATE_CONSERVATIVE_FACTOR}, "
                "pending docs/l3_attempt_rate_audit.md); structural pair cost saturates at "
                f"{MODEL_MAX_STRUCTURAL_PAIR_COST} - see docs/l2_resource_aware_model.md"
            ),
            planning_wall_time_s=planning_wall_time_s, explanation=explanation,
        )


def _counterfactuals_for(rejection_reason: str | None) -> list[str]:
    if rejection_reason == RejectionReason.TARGET_FIDELITY_UNREACHABLE:
        return ["reduce min_fidelity below the iterative purification ceiling", "try a different route"]
    if rejection_reason == RejectionReason.INSUFFICIENT_PEAK_MEMORY:
        return ["increase reserved_memory_slots to at least 2 (purification needs kept+measured simultaneously)"]
    if rejection_reason == RejectionReason.INSUFFICIENT_GENERATION_CAPACITY:
        return ["increase duration_s", "increase reserved_memory_slots", "try a lower-loss route"]
    if rejection_reason == RejectionReason.DELIVERY_TARGET_EXCEEDS_WINDOW:
        return ["increase duration_s", "reduce min_delivered_pairs", "reduce min_fidelity (fewer purification rounds needed)"]
    if rejection_reason == RejectionReason.MODEL_LIMIT_REACHED:
        return ["reduce min_fidelity substantially - the analytical model's purification-cost estimate saturated"]
    return []
