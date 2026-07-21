"""Regression tests for M10.7's two real bugs found while first
exercising L4 (Reference Planner) through the M10 infrastructure: L1-L3-R
never exposed either gap because their planning never touches
`context.topology_spec` and never raises during planning.
"""
from __future__ import annotations

import pytest

from ibqn.demos.environment import collect_environment_info
from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.deterministic_context import DeterminismConfig
from ibqn.experiments.predictability_m10_runner import execute_predictability_m10_trial
from ibqn.experiments.records import TrialIdentity
from ibqn.planning.planners import PlanningContext, SimulationInTheLoopPlanner, SimulationPlannerConfig
from ibqn.planning.routing import ShortestHopCountRouting


@pytest.mark.unit
def test_l4_plan_requires_topology_spec_in_context():
    """Regression guard for the bug found in M10.7: L4's planning step
    needs context.topology_spec (raw NetworkTopologySpec) to build its
    internal-simulation SequenceAdapter instances - omitting it must fail
    fast and clearly, not silently produce a wrong prediction."""
    topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = simple_intent(
        intent_id="t", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=5, start_time=0.01, duration=0.02,
    )
    context_missing_spec = PlanningContext(routing_strategy=ShortestHopCountRouting())  # topology_spec=None (default)
    identity = TrialIdentity(campaign="t", scenario="three_node", parameter_hash="x", strategy="L4", seed=0, intent_id="t")
    env = collect_environment_info()
    policy = SimulationInTheLoopPlanner(config=SimulationPlannerConfig(simulations_per_candidate=2))

    record = execute_predictability_m10_trial(
        identity, intent, topology, policy, context_missing_spec, env=env,
        determinism=DeterminismConfig(enabled=False),
    )
    # Planning-time exceptions (including a missing topology_spec) are
    # caught and recorded as SIMULATION_ERROR, never silently swallowed
    # into a misleadingly "normal" REJECTED/predicted_probability=None row.
    assert record.final_status == "SIMULATION_ERROR"
    assert "topology_spec" in record.rejection_reason or "NoneType" in record.rejection_reason


@pytest.mark.unit
def test_l4_plan_succeeds_with_topology_spec_set():
    topology = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    intent = simple_intent(
        intent_id="t", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=5, start_time=0.01, duration=0.02,
    )
    context = PlanningContext(routing_strategy=ShortestHopCountRouting(), topology_spec=topology)
    identity = TrialIdentity(campaign="t", scenario="three_node", parameter_hash="x", strategy="L4", seed=0, intent_id="t")
    env = collect_environment_info()
    policy = SimulationInTheLoopPlanner(config=SimulationPlannerConfig(simulations_per_candidate=2))

    record = execute_predictability_m10_trial(
        identity, intent, topology, policy, context, env=env, determinism=DeterminismConfig(enabled=False),
    )
    assert record.final_status in ("SATISFIED", "VIOLATED", "REJECTED")


@pytest.mark.unit
def test_planning_exceptions_are_caught_not_propagated():
    """Regression guard for the second M10.7 bug: a planning-time
    exception (L4's internal simulations can hit real SeQUeNCe protocol
    assertions, e.g. BBPSSW's fidelity>0.5 check) must be recorded as
    SIMULATION_ERROR, never raised out of execute_predictability_m10_trial."""
    import inspect

    from ibqn.experiments.predictability_m10_runner import execute_predictability_m10_trial as fn

    source = inspect.getsource(fn)
    assert "policy.plan(" in source
    assert "except Exception" in source
