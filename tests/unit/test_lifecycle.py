"""Tests for `ibqn.intent.lifecycle` (state machine) and
`ibqn.intent.repository` (intent bookkeeping), see docs/execution_lifecycle.md.
"""
import pytest

from ibqn.intent.lifecycle import IntentLifecycle, InvalidTransitionError, StatusTransition
from ibqn.intent.models import (
    EntanglementIntent,
    IntentEndpoints,
    IntentRequirements,
    IntentStatus,
    IntentValidation,
    SuccessCondition,
)
from ibqn.intent.repository import IntentRepository


def build_intent(intent_id="intent-001") -> EntanglementIntent:
    return EntanglementIntent(
        id=intent_id,
        endpoints=IntentEndpoints(source="node_a", destination="node_b"),
        requirements=IntentRequirements(
            min_fidelity=0.9, min_throughput=10, max_latency=0.5,
            requested_pairs=100, start_time=0, duration=10,
        ),
        validation=IntentValidation(
            metrics=["delivered_pairs"],
            success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=100)],
        ),
    )


@pytest.mark.unit
def test_new_lifecycle_starts_at_received_with_one_history_entry():
    lifecycle = IntentLifecycle("intent-001")

    assert lifecycle.status == IntentStatus.RECEIVED
    assert len(lifecycle.history) == 1
    assert lifecycle.history[0].from_status is None
    assert lifecycle.history[0].to_status == IntentStatus.RECEIVED
    assert lifecycle.is_terminal is False


@pytest.mark.unit
def test_full_happy_path_transition_sequence():
    lifecycle = IntentLifecycle("intent-001")
    happy_path = [
        IntentStatus.VALIDATED,
        IntentStatus.PLANNING,
        IntentStatus.PLANNED,
        IntentStatus.DEPLOYING,
        IntentStatus.ACTIVE,
        IntentStatus.SATISFIED,
        IntentStatus.COMPLETED,
    ]
    for i, status in enumerate(happy_path):
        lifecycle.transition(status, f"step {i}", sim_time=float(i))

    assert lifecycle.status == IntentStatus.COMPLETED
    assert lifecycle.is_terminal is True
    assert [t.to_status for t in lifecycle.history] == [IntentStatus.RECEIVED, *happy_path]
    assert lifecycle.history[-1].sim_time == float(len(happy_path) - 1)


@pytest.mark.unit
def test_reconciliation_loop_returns_to_planning():
    lifecycle = IntentLifecycle("intent-001")
    for status in (
        IntentStatus.VALIDATED, IntentStatus.PLANNING, IntentStatus.PLANNED,
        IntentStatus.DEPLOYING, IntentStatus.ACTIVE, IntentStatus.VIOLATED,
    ):
        lifecycle.transition(status, "progress")

    lifecycle.transition(IntentStatus.RECONCILING, "violation detected")
    lifecycle.transition(IntentStatus.PLANNING, "recompiling with a new plan")

    assert lifecycle.status == IntentStatus.PLANNING
    assert lifecycle.is_terminal is False


@pytest.mark.unit
def test_illegal_transition_is_rejected_and_does_not_mutate_state():
    lifecycle = IntentLifecycle("intent-001")

    with pytest.raises(InvalidTransitionError):
        lifecycle.transition(IntentStatus.ACTIVE, "skip ahead")  # RECEIVED -> ACTIVE is not allowed

    assert lifecycle.status == IntentStatus.RECEIVED
    assert len(lifecycle.history) == 1  # rejected transition must not be recorded


@pytest.mark.unit
def test_terminal_status_rejects_any_further_transition():
    lifecycle = IntentLifecycle("intent-001")
    lifecycle.transition(IntentStatus.REJECTED, "infeasible")

    assert lifecycle.is_terminal is True
    with pytest.raises(InvalidTransitionError):
        lifecycle.transition(IntentStatus.VALIDATED, "retry")


@pytest.mark.unit
@pytest.mark.parametrize(
    "status",
    [
        IntentStatus.RECEIVED, IntentStatus.VALIDATED, IntentStatus.PLANNING,
        IntentStatus.PLANNED, IntentStatus.DEPLOYING, IntentStatus.ACTIVE,
        IntentStatus.SATISFIED, IntentStatus.VIOLATED, IntentStatus.RECONCILING,
    ],
)
def test_cancelled_is_reachable_from_every_non_terminal_status(status):
    lifecycle = IntentLifecycle("intent-001")
    lifecycle.status = status  # jump directly to the status under test
    lifecycle.transition(IntentStatus.CANCELLED, "user cancelled")
    assert lifecycle.status == IntentStatus.CANCELLED


@pytest.mark.unit
def test_status_transition_records_are_immutable():
    from pydantic import ValidationError

    transition = StatusTransition(from_status=None, to_status=IntentStatus.RECEIVED, reason="x")
    with pytest.raises(ValidationError):
        transition.reason = "y"


# --- IntentRepository -------------------------------------------------------

@pytest.mark.unit
def test_repository_add_and_get_round_trip():
    repo = IntentRepository()
    intent = build_intent()

    record = repo.add(intent, sim_time=0.0)

    assert record.intent is intent
    assert record.lifecycle.status == IntentStatus.RECEIVED
    assert repo.get("intent-001") is record


@pytest.mark.unit
def test_repository_rejects_duplicate_intent_id():
    repo = IntentRepository()
    repo.add(build_intent("intent-001"))

    with pytest.raises(ValueError, match="already registered"):
        repo.add(build_intent("intent-001"))


@pytest.mark.unit
def test_repository_get_missing_intent_raises_key_error():
    repo = IntentRepository()
    with pytest.raises(KeyError, match="no intent registered"):
        repo.get("does-not-exist")


@pytest.mark.unit
def test_repository_transition_populates_result_on_terminal_status():
    repo = IntentRepository()
    repo.add(build_intent())

    repo.transition("intent-001", IntentStatus.VALIDATED, "ok")
    repo.transition("intent-001", IntentStatus.PLANNING, "ok")
    repo.transition("intent-001", IntentStatus.REJECTED, "no viable plan", sim_time=1.5)

    record = repo.get("intent-001")
    assert record.lifecycle.status == IntentStatus.REJECTED
    assert record.result is not None
    assert record.result.satisfied is False
    assert record.result.reason == "no viable plan"
    assert record.result.sim_time_completed == 1.5


@pytest.mark.unit
def test_repository_transition_leaves_result_none_while_non_terminal():
    repo = IntentRepository()
    repo.add(build_intent())
    repo.transition("intent-001", IntentStatus.VALIDATED, "ok")

    assert repo.get("intent-001").result is None
