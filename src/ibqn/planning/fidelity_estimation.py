"""Pluggable end-to-end fidelity estimators consulted by
`planning.feasibility.evaluate_route` (Fase J1, see
docs/fidelity_estimation_model.md for the full derivation).

Two estimators model two different assumptions about how SeQUeNCe's own
entanglement-generation/swapping protocols compute fidelity:

- `ConservativeMinEstimator` preserves this project's ORIGINAL model (each
  hop's fidelity = `min(raw_fidelity(a), raw_fidelity(b))`, multiplied
  along the route times each interior node's `swapping_degradation`) -
  exact on uniform-fidelity topologies, but a documented UNDERESTIMATE on
  heterogeneous ones (found in Fase H3, `notebooks/article/
  A05_planner_estimation_error.ipynb`).

- `SequenceConsistentEstimator` reproduces the REAL mechanism: each memory
  independently takes on *its own node's* `raw_fidelity` on a successful
  elementary generation (`sequence/entanglement_management/generation/
  barret_kok.py:228`, `self.memory.fidelity = self.memory.raw_fidelity` -
  never a function of the remote peer), combined with the exact swap TREE
  `sequence/resource_management/resource_manager.py`'s
  `generate_load_rules` builds via a balanced bisection over the path (not
  a naive left-to-right chain - a node's `es_rule_condition_A` only fires
  once its memory's `remote_node` already equals the precomputed
  `left`/`right` target, see `.../action_condition_set.py:396-406`, which
  is what forces this exact evaluation order). Verified by cross-checking
  against real campaign data (C01, diamond topology) and against a
  from-scratch discrete-event replica of the swap-firing order for random
  heterogeneous paths of length 3-12 (see the module's test suite).

Both estimators are otherwise interchangeable: `evaluate_route` never
special-cases which one is active, and a campaign can sweep between them
via `experiments.sweeps.SWEEP_PARAMETERS["fidelity_estimator"]`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..network.capabilities import NetworkCapabilities
from .purification import PurificationStrategy


@dataclass(frozen=True)
class FidelityEstimate:
    """The full output of one `LinkFidelityEstimator.estimate_path` call -
    everything downstream (`FeasibilityResult`, `ExecutionPlan`,
    `TrialRecord`) needs to compare a prediction against what was actually
    observed after simulating."""

    estimator_name: str
    route: list[str]
    per_link_endpoint_fidelities: dict[tuple[str, str], tuple[float, float]] = field(default_factory=dict)
    """`(a, b) -> (fidelity_as_seen_by_a, fidelity_as_seen_by_b)` for every
    adjacent pair in `route` - the two values differ whenever
    `raw_fidelity(a) != raw_fidelity(b)` (see the class docstring above)."""
    pre_swap_fidelity: float = 0.0
    """End-to-end fidelity estimate before any purification is applied."""
    estimated_end_to_end_fidelity: float = 0.0
    """Final estimate after purification, if `purification_required`."""
    purification_required: bool = False
    purification_feasible: bool = False
    purification_rounds_estimate: int = 0
    purification_note: str = ""
    """`PurificationDecision.note` - why purification was/wasn't attempted."""
    assumptions: str = ""
    """Describes the estimator's OWN methodology (not the purification
    decision) - see each estimator class's docstring."""


class LinkFidelityEstimator(Protocol):
    name: str

    def estimate_path(
        self,
        route: list[str],
        capabilities: NetworkCapabilities,
        *,
        purification_strategy: PurificationStrategy,
        target_fidelity: float,
        allow_purification: bool,
    ) -> FidelityEstimate:
        """Estimates the end-to-end fidelity of `route` (a simple path,
        source to destination inclusive), then asks `purification_strategy`
        whether purifying past that estimate is warranted."""
        ...


class ConservativeMinEstimator:
    """This project's original estimator: `hop_fidelity(a, b) =
    min(raw_fidelity(a), raw_fidelity(b))`, product of hop fidelities times
    product of interior `swapping_degradation`s. Exact on uniform-fidelity
    topologies; documented underestimate on heterogeneous ones (see the
    module docstring)."""

    name = "conservative_min"

    def estimate_path(
        self, route, capabilities, *, purification_strategy, target_fidelity, allow_purification,
    ) -> FidelityEstimate:
        if len(route) < 2:
            raise ValueError(f"route must have at least two nodes, got {route!r}")

        per_link: dict[tuple[str, str], tuple[float, float]] = {}
        hop_fidelities: list[float] = []
        for a, b in zip(route, route[1:]):
            hop = min(capabilities.node(a).raw_fidelity, capabilities.node(b).raw_fidelity)
            hop_fidelities.append(hop)
            per_link[(a, b)] = (hop, hop)

        pre_swap = 1.0
        for hop in hop_fidelities:
            pre_swap *= hop
        for interior_node in route[1:-1]:
            pre_swap *= capabilities.node(interior_node).swapping_degradation

        decision = purification_strategy.decide(pre_swap, target_fidelity, allow_purification)
        return FidelityEstimate(
            estimator_name=self.name, route=list(route), per_link_endpoint_fidelities=per_link,
            pre_swap_fidelity=pre_swap, estimated_end_to_end_fidelity=decision.fidelity_estimate,
            purification_required=decision.attempt, purification_feasible=decision.attempt,
            purification_rounds_estimate=decision.rounds_estimate, purification_note=decision.note,
            assumptions=(
                "each hop's fidelity = min(raw_fidelity(a), raw_fidelity(b)); exact on uniform-fidelity "
                "topologies, systematically underestimates on heterogeneous ones - see "
                "docs/fidelity_estimation_model.md"
            ),
        )


def _bisection_partners(path: list[str], node: str) -> tuple[str, str]:
    """Verbatim port of the bisection loop `resource_manager.py`'s
    `generate_load_rules` uses to compute each interior node's swap-rule
    `left`/`right` condition targets (see
    `sequence/resource_management/resource_manager.py:229-238`). Determines
    which two (possibly distant) nodes `node`'s swap ultimately connects -
    and, by extension, the exact firing order swaps must respect, since
    `es_rule_condition_A` only fires once `node`'s own memory's
    `remote_node` already equals this precomputed `left`/`right`
    (`.../action_condition_set.py:396-406`)."""
    reduced = path[:]
    while reduced.index(node) % 2 == 0:
        reduced = [n for i, n in enumerate(reduced) if i % 2 == 0 or i == len(reduced) - 1]
    index = reduced.index(node)
    return reduced[index - 1], reduced[index + 1]


def _swap_tree_fidelity(path: list[str], capabilities: NetworkCapabilities) -> float:
    """Resolves the end-to-end fidelity of `path` (>= 3 nodes) by mirroring
    SeQUeNCe's real, order-dependent swap resolution: an interior node's
    swap combines two inputs, each either (a) the node's OWN
    `raw_fidelity` if that side is still a genuine, unswapped elementary
    link to an immediate physical neighbor, or (b) the propagated result
    of the neighboring interior node's OWN swap otherwise - see the module
    docstring and docs/fidelity_estimation_model.md for the full
    derivation and its empirical verification."""
    memo: dict[str, float] = {}

    def resolve(node: str) -> float:
        if node in memo:
            return memo[node]
        index = path.index(node)
        left_partner, right_partner = _bisection_partners(path, node)
        raw_fidelity = capabilities.node(node).raw_fidelity
        left_value = raw_fidelity if left_partner == path[index - 1] else resolve(path[index - 1])
        right_value = raw_fidelity if right_partner == path[index + 1] else resolve(path[index + 1])
        result = left_value * right_value * capabilities.node(node).swapping_degradation
        memo[node] = result
        return result

    root = next(node for node in path[1:-1] if _bisection_partners(path, node) == (path[0], path[-1]))
    return resolve(root)


class SequenceConsistentEstimator:
    """Reproduces SeQUeNCe's real per-node fidelity assignment and swap
    tree exactly - see the module docstring."""

    name = "sequence_consistent"

    def estimate_path(
        self, route, capabilities, *, purification_strategy, target_fidelity, allow_purification,
    ) -> FidelityEstimate:
        if len(route) < 2:
            raise ValueError(f"route must have at least two nodes, got {route!r}")

        per_link: dict[tuple[str, str], tuple[float, float]] = {
            (a, b): (capabilities.node(a).raw_fidelity, capabilities.node(b).raw_fidelity)
            for a, b in zip(route, route[1:])
        }

        if len(route) == 2:
            # No swap: only the reservation initiator's own app ever reports
            # DELIVERY evidence (RequestApp.get_memory only counts on the
            # initiator side - docs/limitations.md), so the observable
            # fidelity is the source node's own raw_fidelity, never a
            # function of the destination's.
            pre_swap = capabilities.node(route[0]).raw_fidelity
            assumptions = (
                "no-swap (direct, 2-node) link: fidelity is the SOURCE node's own raw_fidelity - "
                "RequestApp.get_memory only reports DELIVERY evidence from the reservation's "
                "initiator side, so the destination's raw_fidelity is never observed here"
            )
        else:
            pre_swap = _swap_tree_fidelity(route, capabilities)
            assumptions = (
                "reproduces BarretKokA's per-node raw_fidelity assignment "
                "(sequence/entanglement_management/generation/barret_kok.py:228) combined with the "
                "balanced-bisection swap tree resource_manager.generate_load_rules actually builds; "
                "only interior (swap) nodes' raw_fidelity ever contributes to the result - endpoint "
                "raw_fidelity is irrelevant once at least one swap happens"
            )

        decision = purification_strategy.decide(pre_swap, target_fidelity, allow_purification)
        return FidelityEstimate(
            estimator_name=self.name, route=list(route), per_link_endpoint_fidelities=per_link,
            pre_swap_fidelity=pre_swap, estimated_end_to_end_fidelity=decision.fidelity_estimate,
            purification_required=decision.attempt, purification_feasible=decision.attempt,
            purification_rounds_estimate=decision.rounds_estimate, purification_note=decision.note,
            assumptions=assumptions,
        )


FIDELITY_ESTIMATORS: dict[str, type] = {
    "conservative_min": ConservativeMinEstimator,
    "sequence_consistent": SequenceConsistentEstimator,
}


class UnknownFidelityEstimatorError(ValueError):
    """Raised when a name not in `FIDELITY_ESTIMATORS` is requested."""


def resolve_fidelity_estimator(name: str) -> LinkFidelityEstimator:
    try:
        return FIDELITY_ESTIMATORS[name]()
    except KeyError:
        raise UnknownFidelityEstimatorError(
            f"unknown fidelity estimator '{name}' - supported: {sorted(FIDELITY_ESTIMATORS)}"
        ) from None
