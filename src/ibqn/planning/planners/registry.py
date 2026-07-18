"""Name -> `IntentPlannerPolicy` lookup, mirroring the existing
`experiments.sweeps.ROUTING_STRATEGIES`/`PURIFICATION_POLICIES` pattern so
planner-level selection can eventually become just another sweepable
parameter (see docs/planner_levels.md). Only L1/L2 are registered before
checkpoint 1 - L3/L4/L5/hybrid are added to this same dict as they're
implemented, never a parallel registry.
"""
from __future__ import annotations

from .base import IntentPlannerPolicy
from .l1_conservative import ConservativeOneRoundPlanner
from .l2_iterative import IterativeAnalyticalPlanner

PLANNER_POLICIES: dict[str, type] = {
    "L1": ConservativeOneRoundPlanner,
    "L2": IterativeAnalyticalPlanner,
}


class UnknownPlannerLevelError(ValueError):
    """Raised when a level name not in `PLANNER_POLICIES` is requested."""


def resolve_planner_policy(level: str) -> IntentPlannerPolicy:
    try:
        return PLANNER_POLICIES[level]()
    except KeyError:
        raise UnknownPlannerLevelError(
            f"unknown planner level '{level}' - supported: {sorted(PLANNER_POLICIES)}"
        ) from None
