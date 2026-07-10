"""State machine governing how an `EntanglementIntent` moves through its
lifecycle. Every transition is validated against an explicit allowed-edges
graph, carries a simulation timestamp and a reason, and is appended to an
immutable history (never overwritten) - see docs/execution_lifecycle.md.
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from .models import IntentStatus

TERMINAL_STATUSES: frozenset[IntentStatus] = frozenset(
    {IntentStatus.REJECTED, IntentStatus.FAILED, IntentStatus.COMPLETED, IntentStatus.CANCELLED}
)

# Every non-terminal status may additionally transition to CANCELLED; that
# edge is added programmatically below to avoid repeating it 9 times.
_BASE_ALLOWED_TRANSITIONS: dict[IntentStatus, frozenset[IntentStatus]] = {
    IntentStatus.RECEIVED: frozenset({IntentStatus.VALIDATED, IntentStatus.REJECTED}),
    IntentStatus.VALIDATED: frozenset({IntentStatus.PLANNING}),
    IntentStatus.PLANNING: frozenset({IntentStatus.PLANNED, IntentStatus.REJECTED}),
    IntentStatus.PLANNED: frozenset({IntentStatus.DEPLOYING}),
    IntentStatus.DEPLOYING: frozenset({IntentStatus.ACTIVE, IntentStatus.FAILED}),
    IntentStatus.ACTIVE: frozenset({IntentStatus.SATISFIED, IntentStatus.VIOLATED}),
    IntentStatus.SATISFIED: frozenset({IntentStatus.COMPLETED, IntentStatus.VIOLATED}),
    IntentStatus.VIOLATED: frozenset({IntentStatus.RECONCILING, IntentStatus.FAILED}),
    IntentStatus.RECONCILING: frozenset({IntentStatus.PLANNING, IntentStatus.FAILED}),
}

ALLOWED_TRANSITIONS: dict[IntentStatus, frozenset[IntentStatus]] = {
    status: (edges | {IntentStatus.CANCELLED}) if status not in TERMINAL_STATUSES else edges
    for status, edges in {
        **{status: frozenset() for status in IntentStatus},
        **_BASE_ALLOWED_TRANSITIONS,
    }.items()
}


class InvalidTransitionError(Exception):
    """Raised when a transition is not allowed from the current status, or
    the intent is already in a terminal status."""


class StatusTransition(BaseModel):
    """One immutable entry in an intent's lifecycle history."""

    model_config = ConfigDict(frozen=True)

    from_status: IntentStatus | None  # None only for the initial RECEIVED entry
    to_status: IntentStatus
    reason: str
    sim_time: float | None = Field(default=None, description="seconds, simulation time of the transition")
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IntentLifecycle:
    """Tracks the current status and full transition history of one intent."""

    def __init__(self, intent_id: str, *, sim_time: float | None = None, reason: str = "intent received"):
        self.intent_id = intent_id
        self.status: IntentStatus = IntentStatus.RECEIVED
        self.history: list[StatusTransition] = [
            StatusTransition(from_status=None, to_status=IntentStatus.RECEIVED, reason=reason, sim_time=sim_time)
        ]

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def transition(self, to_status: IntentStatus, reason: str, *, sim_time: float | None = None) -> None:
        """Moves the intent to `to_status`, raising `InvalidTransitionError`
        if that edge is not allowed from the current status."""
        if self.is_terminal:
            raise InvalidTransitionError(
                f"intent '{self.intent_id}' is in terminal status {self.status.value}; "
                f"cannot transition to {to_status.value}"
            )
        allowed = ALLOWED_TRANSITIONS[self.status]
        if to_status not in allowed:
            raise InvalidTransitionError(
                f"intent '{self.intent_id}' cannot transition from {self.status.value} to "
                f"{to_status.value}; allowed: {sorted(s.value for s in allowed)}"
            )
        self.history.append(
            StatusTransition(from_status=self.status, to_status=to_status, reason=reason, sim_time=sim_time)
        )
        self.status = to_status
