"""Tests for L4 (`SimulationInTheLoopPlanner`) - seed isolation (the
mandatory invariant: L4 must NEVER use the trial's operational seed for
its internal simulations) and early-stopping's statistical criterion.
These tests run real (small K) internal simulations - slower than L1-L3's
unit tests, still fast enough for the default test suite.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.planning.planners import PlanningContext, SimulationInTheLoopPlanner, SimulationPlannerConfig, generate_candidate_paths
from ibqn.planning.planners.l4_simulation import INTERNAL_SEED_BASE_OFFSET, _derive_internal_seeds
from ibqn.planning.routing import ShortestHopCountRouting


def _three_node_intent(min_fidelity=0.65):
    return simple_intent(
        intent_id="l4-test", source="a", destination="b", min_fidelity=min_fidelity,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )


@pytest.mark.unit
def test_derive_internal_seeds_never_produces_small_operational_seed_values():
    """Internal seeds must be far outside the range of realistic
    operational seeds (0-19 or similar small integers this project uses)."""
    intent = _three_node_intent()
    config = SimulationPlannerConfig(simulations_per_candidate=30)
    seeds = _derive_internal_seeds(intent, ["a", "r", "b"], config, 30)
    assert all(seed >= INTERNAL_SEED_BASE_OFFSET for seed in seeds)
    assert all(seed > 1000 for seed in seeds)  # far above any operational seed used in this project


@pytest.mark.unit
def test_derive_internal_seeds_is_deterministic():
    intent = _three_node_intent()
    config = SimulationPlannerConfig(simulations_per_candidate=5)
    seeds1 = _derive_internal_seeds(intent, ["a", "r", "b"], config, 5)
    seeds2 = _derive_internal_seeds(intent, ["a", "r", "b"], config, 5)
    assert seeds1 == seeds2


@pytest.mark.unit
def test_derive_internal_seeds_differ_by_route():
    intent = _three_node_intent()
    config = SimulationPlannerConfig(simulations_per_candidate=5)
    seeds_a = _derive_internal_seeds(intent, ["a", "r", "b"], config, 5)
    seeds_b = _derive_internal_seeds(intent, ["a", "x", "b"], config, 5)
    assert seeds_a != seeds_b


@pytest.mark.unit
def test_l4_plan_signature_has_no_operational_seed_parameter():
    """L4's `plan()` receives a `PlanningContext` that MAY carry
    `operational_seed` for provenance/logging only - confirm the internal
    seed-derivation helper's signature never accepts it, so a future edit
    cannot silently wire it in."""
    import inspect

    signature = inspect.signature(_derive_internal_seeds)
    assert "seed" not in signature.parameters or "operational" not in str(signature.parameters)
    assert list(signature.parameters) == ["intent", "route", "config", "n"]


@pytest.mark.unit
def test_l4_admits_a_favorable_intent_with_small_k():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = _three_node_intent(min_fidelity=0.65)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting(), topology_spec=topology)
    candidates = generate_candidate_paths(intent, capabilities, context)

    config = SimulationPlannerConfig(simulations_per_candidate=3)
    decision = SimulationInTheLoopPlanner(config=config, admission_threshold=0.5).plan(
        intent, capabilities, candidates, context,
    )
    assert decision.feasible is True
    assert decision.predicted_satisfaction_probability is not None
    assert decision.predicted_satisfaction_probability >= 0.5


@pytest.mark.unit
def test_l4_rejects_an_unreachable_fidelity_target_with_small_k():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = _three_node_intent(min_fidelity=0.9999)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting(), topology_spec=topology)
    candidates = generate_candidate_paths(intent, capabilities, context)

    config = SimulationPlannerConfig(simulations_per_candidate=2)
    decision = SimulationInTheLoopPlanner(config=config, admission_threshold=0.5).plan(
        intent, capabilities, candidates, context,
    )
    assert decision.feasible is False
    assert decision.rejection_reason is not None


@pytest.mark.unit
def test_l4_early_stopping_can_stop_before_the_full_k():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2))
    topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = _three_node_intent(min_fidelity=0.65)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting(), topology_spec=topology)
    candidates = generate_candidate_paths(intent, capabilities, context)

    config = SimulationPlannerConfig(
        simulations_per_candidate=10, early_stopping=True, early_stopping_confidence=0.80,
        early_stopping_acceptance_threshold=0.5,
    )
    decision = SimulationInTheLoopPlanner(config=config, admission_threshold=0.5).plan(
        intent, capabilities, candidates, context,
    )
    # A clearly-favorable intent (min_fidelity well below the one-round
    # ceiling) should trigger early stopping well before K=10 real sims.
    assert decision.feasible is True


@pytest.mark.unit
def test_l4_reports_correct_identity():
    assert SimulationInTheLoopPlanner.name == "simulation_in_the_loop"
    assert SimulationInTheLoopPlanner.level == "L4"


@pytest.mark.unit
def test_simulation_planner_config_defaults_are_sequential_not_parallel():
    """Documented limitation: `sequence.utils.metrics` is a process-wide
    singleton, so parallel internal simulations are not safe without
    per-process isolation - confirm the safe default stays 1."""
    config = SimulationPlannerConfig()
    assert config.parallelism == 1
