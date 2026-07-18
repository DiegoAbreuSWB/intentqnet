"""L3-R - resource-aware probabilistic planner (planner-family study, M6d).

L3-original (`l3_probabilistic.ProbabilisticPlanner`) is preserved
byte-for-byte, unmodified - its P02 results stay valid and are never
retroactively altered. L3-R is a SEPARATE planner level
(`planner_level="L3-R"`, `planner_name="probabilistic_resource_aware"`)
that:

1. Reuses L2-R's deterministic gates (`l2_resource_aware.
   estimate_resource_aware_plan`) rather than re-deriving peak-memory or
   purification-cost feasibility a second time - if L2-R says the plan is
   structurally impossible (insufficient peak memory) or its analytical
   cost model saturated (`MODEL_LIMIT_REACHED`), that is a deterministic
   fact, not a probability, and L3-R short-circuits to
   `satisfaction_probability=0.0` rather than feeding a broken estimate
   into a Poisson layer (planner-study brief section 9).
2. Replaces L3-original's uncorrected attempt-rate term
   (`reserved_memory_slots / (2 * classical_delay_s)`) with L2-R's
   AUDITED, corrected one (`docs/l3_attempt_rate_audit.md`, M6c: the
   naive round-trip multiplier of 2 undercounts Barret-Kok's real 3-round
   classical coordination protocol by ~3.66x on average; L2-R's
   `ATTEMPT_RATE_CONSERVATIVE_FACTOR=7.5` is reused here rather than a
   second, independently-tuned constant, so L2-R and L3-R share one
   validated correction, per the audit doc's closing recommendation).
3. Keeps the SAME Poisson delivered-pairs approximation family as
   L3-original (not a new stochastic model) - the only change is the
   corrected generation-rate INPUT to that model, which keeps the
   before/after comparison in P02B attributable to exactly one change,
   not entangled with a simultaneous change of approximation family.
   Sections 8-9 of the planner-study brief ask that the approach be
   chosen "by validated behavior, not complexity" - reusing the already-
   validated Poisson family satisfies that more directly than introducing
   an unvalidated binomial/negative-binomial/renewal/Monte-Carlo model
   for this first correction pass.

**What is explicitly NOT changed or newly validated here (documented, not
hidden):**
- `fidelity_success_probability` is still the deterministic 0/1 reuse of
  L2-R's `fidelity_feasible` (same simplification L3-original made from
  L2's estimate) - no independent fidelity-uncertainty model is
  introduced.
- Independence between fidelity-success and delivery-success when
  multiplying into `satisfaction_probability` is still ASSUMED, exactly
  as in L3-original - this audit/correction pass does not measure or
  relax that assumption. P02B's paired-trial design must check it
  empirically (planner-study brief section 9's explicit requirement),
  not take it on faith a second time.
- Whether correcting the attempt-rate bias actually improves the
  near-zero-bin miscalibration found in P02 (Discovery B) is an OPEN,
  unresolved question - `docs/l3_attempt_rate_audit.md`'s closing section
  explicitly declines to assume a direction. P02B's calibration-by-region
  analysis is what answers it, not this module.

See `docs/l3_resource_aware_model.md` for the full write-up.
"""
from __future__ import annotations

import time

from scipy import stats

from ...intent.models import EntanglementIntent
from ...network.capabilities import NetworkCapabilities
from ..feasibility import estimate_latency_s
from ..fidelity_estimation import ConservativeMinEstimator
from ..models import EstimatedMetrics, ExecutionPlan
from .base import evaluate_candidates, to_candidate_evaluation
from .l2_iterative import IterativeAnalyticalPurification
from .l2_resource_aware import ATTEMPT_RATE_CONSERVATIVE_FACTOR, estimate_resource_aware_plan
from .models import PlannerDecision, PlannerExplanation, PlanningContext, ProbabilisticPlanEstimate


def estimate_probabilistic_resource_aware_plan(
    capabilities: NetworkCapabilities,
    route: list[str],
    intent: EntanglementIntent,
    *,
    max_rounds: int = 8,
) -> ProbabilisticPlanEstimate:
    """L3-R's core per-route estimate - see the module docstring for what
    is reused from L2-R/L3-original vs. newly corrected here."""
    resource_estimate = estimate_resource_aware_plan(capabilities, route, intent, max_rounds=max_rounds)
    fidelity_success_probability = 1.0 if resource_estimate.fidelity_feasible else 0.0

    if resource_estimate.model_limit_hit or not resource_estimate.memory_feasible:
        # Deterministic L2-R gate failure - not a probability to estimate,
        # a structural impossibility (see module docstring, point 1).
        return ProbabilisticPlanEstimate(
            expected_delivered_pairs=0.0,
            delivered_pairs_variance=0.0,
            satisfaction_probability=0.0,
            fidelity_success_probability=fidelity_success_probability,
            delivery_success_probability=0.0,
            confidence_interval=(0.0, 0.0),
            estimated_completion_time_s=None,
            approximation_method=(
                f"deterministic L2-R gate short-circuit (rejection_reason="
                f"{resource_estimate.rejection_reason}) - see docs/l3_resource_aware_model.md"
            ),
        )

    expected_delivered_pairs = resource_estimate.estimated_final_pair_rate * intent.requirements.duration_s
    delivered_pairs_variance = expected_delivered_pairs  # Poisson approximation, same as L3-original

    min_delivered_pairs = intent.requirements.min_delivered_pairs or 1
    if expected_delivered_pairs <= 0:
        delivery_success_probability = 0.0
    else:
        delivery_success_probability = float(stats.poisson.sf(min_delivered_pairs - 1, expected_delivered_pairs))

    # Independence assumed here, unchanged from L3-original - see module
    # docstring's "what is explicitly NOT changed" section. Not
    # re-measured in this module; P02B must check it.
    satisfaction_probability = fidelity_success_probability * delivery_success_probability

    if expected_delivered_pairs > 0:
        lo = float(stats.poisson.ppf(0.025, expected_delivered_pairs))
        hi = float(stats.poisson.ppf(0.975, expected_delivered_pairs))
    else:
        lo = hi = 0.0

    estimated_completion_time_s = (
        min_delivered_pairs / resource_estimate.estimated_final_pair_rate
        if resource_estimate.estimated_final_pair_rate > 0 else None
    )

    return ProbabilisticPlanEstimate(
        expected_delivered_pairs=expected_delivered_pairs,
        delivered_pairs_variance=delivered_pairs_variance,
        satisfaction_probability=satisfaction_probability,
        fidelity_success_probability=fidelity_success_probability,
        delivery_success_probability=delivery_success_probability,
        confidence_interval=(lo, hi),
        estimated_completion_time_s=estimated_completion_time_s,
        approximation_method=(
            "Poisson delivered-pairs model (same approximation family as L3-original) with "
            f"L2-R's audited attempt-rate correction (naive rate / {ATTEMPT_RATE_CONSERVATIVE_FACTOR}, "
            "docs/l3_attempt_rate_audit.md) replacing L3-original's uncorrected 2x-round-trip attempt "
            "rate; memory/model-limit feasibility reused from L2-R's deterministic gates; independence "
            "between fidelity- and delivery-success still assumed, unmeasured - see "
            "docs/l3_resource_aware_model.md"
        ),
    )


class ProbabilisticResourceAwarePlanner:
    """L3-R: L3-original's admission-by-probability-threshold behavior,
    with the attempt-rate correction and L2-R's deterministic gates - see
    the module docstring."""

    name = "probabilistic_resource_aware"
    level = "L3-R"

    def __init__(self, *, admission_threshold: float = 0.5, max_rounds: int = 8):
        self._admission_threshold = admission_threshold
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
        purification_strategy = context.purification_strategy or IterativeAnalyticalPurification(
            max_rounds=self._max_rounds,
        )

        candidate_evaluations = []
        probabilistic_by_route: dict[tuple[str, ...], ProbabilisticPlanEstimate] = {}
        feasibility_by_route = {}
        if candidate_paths:
            evaluations = evaluate_candidates(
                network_state, candidate_paths, intent,
                purification_strategy=purification_strategy, fidelity_estimator=fidelity_estimator,
            )
            for route, result in zip(candidate_paths, evaluations):
                candidate_evaluations.append(to_candidate_evaluation(result))
                feasibility_by_route[tuple(route)] = result
                probabilistic_by_route[tuple(route)] = estimate_probabilistic_resource_aware_plan(
                    network_state, route, intent, max_rounds=self._max_rounds,
                )

        admissible = [
            (route, probabilistic_by_route[tuple(route)])
            for route in candidate_paths
            if probabilistic_by_route[tuple(route)].satisfaction_probability >= self._admission_threshold
        ]
        planning_wall_time_s = time.perf_counter() - t0

        if not admissible:
            best_route = max(
                candidate_paths, key=lambda r: probabilistic_by_route[tuple(r)].satisfaction_probability, default=None,
            ) if candidate_paths else None
            best_probability = (
                probabilistic_by_route[tuple(best_route)].satisfaction_probability if best_route else 0.0
            )
            reason = (
                f"no path found from '{intent.endpoints.source}' to '{intent.endpoints.destination}'"
                if not candidate_paths else
                f"best candidate's predicted satisfaction probability {best_probability:.3f} is below "
                f"admission_threshold={self._admission_threshold}"
            )
            plan = ExecutionPlan.infeasible(intent.id, reason)
            explanation = PlannerExplanation(
                summary=f"rejected: {reason}",
                decisive_factors=["predicted satisfaction probability below admission threshold"],
                limiting_constraints=[f"admission_threshold={self._admission_threshold}"],
                counterfactuals=[
                    "lower admission_threshold (accepts more risk of VIOLATED outcomes)",
                    "increase reserved_memory_slots or duration_s (raises expected_delivered_pairs)",
                    "reduce min_delivered_pairs or min_fidelity",
                ],
            )
            return PlannerDecision(
                planner_name=self.name, planner_level=self.level, feasible=False, selected_plan=plan,
                candidate_evaluations=candidate_evaluations, rejection_reason=reason,
                predicted_satisfaction_probability=best_probability if candidate_paths else None,
                assumptions=(
                    "Poisson delivered-pairs model with L2-R's audited attempt-rate correction "
                    "(docs/l3_attempt_rate_audit.md) and deterministic memory/model-limit gates reused "
                    "from L2-R - see docs/l3_resource_aware_model.md"
                ),
                planning_wall_time_s=planning_wall_time_s, explanation=explanation,
            )

        best_route, best_estimate = max(admissible, key=lambda item: item[1].satisfaction_probability)
        best_feasibility = feasibility_by_route[tuple(best_route)]

        latency_s = estimate_latency_s(network_state, best_route)
        estimated_fidelity = (
            best_feasibility.purified_fidelity_estimate if best_feasibility.requires_purification
            else best_feasibility.swap_only_fidelity
        )
        plan = ExecutionPlan(
            intent_id=intent.id, feasible=True, route=best_route,
            route_rationale=(
                f"selected by L3-R (predicted satisfaction probability {best_estimate.satisfaction_probability:.3f} "
                f">= admission_threshold={self._admission_threshold})"
            ),
            reservations=best_feasibility.reservations, requires_purification=best_feasibility.requires_purification,
            purification_rounds_estimate=best_feasibility.purification_rounds_estimate,
            estimated_metrics=EstimatedMetrics(fidelity=estimated_fidelity, latency_s=latency_s),
            fidelity_estimator=fidelity_estimator.name,
            fallback_routes=[r for r, _ in admissible if r != best_route],
        )
        explanation = PlannerExplanation(
            summary=(
                f"accepted route {' -> '.join(best_route)}, predicted satisfaction probability "
                f"{best_estimate.satisfaction_probability:.3f}, expected delivered pairs "
                f"{best_estimate.expected_delivered_pairs:.2f}"
            ),
            decisive_factors=[
                f"delivery_success_probability={best_estimate.delivery_success_probability:.3f}",
                f"fidelity_success_probability={best_estimate.fidelity_success_probability:.3f}",
            ],
            limiting_constraints=[f"admission_threshold={self._admission_threshold}"],
            uncertainty_notes=(
                f"95% CI for delivered pairs: [{best_estimate.confidence_interval[0]:.1f}, "
                f"{best_estimate.confidence_interval[1]:.1f}] (Poisson approximation); "
                f"estimated_completion_time_s={best_estimate.estimated_completion_time_s}"
            ),
        )
        return PlannerDecision(
            planner_name=self.name, planner_level=self.level, feasible=True, selected_plan=plan,
            candidate_evaluations=candidate_evaluations,
            predicted_satisfaction_probability=best_estimate.satisfaction_probability,
            predicted_delivered_pairs=best_estimate.expected_delivered_pairs,
            predicted_average_fidelity=estimated_fidelity, predicted_minimum_fidelity=estimated_fidelity,
            uncertainty=None,
            assumptions=(
                "Poisson delivered-pairs model with L2-R's audited attempt-rate correction "
                "(docs/l3_attempt_rate_audit.md) and deterministic memory/model-limit gates reused "
                "from L2-R - see docs/l3_resource_aware_model.md"
            ),
            planning_wall_time_s=planning_wall_time_s, explanation=explanation,
        )
