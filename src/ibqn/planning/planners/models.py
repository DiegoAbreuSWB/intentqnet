"""Shared result/context types for the `IntentPlannerPolicy` family (planner
study, M1). These wrap - never replace - `planning.models.ExecutionPlan`,
which stays the one type `SequenceExecutor.deploy()` consumes; every policy
below still produces a real `ExecutionPlan` inside its `PlannerDecision`.

Fields a given planner level cannot predict are `None`, never `0` or a
guessed value (section 3 of the planner-study brief) - e.g. L1 never
predicts `predicted_satisfaction_probability` or `predicted_delivered_pairs`,
so those stay `None` on its decisions, not a placeholder number.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..models import ExecutionPlan


@dataclass(frozen=True)
class CandidateEvaluation:
    """One candidate route's outcome, independent of which planner level
    produced it - `extra` carries level-specific detail (e.g. L2's
    `IterativePurificationEstimate`) without forcing every level to share
    the same rich schema."""

    route: list[str]
    feasible: bool
    reason: str = ""
    predicted_fidelity: float | None = None
    predicted_delivered_pairs: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UncertaintyEstimate:
    """Populated from L5 onward (section 11 of the planner-study brief).
    L1-L4 leave every field `None` - there is no meaningful epistemic/
    aleatoric decomposition for a deterministic analytical formula or a
    fixed-K internal simulation batch in the sense L5's OOD detector needs;
    reporting a fabricated number here would misrepresent the planner's own
    method (see docs/planner_ood_policy.md, once L5 exists)."""

    confidence: float | None = None
    epistemic_uncertainty: float | None = None
    aleatoric_uncertainty: float | None = None
    ood_score: float | None = None
    is_ood: bool | None = None


@dataclass(frozen=True)
class PlannerExplanation:
    """Every planner level must produce one (section 13). What populates
    `decisive_factors`/`limiting_constraints` differs by level - L1/L2 use
    the closed-form fidelity/resource formulas, L3 its probability
    components, L4 its simulation distribution, L5 its feature importances
    - but the shape stays the same so downstream analysis never special-
    cases the planner level just to read an explanation."""

    summary: str
    decisive_factors: list[str] = field(default_factory=list)
    limiting_constraints: list[str] = field(default_factory=list)
    uncertainty_notes: str = ""
    counterfactuals: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlannerDecision:
    """The common output of every `IntentPlannerPolicy.plan()` call -
    section 3 of the planner-study brief. `selected_plan` is a real
    `ExecutionPlan` (the exact type `SequenceExecutor.deploy()` already
    consumes), so a `PlannerDecision` is always deployable without any
    adapter layer between the planner family and the rest of IBQN."""

    planner_name: str
    planner_level: str
    feasible: bool
    selected_plan: ExecutionPlan
    candidate_evaluations: list[CandidateEvaluation] = field(default_factory=list)
    predicted_satisfaction_probability: float | None = None
    predicted_delivered_pairs: float | None = None
    predicted_average_fidelity: float | None = None
    predicted_minimum_fidelity: float | None = None
    predicted_throughput: float | None = None
    uncertainty: UncertaintyEstimate | None = None
    rejection_reason: str | None = None
    assumptions: str = ""
    planning_wall_time_s: float = 0.0
    explanation: PlannerExplanation | None = None


@dataclass(frozen=True)
class PlanningContext:
    """Planner-independent knobs shared by every `IntentPlannerPolicy.plan()`
    call. `operational_seed` exists ONLY for provenance/logging by planners
    that don't simulate (L1-L3) and for validation tests to assert L4/L5
    never read it for their own internal estimation - see
    `tests/planning/planners/test_seed_isolation.py` and
    docs/planner_split_protocols.md. No planner may derive its own
    randomness from this field; L4's internal simulation seeds are derived
    from the intent/topology/config instead (see
    `planning.planners.l4_simulation`, added after checkpoint 1)."""

    routing_strategy: Any
    """A `planning.routing.RoutingStrategy` instance - typed `Any` here to
    avoid a circular import; every concrete policy imports the real type."""
    purification_strategy: Any = None
    fidelity_estimator: Any = None
    operational_seed: int | None = None
    max_candidates: int = 3
    topology_spec: Any = None
    """The raw `network.topology.NetworkTopologySpec` (not just the
    `NetworkCapabilities` view already passed to `plan()` as
    `network_state`) - `None` for L1-L3, which never need to construct a
    `SequenceAdapter` themselves. Required by L4
    (`planning.planners.l4_simulation`), which runs real internal
    simulations at planning time and therefore needs the full spec to
    build fresh `SequenceAdapter` instances."""


@dataclass(frozen=True)
class ProbabilisticPlanEstimate:
    """L3's output (planner-family study, M5) - see
    docs/l3_probabilistic_model.md for the exact formulas and their
    physical grounding (SeQUeNCe's real BSM success rate, the real
    Dur-Briegel purification success-probability formula, real memory/
    classical-delay parameters). Every field here is an APPROXIMATION
    with documented assumptions, never a claim of matching SeQUeNCe's
    exact event-driven dynamics - `approximation_method` names exactly
    which simplifications were made, so a low Brier score / large
    calibration error found during P02 has a clear, referenceable cause
    to check first."""

    expected_delivered_pairs: float
    delivered_pairs_variance: float
    satisfaction_probability: float
    fidelity_success_probability: float
    delivery_success_probability: float
    confidence_interval: tuple[float, float]
    approximation_method: str
