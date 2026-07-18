"""L3 - probabilistic analytical planner (planner-family study, M5).

Predicts P(satisfied), P(delivered_pairs >= min_delivered_pairs), and
P(average_fidelity >= min_fidelity) - not just a feasible/infeasible
point estimate like L1/L2. See `docs/l3_probabilistic_model.md` for the
full derivation; summary of what is and is NOT modeled here:

**Grounded in real SeQUeNCe physics (not invented):**
- Elementary-generation success probability per attempt: photon survival
  over the fiber (`1 - loss`, `sequence.components.optical_channel.
  QuantumChannel.loss = 1 - 10**(-distance*attenuation/10)`, with the BSM
  at the link midpoint splitting distance in half per leg - see
  `network.topology.QuantumLinkSpec`'s docstring) times the linear-optics
  Bell-state-measurement success rate (`sequence.components.bsm`'s
  `success_rate: float = 0.5` default).
- Purification round success probability: the Dur-Briegel formula's OWN
  denominator (`f**2 + 2*f*(1-f)/3 + 5*((1-f)/3)**2` -
  `bbpssw_circuit.BBPSSWCircuit.improved_fidelity`'s normalization term IS
  the round success probability in the Dur-Briegel 2007 derivation this
  project already cites).
- Swap success probability: exactly 1 in this project's configuration -
  `sequence.topology.node`'s `swapping_success_prob` defaults to 1 and
  `network.sequence_adapter` never overrides it (only
  `swapping_degradation`, a FIDELITY factor, is set) - confirmed by
  reading both modules, not assumed.
- Attempt timing: `reserved_memory_slots` parallel attempt streams, each
  gated by one classical round-trip (`2 * classical_delay_s` per attempt
  cycle) - a real, topology-declared parameter
  (`NetworkCapabilities.classical_delay_s`), not memory's raw 80 MHz
  excitation frequency, which is negligible next to classical signaling
  time at the distances this project's topologies use.

**Explicitly approximate, documented simplifying assumptions (not
SeQUeNCe's exact event-driven dynamics):**
- A "raw path pair" is treated as requiring every hop to succeed in the
  same attempt cycle (real SeQUeNCe generates per-link independently and
  buffers completed links until a swap partner is ready - this
  overestimates correlation, thus likely UNDERESTIMATES achievable
  throughput on multi-hop routes; P02 measures how large this gap is).
- Purification retries are modeled as an EFFECTIVE per-round pair cost
  (`2 / round_success_probability`), not as an explicit retry loop -
  reduces to L2's deterministic `2**rounds` cost only in the limit
  `round_success_probability -> 1`.
- `fidelity_success_probability` is NOT independently modeled from first
  principles - it is set to 1.0 if L2's deterministic iterative estimate
  reaches the target (within the same `max_rounds`/`max_pair_cost`) and
  0.0 otherwise. This reuses L2's checkpoint-1 empirical finding (its
  fidelity estimate matched observed fidelity almost exactly on both
  uniform topologies tested) rather than inventing a second, unvalidated
  fidelity-uncertainty model; P02 will show if this holds outside that
  regime.
- `delivered_pairs` is modeled as Poisson-distributed (a standard
  approximation for a rare, memoryless success-counting process) - real
  delivery counts may be over- or under-dispersed relative to Poisson;
  not verified here.
- Independence assumed between fidelity success and delivery success when
  combining into `satisfaction_probability` - both are driven by the same
  underlying route/attempt process, so this likely UNDERSTATES their true
  (positive) correlation.

Reuses L2's `IterativeAnalyticalPurification` for the rounds-needed
estimate (no duplicated purification-round logic), and the existing
`base.generate_candidate_paths`/`evaluate_candidates` for routing/resource
checks (no duplicated candidate generation or memory-feasibility logic).
"""
from __future__ import annotations

import time

from scipy import stats

from ...intent.models import EntanglementIntent
from ...network.capabilities import NetworkCapabilities
from ..feasibility import estimate_latency_s, estimate_swap_only_fidelity
from ..fidelity_estimation import ConservativeMinEstimator
from ..models import EstimatedMetrics, ExecutionPlan
from .base import evaluate_candidates, to_candidate_evaluation
from .l2_iterative import IterativeAnalyticalPurification
from .models import PlannerDecision, PlannerExplanation, PlanningContext, ProbabilisticPlanEstimate

BSM_SUCCESS_RATE = 0.5
"""`sequence.components.bsm`'s linear-optics Bell-state-measurement
success-rate default - see the module docstring."""

PAIR_CONSUMPTION_PER_ROUND = 2


def _link_success_probability(distance_m: float, attenuation_db_per_m: float) -> float:
    """Probability that ONE elementary-generation attempt on this link
    succeeds: photon transmission over the full logical distance (both
    BSM-to-router legs combine multiplicatively to the full-distance
    transmission probability) times the BSM success rate."""
    transmission = 10 ** (-(distance_m * attenuation_db_per_m) / 10)
    return transmission * BSM_SUCCESS_RATE


def _route_raw_pair_probability(capabilities: NetworkCapabilities, route: list[str]) -> float:
    """Probability that a single attempt cycle produces one raw (pre-
    purification, pre-swap) end-to-end pair: every hop's elementary
    generation must succeed (swap itself never fails in this project's
    configuration - see the module docstring)."""
    probability = 1.0
    for a, b in zip(route, route[1:]):
        link = capabilities.link(a, b)
        probability *= _link_success_probability(link.distance_m, link.attenuation_db_per_m)
    return probability


def _purification_round_success_probability(fidelity: float) -> float:
    """The Dur-Briegel BBPSSW round success probability - the exact
    denominator of `BBPSSWCircuit.improved_fidelity` (see the module
    docstring)."""
    return fidelity**2 + 2 * fidelity * (1 - fidelity) / 3 + 5 * ((1 - fidelity) / 3) ** 2


def estimate_probabilistic_plan(
    capabilities: NetworkCapabilities,
    route: list[str],
    intent: EntanglementIntent,
    *,
    max_rounds: int = 8,
) -> ProbabilisticPlanEstimate:
    """The core L3 estimate for one candidate `route` - see the module
    docstring for exactly what is/isn't modeled."""
    swap_only_fidelity, _ = estimate_swap_only_fidelity(capabilities, route)
    target_fidelity = intent.requirements.min_fidelity
    allow_purification = intent.policy.allow_purification

    purification = IterativeAnalyticalPurification(max_rounds=max_rounds)
    purification.decide(swap_only_fidelity, target_fidelity, allow_purification)
    estimate = purification.last_estimate

    fidelity_success_probability = 1.0 if estimate.target_reached else 0.0

    if not estimate.rounds:
        effective_pair_cost = 1.0
    else:
        effective_pair_cost = 1.0
        for round_estimate in estimate.rounds:
            round_success = _purification_round_success_probability(round_estimate.input_fidelity)
            round_success = max(round_success, 1e-6)  # avoid division by zero on a degenerate formula input
            effective_pair_cost *= PAIR_CONSUMPTION_PER_ROUND / round_success

    raw_pair_probability = _route_raw_pair_probability(capabilities, route)
    attempt_rate = intent.requirements.reserved_memory_slots / (2 * capabilities.classical_delay_s)
    expected_raw_pairs = attempt_rate * intent.requirements.duration_s * raw_pair_probability
    expected_delivered_pairs = expected_raw_pairs / effective_pair_cost
    delivered_pairs_variance = expected_delivered_pairs  # Poisson approximation - see module docstring

    min_delivered_pairs = intent.requirements.min_delivered_pairs or 1
    if expected_delivered_pairs <= 0:
        delivery_success_probability = 0.0
    else:
        delivery_success_probability = float(stats.poisson.sf(min_delivered_pairs - 1, expected_delivered_pairs))

    satisfaction_probability = fidelity_success_probability * delivery_success_probability

    if expected_delivered_pairs > 0:
        lo = float(stats.poisson.ppf(0.025, expected_delivered_pairs))
        hi = float(stats.poisson.ppf(0.975, expected_delivered_pairs))
    else:
        lo = hi = 0.0

    return ProbabilisticPlanEstimate(
        expected_delivered_pairs=expected_delivered_pairs,
        delivered_pairs_variance=delivered_pairs_variance,
        satisfaction_probability=satisfaction_probability,
        fidelity_success_probability=fidelity_success_probability,
        delivery_success_probability=delivery_success_probability,
        confidence_interval=(lo, hi),
        approximation_method=(
            "Poisson delivered-pairs model; raw-pair probability = product of per-hop "
            "(photon transmission x BSM success rate 0.5); effective purification pair cost = "
            "product over rounds of (2 / Dur-Briegel round success probability); fidelity success "
            "is L2's deterministic reachability (0/1), not independently modeled - see "
            "docs/l3_probabilistic_model.md"
        ),
    )


class ProbabilisticPlanner:
    """L3: predicts P(satisfied) per candidate route and admits the best
    candidate whose predicted satisfaction probability clears
    `admission_threshold` - see `docs/l3_probabilistic_model.md` for
    threshold calibration guidance (never chosen from a test set)."""

    name = "probabilistic"
    level = "L3"

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
                probabilistic_by_route[tuple(route)] = estimate_probabilistic_plan(
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
                    "Poisson delivered-pairs model, effective purification pair cost via Dur-Briegel round "
                    "success probability - see docs/l3_probabilistic_model.md"
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
                f"selected by L3 (predicted satisfaction probability {best_estimate.satisfaction_probability:.3f} "
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
                f"{best_estimate.confidence_interval[1]:.1f}] (Poisson approximation)"
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
                "Poisson delivered-pairs model, effective purification pair cost via Dur-Briegel round "
                "success probability - see docs/l3_probabilistic_model.md"
            ),
            planning_wall_time_s=planning_wall_time_s, explanation=explanation,
        )
