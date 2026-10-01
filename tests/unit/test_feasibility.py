"""Tests for `ibqn.planning.feasibility` - pure estimation logic, no SeQUeNCe
simulation involved. Expected fidelity values are computed from the real
simulator formulas (`f1*f2*degradation`, `BBPSSWCircuit.improved_fidelity`),
never hand-derived independently (see docs/sequence_code_analysis.md,
section 2 constraints).
"""
# LEGACY-MODEL REGRESSION: every expected number below is a ket_vector
# closed form (f1*f2*degradation, Dur-Briegel purification). Since the
# physical-realism revision (docs/physical_model.md) the project default
# is bell_diagonal, so these fixtures pin formalism="ket_vector" to keep
# checking the legacy model they document.

import pytest
from sequence.entanglement_management.purification.bbpssw_circuit import BBPSSWCircuit

from ibqn.intent.models import (
    EntanglementIntent, IntentEndpoints, IntentPolicy, IntentRequirements, IntentValidation, SuccessCondition,
)
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec
from ibqn.planning.feasibility import estimate_latency_s, estimate_swap_only_fidelity, evaluate_route
from ibqn.planning.purification import NeverPurify, PurifyUntilTarget

LINEAR_SPEC = NetworkTopologySpec(
    nodes=[
        NodeSpec(id="r1", memories=10, raw_fidelity=0.85, swapping_degradation=0.95),
        NodeSpec(id="r2", memories=20, raw_fidelity=0.85, swapping_degradation=0.95),
        NodeSpec(id="r3", memories=10, raw_fidelity=0.85, swapping_degradation=0.95),
    ],
    quantum_links=[
        QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=1e-5),
        QuantumLinkSpec(source="r2", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
    ],
    stop_time_s=1.0, formalism="ket_vector",
)

SINGLE_SWAP_FIDELITY = 0.85 * 0.85 * 0.95


def build_intent(min_fidelity, requested_pairs=10, allow_purification=True) -> EntanglementIntent:
    return EntanglementIntent(
        id="intent-001",
        endpoints=IntentEndpoints(source="r1", destination="r3"),
        requirements=IntentRequirements(
            min_fidelity=min_fidelity, min_throughput=1, max_latency=1.0,
            requested_pairs=requested_pairs, start_time=0, duration=1,
        ),
        policy=IntentPolicy(allow_purification=allow_purification),
        validation=IntentValidation(
            metrics=["delivered_pairs"],
            success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=requested_pairs)],
        ),
    )


@pytest.mark.unit
def test_estimate_swap_only_fidelity_matches_real_swapping_formula():
    capabilities = NetworkCapabilities(LINEAR_SPEC)
    fidelity, hop_fidelities = estimate_swap_only_fidelity(capabilities, ["r1", "r2", "r3"])

    assert hop_fidelities == [0.85, 0.85]
    assert fidelity == pytest.approx(SINGLE_SWAP_FIDELITY)


@pytest.mark.unit
def test_estimate_swap_only_fidelity_is_order_independent_for_more_swaps():
    """Multiplication is associative: a 4-node chain (2 swaps) must give the
    exact product of hop fidelities times each interior node's degradation,
    regardless of which interior node is considered "first" (see
    docs/sequence_code_analysis.md, section 4.3: swap order doesn't change
    the analytical result)."""
    spec = NetworkTopologySpec(
        nodes=[
            NodeSpec(id="a", memories=10, raw_fidelity=0.9, swapping_degradation=0.9),
            NodeSpec(id="b", memories=10, raw_fidelity=0.9, swapping_degradation=0.9),
            NodeSpec(id="c", memories=10, raw_fidelity=0.9, swapping_degradation=0.9),
            NodeSpec(id="d", memories=10, raw_fidelity=0.9, swapping_degradation=0.9),
        ],
        quantum_links=[
            QuantumLinkSpec(source="a", destination="b", distance_m=1000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="b", destination="c", distance_m=1000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="c", destination="d", distance_m=1000, attenuation_db_per_m=1e-5),
        ],
        stop_time_s=1.0, formalism="ket_vector",
    )
    capabilities = NetworkCapabilities(spec)
    fidelity, hop_fidelities = estimate_swap_only_fidelity(capabilities, ["a", "b", "c", "d"])

    assert hop_fidelities == [0.9, 0.9, 0.9]
    assert fidelity == pytest.approx(0.9 ** 3 * 0.9 ** 2)  # 3 hops, 2 interior swaps


@pytest.mark.unit
def test_estimate_latency_uses_real_speed_of_light_constant():
    from sequence.constants import SPEED_OF_LIGHT

    capabilities = NetworkCapabilities(LINEAR_SPEC)
    latency = estimate_latency_s(capabilities, ["r1", "r2", "r3"])

    expected = 2 * 2000 / (SPEED_OF_LIGHT * 1e12)
    assert latency == pytest.approx(expected)


@pytest.mark.unit
def test_route_feasible_without_purification_when_target_below_swap_fidelity():
    capabilities = NetworkCapabilities(LINEAR_SPEC)
    intent = build_intent(min_fidelity=0.65)

    result = evaluate_route(capabilities, ["r1", "r2", "r3"], intent)

    assert result.feasible is True
    assert result.requires_purification is False
    assert result.purified_fidelity_estimate is None
    assert result.swap_only_fidelity == pytest.approx(SINGLE_SWAP_FIDELITY)


@pytest.mark.unit
def test_route_feasible_with_one_purification_round():
    capabilities = NetworkCapabilities(LINEAR_SPEC)
    expected_purified = BBPSSWCircuit.improved_fidelity(SINGLE_SWAP_FIDELITY)
    intent = build_intent(min_fidelity=expected_purified - 0.01)

    result = evaluate_route(capabilities, ["r1", "r2", "r3"], intent)

    assert result.feasible is True
    assert result.requires_purification is True
    assert result.purification_rounds_estimate == 1
    assert result.purified_fidelity_estimate == pytest.approx(expected_purified)


@pytest.mark.unit
def test_route_infeasible_when_target_exceeds_one_round_purification_estimate():
    capabilities = NetworkCapabilities(LINEAR_SPEC)
    intent = build_intent(min_fidelity=0.99)

    result = evaluate_route(capabilities, ["r1", "r2", "r3"], intent)

    assert result.feasible is False
    assert "exceeds" in result.reason


@pytest.mark.unit
def test_route_infeasible_when_purification_disallowed_by_policy():
    capabilities = NetworkCapabilities(LINEAR_SPEC)
    intent = build_intent(min_fidelity=0.70, allow_purification=False)

    result = evaluate_route(capabilities, ["r1", "r2", "r3"], intent)

    assert result.feasible is False
    assert result.requires_purification is False  # NeverPurify-equivalent behavior baked into PurifyUntilTarget
    assert "allow_purification is False" in result.reason


@pytest.mark.unit
def test_route_infeasible_when_memory_insufficient_at_interior_node():
    spec = NetworkTopologySpec(
        nodes=[
            NodeSpec(id="r1", memories=10, raw_fidelity=0.85, swapping_degradation=0.95),
            NodeSpec(id="r2", memories=5, raw_fidelity=0.85, swapping_degradation=0.95),  # too small: needs 2*10=20
            NodeSpec(id="r3", memories=10, raw_fidelity=0.85, swapping_degradation=0.95),
        ],
        quantum_links=[
            QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="r2", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
        ],
        stop_time_s=1.0, formalism="ket_vector",
    )
    capabilities = NetworkCapabilities(spec)
    intent = build_intent(min_fidelity=0.65, requested_pairs=10)

    result = evaluate_route(capabilities, ["r1", "r2", "r3"], intent)

    assert result.memory_feasible is False
    assert result.feasible is False
    assert "r2" in result.reason


@pytest.mark.unit
def test_never_purify_strategy_rejects_routes_needing_purification():
    capabilities = NetworkCapabilities(LINEAR_SPEC)
    intent = build_intent(min_fidelity=0.70)  # achievable with 1 purification round, but strategy forbids it

    result = evaluate_route(capabilities, ["r1", "r2", "r3"], intent, purification_strategy=NeverPurify())

    assert result.feasible is False
    assert result.requires_purification is False


@pytest.mark.unit
def test_purify_until_target_matches_default_when_swap_alone_suffices():
    capabilities = NetworkCapabilities(LINEAR_SPEC)
    intent = build_intent(min_fidelity=0.5)

    default_result = evaluate_route(capabilities, ["r1", "r2", "r3"], intent)
    explicit_result = evaluate_route(
        capabilities, ["r1", "r2", "r3"], intent, purification_strategy=PurifyUntilTarget()
    )

    assert default_result == explicit_result
