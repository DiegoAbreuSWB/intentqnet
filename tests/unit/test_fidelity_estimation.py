"""Tests for `ibqn.planning.fidelity_estimation` (Fase J1) - see
docs/fidelity_estimation_model.md.

Expected values are computed from the same formulas SeQUeNCe's own
protocols use (`BarretKokA._entanglement_succeed`,
`EntanglementSwappingA_Circuit.updated_fidelity`), never hand-invented -
`test_sequence_consistent_estimator_matches_real_simulation_*` go one step
further and run the *actual* simulator to confirm the estimator's
prediction against real, observed telemetry.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.scenarios import ad_hoc_scenario
from ibqn.experiments.runner import run_scenario
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec
from ibqn.planning.fidelity_estimation import (
    ConservativeMinEstimator,
    SequenceConsistentEstimator,
    _swap_tree_fidelity,
)
from ibqn.planning.purification import NeverPurify, PurifyUntilTarget
from ibqn.planning.routing import ShortestHopCountRouting


def _spec(nodes: list[NodeSpec], links: list[QuantumLinkSpec]) -> NetworkTopologySpec:
    return NetworkTopologySpec(nodes=nodes, quantum_links=links, stop_time_s=1.0)


def _node(node_id: str, *, raw_fidelity: float = 0.85, swapping_degradation: float = 0.95, memories: int = 10) -> NodeSpec:
    return NodeSpec(id=node_id, memories=memories, raw_fidelity=raw_fidelity, swapping_degradation=swapping_degradation)


def _link(a: str, b: str, *, distance_m: float = 1000, attenuation_db_per_m: float = 1e-5) -> QuantumLinkSpec:
    return QuantumLinkSpec(source=a, destination=b, distance_m=distance_m, attenuation_db_per_m=attenuation_db_per_m)


NEVER_PURIFY = NeverPurify()


def _estimate(estimator, route, capabilities, *, target_fidelity=0.5, allow_purification=False, purification_strategy=NEVER_PURIFY):
    return estimator.estimate_path(
        route, capabilities, purification_strategy=purification_strategy,
        target_fidelity=target_fidelity, allow_purification=allow_purification,
    )


# --- uniform two-node link (direct, no swap) ---

@pytest.mark.unit
def test_conservative_estimator_uniform_two_node_link():
    capabilities = NetworkCapabilities(_spec([_node("a", raw_fidelity=0.85), _node("b", raw_fidelity=0.85)], [_link("a", "b")]))
    estimate = _estimate(ConservativeMinEstimator(), ["a", "b"], capabilities)
    assert estimate.pre_swap_fidelity == pytest.approx(0.85)


@pytest.mark.unit
def test_sequence_consistent_estimator_uniform_two_node_link():
    capabilities = NetworkCapabilities(_spec([_node("a", raw_fidelity=0.85), _node("b", raw_fidelity=0.85)], [_link("a", "b")]))
    estimate = _estimate(SequenceConsistentEstimator(), ["a", "b"], capabilities)
    assert estimate.pre_swap_fidelity == pytest.approx(0.85)


# --- heterogeneous two-node link: the two estimators genuinely disagree ---

@pytest.mark.unit
def test_conservative_estimator_heterogeneous_two_node_link_takes_the_minimum():
    capabilities = NetworkCapabilities(_spec([_node("a", raw_fidelity=0.9), _node("b", raw_fidelity=0.7)], [_link("a", "b")]))
    estimate = _estimate(ConservativeMinEstimator(), ["a", "b"], capabilities)
    assert estimate.pre_swap_fidelity == pytest.approx(0.7)


@pytest.mark.unit
def test_sequence_consistent_estimator_heterogeneous_two_node_link_uses_source_only():
    """No swap happens on a direct link - only the reservation initiator's
    app ever reports DELIVERY evidence (docs/limitations.md), so the
    observable fidelity is the SOURCE's own raw_fidelity, never the
    destination's and never a function combining both."""
    capabilities = NetworkCapabilities(_spec([_node("a", raw_fidelity=0.9), _node("b", raw_fidelity=0.7)], [_link("a", "b")]))
    estimate = _estimate(SequenceConsistentEstimator(), ["a", "b"], capabilities)
    assert estimate.pre_swap_fidelity == pytest.approx(0.9)

    reversed_estimate = _estimate(SequenceConsistentEstimator(), ["b", "a"], capabilities)
    assert reversed_estimate.pre_swap_fidelity == pytest.approx(0.7)


# --- uniform three-node chain (one swap): both estimators agree ---

UNIFORM_THREE_NODE = _spec(
    [_node("a", raw_fidelity=0.85), _node("r", raw_fidelity=0.85), _node("b", raw_fidelity=0.85)],
    [_link("a", "r"), _link("r", "b")],
)


@pytest.mark.unit
def test_both_estimators_agree_on_uniform_three_node_chain():
    capabilities = NetworkCapabilities(UNIFORM_THREE_NODE)
    conservative = _estimate(ConservativeMinEstimator(), ["a", "r", "b"], capabilities)
    consistent = _estimate(SequenceConsistentEstimator(), ["a", "r", "b"], capabilities)
    expected = 0.85 * 0.85 * 0.95
    assert conservative.pre_swap_fidelity == pytest.approx(expected)
    assert consistent.pre_swap_fidelity == pytest.approx(expected)


# --- heterogeneous three-node chain: only the swap node's own raw_fidelity matters ---

HETEROGENEOUS_THREE_NODE = _spec(
    [_node("a", raw_fidelity=0.85), _node("bad", raw_fidelity=0.9, swapping_degradation=0.95), _node("b", raw_fidelity=0.85)],
    [_link("a", "bad"), _link("bad", "b")],
)


@pytest.mark.unit
def test_conservative_estimator_heterogeneous_three_node_chain_uses_hop_minimum():
    capabilities = NetworkCapabilities(HETEROGENEOUS_THREE_NODE)
    estimate = _estimate(ConservativeMinEstimator(), ["a", "bad", "b"], capabilities)
    # hop(a,bad) = min(0.85, 0.9) = 0.85; hop(bad,b) = min(0.9, 0.85) = 0.85
    assert estimate.pre_swap_fidelity == pytest.approx(0.85 * 0.85 * 0.95)


@pytest.mark.unit
def test_sequence_consistent_estimator_heterogeneous_three_node_chain_uses_swap_node_only():
    """Both memories combined in the swap belong to the swap node itself,
    so only ITS raw_fidelity (squared) matters, never the endpoints' -
    matches the empirically-confirmed C01 finding (Fase H3, notebook A05)."""
    capabilities = NetworkCapabilities(HETEROGENEOUS_THREE_NODE)
    estimate = _estimate(SequenceConsistentEstimator(), ["a", "bad", "b"], capabilities)
    assert estimate.pre_swap_fidelity == pytest.approx(0.9 * 0.9 * 0.95)


@pytest.mark.unit
def test_sequence_consistent_estimator_is_route_direction_symmetric_for_a_single_swap():
    """A single swap's result doesn't depend on which endpoint is
    'source'/'destination' - only the swap node's own raw_fidelity/
    degradation matter."""
    capabilities = NetworkCapabilities(HETEROGENEOUS_THREE_NODE)
    forward = _estimate(SequenceConsistentEstimator(), ["a", "bad", "b"], capabilities)
    backward = _estimate(SequenceConsistentEstimator(), ["b", "bad", "a"], capabilities)
    assert forward.pre_swap_fidelity == pytest.approx(backward.pre_swap_fidelity)


# --- uniform diamond (least_loss detour: two swaps) ---

UNIFORM_DIAMOND = _spec(
    [
        _node("r1", raw_fidelity=0.85), _node("r3", raw_fidelity=0.85),
        _node("good1", raw_fidelity=0.85, swapping_degradation=0.95),
        _node("good2", raw_fidelity=0.85, swapping_degradation=0.95),
    ],
    [_link("r1", "good1"), _link("good1", "good2"), _link("good2", "r3")],
)


@pytest.mark.unit
def test_both_estimators_agree_on_uniform_diamond_detour():
    capabilities = NetworkCapabilities(UNIFORM_DIAMOND)
    route = ["r1", "good1", "good2", "r3"]
    conservative = _estimate(ConservativeMinEstimator(), route, capabilities)
    consistent = _estimate(SequenceConsistentEstimator(), route, capabilities)
    expected = 0.85**3 * 0.95**2  # 3 uniform hops, 2 interior swaps
    assert conservative.pre_swap_fidelity == pytest.approx(expected)
    assert consistent.pre_swap_fidelity == pytest.approx(expected)


# --- heterogeneous diamond: the real C01 calibration, cross-checked against
# empirically observed values from Fase H3's campaign data ---

HETEROGENEOUS_DIAMOND = _spec(
    [
        _node("r1", raw_fidelity=0.85), _node("r3", raw_fidelity=0.85),
        _node("bad", raw_fidelity=0.9, swapping_degradation=0.95),
        _node("good1", raw_fidelity=0.9, swapping_degradation=0.95),
        _node("good2", raw_fidelity=0.9, swapping_degradation=0.95),
    ],
    [_link("r1", "bad"), _link("bad", "r3"), _link("r1", "good1"), _link("good1", "good2"), _link("good2", "r3")],
)


@pytest.mark.unit
def test_sequence_consistent_estimator_matches_c01_observed_bad_route():
    capabilities = NetworkCapabilities(HETEROGENEOUS_DIAMOND)
    estimate = _estimate(SequenceConsistentEstimator(), ["r1", "bad", "r3"], capabilities)
    assert estimate.pre_swap_fidelity == pytest.approx(0.7695)  # 0.9 * 0.9 * 0.95, confirmed against real simulation in Fase H3


@pytest.mark.unit
def test_sequence_consistent_estimator_matches_c01_observed_least_loss_route():
    capabilities = NetworkCapabilities(HETEROGENEOUS_DIAMOND)
    estimate = _estimate(SequenceConsistentEstimator(), ["r1", "good1", "good2", "r3"], capabilities)
    assert estimate.pre_swap_fidelity == pytest.approx(0.657922, abs=1e-6)  # cascaded: 0.9*0.9*0.95, then *0.9*0.95


@pytest.mark.unit
def test_conservative_estimator_underestimates_on_heterogeneous_diamond():
    """Documents the systematic gap the conservative estimator has on
    heterogeneous topologies (Fase H3 finding) - the consistent estimator
    must produce a STRICTLY higher pre_swap_fidelity here."""
    capabilities = NetworkCapabilities(HETEROGENEOUS_DIAMOND)
    route = ["r1", "bad", "r3"]
    conservative = _estimate(ConservativeMinEstimator(), route, capabilities)
    consistent = _estimate(SequenceConsistentEstimator(), route, capabilities)
    assert conservative.pre_swap_fidelity < consistent.pre_swap_fidelity
    assert conservative.pre_swap_fidelity == pytest.approx(0.85 * 0.85 * 0.95)  # min(0.85, 0.9) each hop


# --- with / without purification: purification is estimator-agnostic ---

@pytest.mark.unit
def test_purification_applies_identically_on_top_of_either_estimator():
    from sequence.entanglement_management.purification.bbpssw_circuit import BBPSSWCircuit

    capabilities = NetworkCapabilities(HETEROGENEOUS_THREE_NODE)
    route = ["a", "bad", "b"]
    for estimator in (ConservativeMinEstimator(), SequenceConsistentEstimator()):
        pre_swap = _estimate(estimator, route, capabilities).pre_swap_fidelity
        target = pre_swap + 0.05  # just above the swap-only estimate, forcing purification
        with_purification = _estimate(
            estimator, route, capabilities, target_fidelity=target, allow_purification=True,
            purification_strategy=PurifyUntilTarget(),
        )
        assert with_purification.purification_required is True
        assert with_purification.estimated_end_to_end_fidelity == pytest.approx(BBPSSWCircuit.improved_fidelity(pre_swap))


@pytest.mark.unit
def test_without_purification_estimated_fidelity_equals_pre_swap_fidelity():
    capabilities = NetworkCapabilities(HETEROGENEOUS_THREE_NODE)
    estimate = _estimate(SequenceConsistentEstimator(), ["a", "bad", "b"], capabilities, allow_purification=False)
    assert estimate.purification_required is False
    assert estimate.estimated_end_to_end_fidelity == pytest.approx(estimate.pre_swap_fidelity)


# --- swap-tree bisection helper: cross-checked against a REAL simulation
# run on a 3-interior-node chain (longer than the diamond's 2-swap detour),
# not just against another hand-rolled algorithm - this project's standing
# rule is to validate against the real simulator, never against an
# independently invented reference (see docs/sequence_code_analysis.md,
# section 2 constraints) ---

@pytest.mark.unit
def test_swap_tree_fidelity_matches_real_simulation_on_a_three_interior_node_chain():
    nodes = [
        NodeSpec(id="a", memories=10, raw_fidelity=0.85),
        NodeSpec(id="n1", memories=20, raw_fidelity=0.92, swapping_degradation=0.93),
        NodeSpec(id="n2", memories=20, raw_fidelity=0.88, swapping_degradation=0.97),
        NodeSpec(id="n3", memories=20, raw_fidelity=0.95, swapping_degradation=0.90),
        NodeSpec(id="b", memories=10, raw_fidelity=0.80),
    ]
    links = [
        QuantumLinkSpec(source="a", destination="n1", distance_m=200, attenuation_db_per_m=1e-6),
        QuantumLinkSpec(source="n1", destination="n2", distance_m=200, attenuation_db_per_m=1e-6),
        QuantumLinkSpec(source="n2", destination="n3", distance_m=200, attenuation_db_per_m=1e-6),
        QuantumLinkSpec(source="n3", destination="b", distance_m=200, attenuation_db_per_m=1e-6),
    ]
    spec = _spec(nodes, links)
    capabilities = NetworkCapabilities(spec)
    route = ["a", "n1", "n2", "n3", "b"]

    predicted = _swap_tree_fidelity(route, capabilities)

    intent = simple_intent(
        intent_id="chain5", source="a", destination="b", min_fidelity=0.01,
        requested_pairs=5, start_time=0.02, duration=0.2, allow_purification=False,
    )
    scenario = ad_hoc_scenario(spec, [intent], seed=7, name="chain5-test")
    result = run_scenario(scenario, seed=7, routing_strategy=ShortestHopCountRouting(), purification_strategy=NEVER_PURIFY)
    trial = result.get("chain5")

    assert trial.final_status.value == "SATISFIED"
    observed = next(c.observed for c in trial.evaluation.condition_results if c.metric == "average_fidelity")
    assert observed == pytest.approx(predicted, abs=1e-9)
    assert observed == pytest.approx(0.62018328564, abs=1e-9)  # pinned: confirmed once against the real simulator
