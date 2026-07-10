"""Typed intent model: what an application asks for, never how the network
delivers it (see docs/architecture.md for the WHAT/HOW split).

All time-like fields (`start_time`, `duration`, `max_latency`) are expressed
in **seconds** at the intent layer, regardless of the picosecond convention
used internally by SeQUeNCe's `Timeline` - unit conversion is the
responsibility of `network.sequence_adapter` (Etapa D), never of these models.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_CONDITION_PATTERN = re.compile(r"^(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)$")

ComparisonOperator = Literal[">=", "<=", ">", "<", "==", "!="]


class IntentStatus(str, Enum):
    """Lifecycle states of an `EntanglementIntent` (see `intent.lifecycle`
    for the allowed-transition graph)."""

    RECEIVED = "RECEIVED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"
    PLANNING = "PLANNING"
    PLANNED = "PLANNED"
    DEPLOYING = "DEPLOYING"
    ACTIVE = "ACTIVE"
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    RECONCILING = "RECONCILING"
    FAILED = "FAILED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class IntentEndpoints(BaseModel):
    """Source and destination nodes for the requested entanglement distribution.

    Node names are opaque strings resolved later against a concrete topology
    (`network.topology`) - this model does not validate that they exist.
    """

    model_config = ConfigDict(frozen=True)

    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)

    @model_validator(mode="after")
    def _source_and_destination_must_differ(self) -> "IntentEndpoints":
        if self.source == self.destination:
            raise ValueError(f"source and destination must differ, both are '{self.source}'")
        return self


class IntentRequirements(BaseModel):
    """Application-level requirements. Units are documented per field since
    the prompt that produced this project explicitly forbids unitless
    parameters."""

    model_config = ConfigDict(frozen=True)

    min_fidelity: float = Field(ge=0.0, le=1.0, description="dimensionless, in [0, 1]")
    min_throughput: float = Field(gt=0.0, description="entangled pairs per second")
    max_latency: float = Field(gt=0.0, description="seconds, per-pair end-to-end latency budget")
    requested_pairs: int = Field(gt=0, description="number of end-to-end entangled pairs requested")
    start_time: float = Field(ge=0.0, description="seconds, relative to scenario/simulation start")
    duration: float = Field(gt=0.0, description="seconds, length of the reservation window")


class IntentPolicy(BaseModel):
    """Optional knobs the network is *allowed* to use while satisfying the
    intent - never a specification of *how* (no route, no swap order, no
    purification round count)."""

    model_config = ConfigDict(frozen=True)

    priority: Literal["low", "normal", "high"] = "normal"
    allow_rerouting: bool = True
    allow_purification: bool = True
    allow_multiple_paths: bool = False


class SuccessCondition(BaseModel):
    """A single measurable condition, e.g. `average_fidelity >= 0.90`."""

    model_config = ConfigDict(frozen=True)

    metric: str = Field(min_length=1)
    operator: ComparisonOperator
    expected: float

    @classmethod
    def parse(cls, metric: str, expression: str) -> "SuccessCondition":
        """Parses a condition expressed as `"<operator> <value>"`
        (e.g. `">= 0.90"`), the format used in the intent YAML/JSON schema.
        """
        match = _CONDITION_PATTERN.match(expression.strip())
        if not match:
            raise ValueError(
                f"invalid success condition expression for metric '{metric}': {expression!r} "
                f"(expected '<op> <value>' with op in >=, <=, >, <, ==, !=)"
            )
        operator, value = match.groups()
        return cls(metric=metric, operator=operator, expected=float(value))

    def __str__(self) -> str:
        return f"{self.metric} {self.operator} {self.expected}"


class IntentValidation(BaseModel):
    """Declares how the intent's own success should be measured - the
    application states WHAT to check, `assurance.evaluator` (Etapa G) is
    responsible for actually checking it against observed metrics."""

    model_config = ConfigDict(frozen=True)

    metrics: list[str] = Field(min_length=1)
    success_conditions: list[SuccessCondition] = Field(min_length=1)

    @model_validator(mode="after")
    def _conditions_must_reference_declared_metrics(self) -> "IntentValidation":
        declared = set(self.metrics)
        undeclared = [c.metric for c in self.success_conditions if c.metric not in declared]
        if undeclared:
            raise ValueError(
                f"success_conditions reference metrics not listed in 'metrics': {undeclared}"
            )
        return self


class EntanglementIntent(BaseModel):
    """The declarative, WHAT-only request an application submits.

    Never specifies path, repeater nodes, swap order, purification protocol,
    purification round count, memories, node rules, routing algorithm, or
    recovery policy - those are the network's job (see docs/architecture.md).
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    service: Literal["entanglement_distribution"] = "entanglement_distribution"
    endpoints: IntentEndpoints
    requirements: IntentRequirements
    policy: IntentPolicy = Field(default_factory=IntentPolicy)
    validation: IntentValidation


class IntentResult(BaseModel):
    """Terminal-state summary for an intent (the detailed per-condition
    breakdown lives in `assurance.evaluator.IntentEvaluation`, Etapa G)."""

    intent_id: str
    final_status: IntentStatus
    satisfied: bool | None = None
    reason: str | None = None
    sim_time_completed: float | None = Field(
        default=None, description="seconds, simulation time when the intent reached a terminal status"
    )
