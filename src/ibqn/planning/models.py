"""Data containers produced by `planning.planner.IntentPlanner`.

`ExecutionPlan` never contains a route/purification/swap decision the
application specified itself - it is entirely the network's own HOW,
computed from the intent's WHAT (see docs/architecture.md).
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EstimatedMetrics(BaseModel):
    """Pre-execution estimates - never a substitute for telemetry collected
    from an actual simulation run (see docs/sequence_code_analysis.md,
    section 2 constraints). `throughput_pairs_per_s` is intentionally
    omitted: no closed-form estimate of generation rate is derived here
    (attempt rate depends on memory frequency, round-trip classical delay,
    and retry dynamics not modeled by this planner - see
    docs/limitations.md)."""

    model_config = ConfigDict(frozen=True)

    fidelity: float = Field(ge=0.0, le=1.0)
    latency_s: float = Field(ge=0.0, description="round-trip photon travel time estimate along the route")


class ResourceRequirement(BaseModel):
    """Memories reserved at one node along the route. Interior (swapping)
    nodes need twice as many as endpoints (see
    docs/sequence_code_analysis.md, section 4.5:
    `RSVPProtocol.schedule` reserves `memory_size * 2` at non-endpoint
    nodes)."""

    model_config = ConfigDict(frozen=True)

    node_id: str
    memories_required: int = Field(gt=0)
    memories_available: int = Field(ge=0)

    @property
    def satisfied(self) -> bool:
        return self.memories_available >= self.memories_required


class ExecutionPlan(BaseModel):
    """The network's HOW for one intent."""

    model_config = ConfigDict(frozen=True)

    intent_id: str
    feasible: bool
    infeasibility_reason: str | None = None

    route: list[str] = Field(default_factory=list)
    route_rationale: str = ""

    reservations: list[ResourceRequirement] = Field(default_factory=list)

    requires_purification: bool = False
    purification_rounds_estimate: int = Field(
        default=0, ge=0,
        description="static estimate only; SeQUeNCe's own 'until_target' reservation mode may run a "
                     "different number of rounds at execution time - see docs/sequence_integration.md",
    )
    swapping_strategy_note: str = ""

    estimated_metrics: EstimatedMetrics | None = None

    fallback_routes: list[list[str]] = Field(
        default_factory=list, description="other feasible candidate routes, in the routing strategy's cost order"
    )

    @classmethod
    def infeasible(cls, intent_id: str, reason: str) -> "ExecutionPlan":
        return cls(intent_id=intent_id, feasible=False, infeasibility_reason=reason)
