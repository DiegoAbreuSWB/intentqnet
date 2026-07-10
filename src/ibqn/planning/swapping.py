"""Swapping strategy interface.

Only one concrete strategy exists in this version. Swap order for a route is
fixed by `ResourceManager.generate_load_rules`'s binary-bisection of the path
(`sequence/resource_management/resource_manager.py`, see
docs/sequence_code_analysis.md, sections 4.3/4.7) whenever a reservation
goes through SeQUeNCe's default `NetworkManager.request` mechanism, which is
what `SequenceExecutor` uses (Etapa D). Changing swap order would require
building `Rule`s by hand instead of using that mechanism - explicitly out of
scope for this planner version (see docs/sequence_integration.md). The
interface is kept here, ready for that future strategy, rather than left
unmodeled.

This does not bias fidelity estimates: `feasibility.estimate_swap_only_fidelity`
is a simple product over hops, which is order-independent regardless of
which concrete `SwappingStrategy` (if any) ends up controlling execution.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class SwappingStrategy(ABC):
    @abstractmethod
    def describe(self, route: list[str]) -> str:
        """Returns a human-readable description of the swap order this
        strategy would use for `route`, for `ExecutionPlan.swapping_strategy_note`."""


class DefaultSequenceSwappingStrategy(SwappingStrategy):
    """Documents, rather than controls, SeQUeNCe's own default behavior."""

    def describe(self, route: list[str]) -> str:
        n_swaps = max(len(route) - 2, 0)
        return (
            f"swap order follows SeQUeNCe's default binary-bisection of the {len(route)}-node route "
            f"({n_swaps} swap(s) at {route[1:-1] or 'no interior nodes'}); not parametrized by this planner"
        )
