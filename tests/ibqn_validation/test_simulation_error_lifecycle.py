"""IBQN Validation-B1: confirms the SIMULATION_ERROR lifecycle gap found in
docs/paper_ibqn_validation/simulation_error_trace.md is fixed - an intent
whose reservation was already approved (ACTIVE) but whose simulated
execution then raises must reach a terminal IntentStatus.FAILED, not stay
stuck in ACTIVE forever. Uses a deliberately injected failure (monkeypatched
adapter.run) rather than trying to reproduce the real BBPSSW assertion,
since the point under test is the lifecycle/executor's exception handling,
not SeQUeNCe's internal protocol code."""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.execution.sequence_executor import SequenceExecutor
from ibqn.intent.models import IntentStatus
from ibqn.intent.repository import IntentRepository
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.planning.planner import IntentPlanner


def _build_deployed_executor():
    """Builds a real executor with one feasible, deployed intent - stops
    just short of calling `run()`, so the test controls exactly when/how
    the simulated failure happens."""
    spec = three_node_spec()
    capabilities = NetworkCapabilities(spec)
    adapter = SequenceAdapter(spec, seed=0)
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    planner = IntentPlanner(capabilities)

    intent = simple_intent(intent_id="sim-error-test", source="a", destination="b", min_fidelity=0.6, requested_pairs=5)
    plan = planner.plan(intent)
    assert plan.feasible, "test setup requires a feasible plan (deploy must reach DEPLOYING, not REJECTED)"
    executor.deploy(intent, plan)

    return executor, repository, intent


@pytest.mark.unit
def test_state_before_run_is_deploying_not_yet_terminal():
    executor, repository, intent = _build_deployed_executor()
    record = repository.get(intent.id)
    assert record.lifecycle.status == IntentStatus.DEPLOYING
    assert not record.lifecycle.is_terminal


@pytest.mark.unit
def test_exception_during_run_after_active_reaches_failed_not_stuck(monkeypatch):
    """The scenario the trace identified as a genuine gap: the reservation
    is already ACTIVE (approved) when SeQUeNCe raises mid-simulation."""
    executor, repository, intent = _build_deployed_executor()

    # Simulate what a real run() does up to the point of approval, without
    # actually running the timeline: the reservation was approved.
    repository.transition(intent.id, IntentStatus.ACTIVE, "test setup: reservation approved", sim_time=0.01)
    assert repository.get(intent.id).lifecycle.status == IntentStatus.ACTIVE

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated SeQUeNCe-internal protocol assertion")

    monkeypatch.setattr(executor._adapter, "run", _raise)

    with pytest.raises(RuntimeError, match="simulated SeQUeNCe-internal protocol assertion"):
        executor.run()

    record = repository.get(intent.id)
    assert record.lifecycle.status == IntentStatus.FAILED, (
        "intent must not remain stuck in ACTIVE after a mid-simulation exception"
    )
    assert record.lifecycle.is_terminal
    assert record.result is not None
    assert record.result.final_status == IntentStatus.FAILED


@pytest.mark.unit
def test_exception_during_run_before_active_reaches_failed(monkeypatch):
    """Same failure, but injected before the reservation was ever approved
    (intent still sitting in DEPLOYING) - the pre-existing DEPLOYING->FAILED
    edge already covered this case; confirms the new exception handling
    doesn't regress it."""
    executor, repository, intent = _build_deployed_executor()
    assert repository.get(intent.id).lifecycle.status == IntentStatus.DEPLOYING

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated failure before approval")

    monkeypatch.setattr(executor._adapter, "run", _raise)

    with pytest.raises(RuntimeError):
        executor.run()

    record = repository.get(intent.id)
    assert record.lifecycle.status == IntentStatus.FAILED
    assert record.lifecycle.is_terminal


@pytest.mark.unit
def test_exception_after_already_terminal_does_not_raise_invalid_transition(monkeypatch):
    """If the intent already reached a terminal status (e.g. FAILED via the
    reservation-rejected path) before run() is ever called, the exception
    handler must not attempt a second, invalid transition and crash with
    InvalidTransitionError while already unwinding a real exception."""
    executor, repository, intent = _build_deployed_executor()
    repository.transition(intent.id, IntentStatus.FAILED, "test setup: already terminal", sim_time=0.0)
    assert repository.get(intent.id).lifecycle.is_terminal

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated failure after intent already terminal")

    monkeypatch.setattr(executor._adapter, "run", _raise)

    with pytest.raises(RuntimeError, match="simulated failure after intent already terminal"):
        executor.run()

    # still FAILED, not re-transitioned or corrupted
    assert repository.get(intent.id).lifecycle.status == IntentStatus.FAILED


@pytest.mark.unit
def test_successful_run_is_unaffected_by_the_new_exception_handling():
    """The happy path (no exception) must behave exactly as before: ACTIVE
    reached via the real get_reservation_result callback, no FAILED
    transition attempted."""
    executor, repository, intent = _build_deployed_executor()

    executor.run()

    record = repository.get(intent.id)
    assert record.lifecycle.status in (IntentStatus.ACTIVE, IntentStatus.SATISFIED, IntentStatus.VIOLATED)
    assert record.lifecycle.status != IntentStatus.FAILED


@pytest.mark.unit
def test_real_run_scenario_pipeline_still_reaches_satisfied_end_to_end():
    """Regression guard: the ordinary run_scenario pipeline (which does not
    inject any failure) must still work identically after this fix -
    confirms the ACTIVE->FAILED edge addition and the executor.run() change
    do not alter any existing, correct control flow."""
    from ibqn.demos.scenarios import ad_hoc_scenario
    from ibqn.experiments.runner import run_scenario

    spec = three_node_spec()
    intent = simple_intent(intent_id="sim-error-regression", source="a", destination="b", min_fidelity=0.6, requested_pairs=5)
    scenario = ad_hoc_scenario(spec, [intent], seed=0, name="sim-error-regression-scenario")

    result = run_scenario(scenario, seed=0)
    trial = result.get(intent.id)
    assert trial.final_status in (IntentStatus.SATISFIED, IntentStatus.VIOLATED)
