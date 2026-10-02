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
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..utils.logging import get_logger

logger = get_logger(__name__)

_CONDITION_PATTERN = re.compile(r"^(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?)$")

ComparisonOperator = Literal[">=", "<=", ">", "<", "==", "!="]

_LEGACY_REQUIREMENT_KEY_MAP: dict[str, str] = {
    "requested_pairs": "reserved_memory_slots",
    "start_time": "start_time_s",
    "duration": "duration_s",
}


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
    parameters.

    `reserved_memory_slots` and `min_delivered_pairs` are deliberately
    separate fields (Fase J2, see docs/intent_resource_semantics.md):
    `reserved_memory_slots` sizes the memory pool handed to SeQUeNCe's
    `RSVPProtocol.schedule` (a RESOURCE), while `min_delivered_pairs` is an
    OPTIONAL service-level delivery GOAL. Conflating the two under one name
    (`requested_pairs`, this project's original field) made
    `delivered_pairs >> requested_pairs` look like a bug instead of the
    expected consequence of memory reuse during the reservation window
    (see docs/metrics.md). Legacy intents that only ever declared
    `requested_pairs` keep working unchanged - the value is migrated to
    `reserved_memory_slots` below - and their delivery success continues
    to be judged by `validation.success_conditions` exactly as before;
    `min_delivered_pairs` is never silently inferred from either of those,
    it stays `None` unless an intent explicitly declares it."""

    model_config = ConfigDict(frozen=True)

    min_fidelity: float = Field(ge=0.0, le=1.0, description="dimensionless, in [0, 1]")
    min_throughput: float = Field(gt=0.0, description="entangled pairs per second")
    max_latency: float = Field(gt=0.0, description="seconds, per-pair end-to-end latency budget")
    min_delivered_pairs: int | None = Field(
        default=None, gt=0,
        description=(
            "OPTIONAL service-level delivery goal, distinct from reserved_memory_slots - "
            "see docs/intent_resource_semantics.md. None for intents that only rely on "
            "validation.success_conditions['delivered_pairs'] for their delivery bar."
        ),
    )
    reserved_memory_slots: int = Field(
        gt=0,
        description=(
            "memory pool size handed to SeQUeNCe's RSVPProtocol.schedule - a RESOURCE, not "
            "a delivery cap: memories are recycled during the reservation window, so "
            "delivered_pairs routinely exceeds this (see docs/metrics.md). Formerly named "
            "'requested_pairs'; that name is still accepted on input and migrated here, but "
            "is no longer produced anywhere downstream."
        ),
    )
    start_time_s: float = Field(ge=0.0, description="seconds, relative to scenario/simulation start")
    duration_s: float = Field(gt=0.0, description="seconds, length of the reservation window")

    @model_validator(mode="before")
    @classmethod
    def _migrate_legacy_field_names(cls, data: Any) -> Any:
        """Explicit, documented migration (Fase J2): accepts the legacy
        flat field names (`requested_pairs`, `start_time`, `duration`) and
        renames them to their new counterparts *before* validation, so
        every intent constructed with the old shape - in Python, YAML, or
        JSON - keeps working without modification. Never accepts both an
        old and a new name with conflicting values (that would be exactly
        the kind of silent double-interpretation this migration must
        avoid)."""
        if not isinstance(data, dict):
            return data
        migrated = dict(data)
        for legacy_name, new_name in _LEGACY_REQUIREMENT_KEY_MAP.items():
            if legacy_name not in migrated:
                continue
            legacy_value = migrated.pop(legacy_name)
            if new_name in migrated and migrated[new_name] != legacy_value:
                raise ValueError(
                    f"IntentRequirements received both legacy '{legacy_name}'={legacy_value!r} and "
                    f"'{new_name}'={migrated[new_name]!r} with different values - specify only one "
                    f"(see docs/intent_resource_semantics.md)"
                )
            migrated.setdefault(new_name, legacy_value)
            logger.info(
                "IntentRequirements: migrating legacy field '%s' -> '%s' (see docs/intent_resource_semantics.md)",
                legacy_name, new_name,
            )
        return migrated


class IntentPolicy(BaseModel):
    """Optional knobs the network is *allowed* to use while satisfying the
    intent - never a specification of *how* (no route, no swap order, no
    purification round count).

    The intent's `reserved_memory_slots` and `duration_s` are the resource
    BUDGET it grants the network. Planning reserves exactly that budget; a
    later episode may use more only as far as `max_resource_scale` allows
    (`assurance.reconciliation_policy`). Likewise `allow_rerouting` decides
    whether reconciliation may move the intent to another route, and
    `allow_purification` whether any purification is executed
    (`planning.purification.executed_purification_mode`)."""

    model_config = ConfigDict(frozen=True)

    priority: Literal["low", "normal", "high"] = "normal"
    allow_rerouting: bool = True
    allow_purification: bool = True
    allow_multiple_paths: bool = False
    max_resource_scale: float = Field(
        default=1.0, ge=1.0,
        description=(
            "how far a later episode may enlarge the declared budget (reserved_memory_slots and "
            "duration_s) when the system reconciles a violated intent: 1 (default) never, 2 up to "
            "twice the declared values"
        ),
    )


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
