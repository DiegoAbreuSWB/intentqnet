"""Tests for `planning.planners.generation_models` and the buffered planner
levels (L2-RB, L3-RB) - docs/generation_model_audit.md.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.realistic_topologies import realistic_chain, realistic_diamond
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.platforms import SIV_2024, SIV_2024_THEORETICAL_OPS
from ibqn.planning.planners import (
    PLANNER_POLICIES,
    BufferedResourceAwarePlanner,
    PlanningContext,
    ProbabilisticBufferedPlanner,
    ResourceAwareIterativePlanner,
    estimate_resource_aware_plan,
    generate_candidate_paths,
    resolve_planner_policy,
)
from ibqn.planning.planners.generation_models import (
    BARRETT_KOK_ATTEMPT_RATE_FACTOR,
    SINGLE_HERALDED_CYCLE_FACTOR,
    SINGLE_HERALDED_PRIMARY_REQUESTER_CYCLE_FACTOR,
    attempt_cycle_s,
    buffered_end_to_end_rate,
    estimate_generation,
    hop_success_probability,
    matched_stream_rate,
    single_heralded_cycle_factor,
)
from ibqn.planning.routing import ShortestHopCountRouting


def _intent(min_fidelity=0.6, slots=4, pairs=10, duration=0.3, source="a", destination="b"):
    return simple_intent(
        intent_id="gen", source=source, destination=destination, min_fidelity=min_fidelity,
        requested_pairs=slots, min_delivered_pairs=pairs, start_time=0.01, duration=duration,
    )


@pytest.mark.unit
def test_hop_success_probability_matches_the_single_heralded_closed_form():
    capabilities = NetworkCapabilities(realistic_chain(1, platform=SIV_2024, link_m=5_000))
    transmission = 10 ** (-(5_000 * SIV_2024.attenuation_db_per_m) / 10)
    expected = 0.5 * SIV_2024.memory_efficiency ** 2 * SIV_2024.detector_efficiency ** 2 * transmission
    assert hop_success_probability(capabilities, "a", "r1") == pytest.approx(expected)
    assert expected == pytest.approx(5.62e-3, rel=1e-2)  # the value the audit measured against


@pytest.mark.unit
def test_hop_success_probability_keeps_the_legacy_formula_under_ket_vector():
    capabilities = NetworkCapabilities(three_node_spec(attenuation_db_per_m=1e-5, formalism="ket_vector"))
    assert hop_success_probability(capabilities, "a", "r") == pytest.approx(0.5 * 10 ** (-(1000 * 1e-5) / 10))


@pytest.mark.unit
def test_attempt_cycle_depends_on_which_end_requests_the_pairing():
    """4 one-way delays when the requesting node (earlier on the route) is
    not the protocol's primary (the lexicographically larger name), 5 when
    it is - the same link is slower in one direction of the route."""
    assert single_heralded_cycle_factor("a", "r1") == SINGLE_HERALDED_CYCLE_FACTOR == 4.0
    assert single_heralded_cycle_factor("r1", "b") == SINGLE_HERALDED_PRIMARY_REQUESTER_CYCLE_FACTOR == 5.0
    assert single_heralded_cycle_factor("b", "r1") == 4.0

    capabilities = NetworkCapabilities(realistic_diamond())
    assert attempt_cycle_s(capabilities, "good1", "good2") == pytest.approx(4 * 2.5e-5)
    assert attempt_cycle_s(capabilities, "r1", "good1") == pytest.approx(5 * 2.5e-5)   # "r1" > "good1"
    assert attempt_cycle_s(capabilities, "good1", "r1") == pytest.approx(4 * 2.5e-5)
    assert attempt_cycle_s(capabilities, "bad", "r3") == pytest.approx(4 * 1e-4)


@pytest.mark.unit
def test_matched_stream_rate_is_the_finite_buffer_matching_queue():
    # two equal streams: the stationary chain gives 3/4 of the stream rate with 2 slots...
    assert matched_stream_rate(100.0, 100.0, 2) == pytest.approx(75.0)
    # ...and tends to the stream rate as the buffer grows (nothing is ever blocked)
    rates = [matched_stream_rate(100.0, 100.0, slots) for slots in (1, 2, 4, 16, 256)]
    assert rates == sorted(rates) and rates[0] == pytest.approx(200 / 3) and 95 < rates[-1] < 100
    # symmetric in its two streams, never above the slower one
    assert matched_stream_rate(100.0, 60.0, 4) == pytest.approx(matched_stream_rate(60.0, 100.0, 4))
    assert matched_stream_rate(100.0, 60.0, 4) < 60.0
    assert matched_stream_rate(1e9, 60.0, 4) == pytest.approx(60.0, rel=1e-3)   # an instantaneous partner costs nothing
    assert matched_stream_rate(0.0, 60.0, 4) == 0.0


@pytest.mark.unit
def test_buffered_rate_composes_swaps_in_the_simulators_order():
    one_swap = matched_stream_rate(100.0, 100.0, 4)
    assert buffered_end_to_end_rate([100.0], 4) == 100.0                        # a direct link has no swap
    assert buffered_end_to_end_rate([100.0, 100.0], 4) == pytest.approx(one_swap)
    # 3 links: node 1 swaps first, node 2 joins the result with the third link
    assert buffered_end_to_end_rate([100.0, 100.0, 80.0], 4) == pytest.approx(matched_stream_rate(one_swap, 80.0, 4))
    # 4 links: nodes 1 and 3 swap first, node 2 joins the two halves
    assert buffered_end_to_end_rate([100.0] * 4, 4) == pytest.approx(matched_stream_rate(one_swap, one_swap, 4))
    # a probabilistic swap loses both pairs when it fails
    assert buffered_end_to_end_rate([100.0, 100.0], 4, [0.5]) == pytest.approx(0.5 * one_swap)
    assert buffered_end_to_end_rate([100.0] * 3, 4, [0.5, 1.0]) == pytest.approx(
        matched_stream_rate(0.5 * one_swap, 100.0, 4))
    with pytest.raises(ValueError, match="one swap success probability per interior node"):
        buffered_end_to_end_rate([100.0, 100.0], 4, [])


@pytest.mark.unit
def test_same_cycle_and_buffered_laws_on_a_calibrated_chain():
    capabilities = NetworkCapabilities(realistic_chain(1, platform=SIV_2024, link_m=5_000))
    route = ["a", "r1", "b"]
    p = hop_success_probability(capabilities, "a", "r1")
    first_cycle = attempt_cycle_s(capabilities, "a", "r1")
    last_cycle = attempt_cycle_s(capabilities, "r1", "b")
    assert last_cycle == pytest.approx(1.25 * first_cycle)   # r1 requests the pairing and is the primary

    same_cycle = estimate_generation(capabilities, route, 4, model="same_cycle")
    assert same_cycle.attempt_rate == pytest.approx(4 / last_cycle)          # the slowest hop
    assert same_cycle.raw_end_to_end_pair_rate == pytest.approx(4 / last_cycle * p * p)

    buffered = estimate_generation(capabilities, route, 4, model="buffered")
    assert buffered.raw_end_to_end_pair_rate == pytest.approx(
        matched_stream_rate(4 * p / first_cycle, 4 * p / last_cycle, 4))
    # the point of the buffered law: the same-cycle law is ~1/p too pessimistic on multi-hop routes...
    assert buffered.raw_end_to_end_pair_rate / same_cycle.raw_end_to_end_pair_rate > 100
    # ...and it lands on what the audit measured for this exact configuration (~150 pairs/s)
    assert buffered.raw_end_to_end_pair_rate == pytest.approx(160.8, rel=1e-2)
    assert same_cycle.raw_end_to_end_pair_rate < 2

    direct = estimate_generation(capabilities, ["a", "r1"], 4, model="buffered")
    assert direct.raw_end_to_end_pair_rate == pytest.approx(4 * p / first_cycle)  # no buffering penalty on one link


@pytest.mark.unit
def test_buffered_law_follows_the_slowest_link():
    capabilities = NetworkCapabilities(realistic_diamond())
    slow = estimate_generation(capabilities, ["r1", "bad", "r3"], 4, model="buffered")
    fast = estimate_generation(capabilities, ["r1", "good1", "good2", "r3"], 4, model="buffered")
    assert fast.raw_end_to_end_pair_rate > 10 * slow.raw_end_to_end_pair_rate


@pytest.mark.unit
def test_legacy_same_cycle_arithmetic_is_unchanged_under_ket_vector():
    spec = three_node_spec(attenuation_db_per_m=1e-5, formalism="ket_vector")
    capabilities = NetworkCapabilities(spec)
    estimate = estimate_generation(capabilities, ["a", "r", "b"], 10, model="same_cycle")
    naive = 10 / (2 * spec.classical_delay_s)
    per_hop = 0.5 * 10 ** (-(1000 * 1e-5) / 10)
    assert estimate.attempt_rate == pytest.approx(naive / BARRETT_KOK_ATTEMPT_RATE_FACTOR)
    assert estimate.raw_end_to_end_pair_rate == pytest.approx(naive / BARRETT_KOK_ATTEMPT_RATE_FACTOR * per_hop ** 2)


@pytest.mark.unit
def test_unknown_generation_model_is_rejected():
    capabilities = NetworkCapabilities(realistic_chain(1))
    with pytest.raises(ValueError, match="unknown generation model"):
        estimate_generation(capabilities, ["a", "r1", "b"], 4, model="psychic")


@pytest.mark.unit
def test_buffered_planners_are_registered_and_identified():
    assert PLANNER_POLICIES["L2-RB"] is BufferedResourceAwarePlanner
    assert PLANNER_POLICIES["L3-RB"] is ProbabilisticBufferedPlanner
    assert resolve_planner_policy("L2-RB").level == "L2-RB"
    assert BufferedResourceAwarePlanner.name == "iterative_resource_aware_buffered"
    assert ProbabilisticBufferedPlanner.level == "L3-RB"
    assert BufferedResourceAwarePlanner.generation_model == ProbabilisticBufferedPlanner.generation_model == "buffered"
    assert ResourceAwareIterativePlanner.generation_model == "same_cycle"


@pytest.mark.unit
def test_on_calibrated_hardware_the_same_cycle_planner_rejects_what_the_buffered_one_admits():
    """The decision-level consequence of the audit: 10 pairs in 0.3 s over a
    calibrated SiV chain is easily deliverable (the simulator delivers ~45),
    L2-R's same-cycle law predicts less than one, L2-RB's buffered law
    predicts 48."""
    spec = realistic_chain(1, platform=SIV_2024, link_m=5_000)
    capabilities = NetworkCapabilities(spec)
    intent = _intent(min_fidelity=0.6, slots=4, pairs=10, duration=0.3)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    candidates = generate_candidate_paths(intent, capabilities, context)

    same_cycle = ResourceAwareIterativePlanner().plan(intent, capabilities, candidates, context)
    buffered = BufferedResourceAwarePlanner().plan(intent, capabilities, candidates, context)
    assert same_cycle.feasible is False
    assert buffered.feasible is True
    assert 40 <= buffered.predicted_delivered_pairs <= 50
    assert buffered.planner_level == "L2-RB" and buffered.selected_plan.purification_mode == "until_target"

    probabilistic = ProbabilisticBufferedPlanner().plan(intent, capabilities, candidates, context)
    assert probabilistic.feasible is True
    assert probabilistic.predicted_satisfaction_probability > 0.99


@pytest.mark.unit
def test_resource_aware_estimate_uses_gate_noise_for_purification_under_bell_diagonal():
    """With demonstrated gates one BBPSSW round does not lift the swapped
    pair, so a target above the swap output is unreachable; with ideal
    operations the same target is one round away."""
    intent = _intent(min_fidelity=0.75, slots=4, pairs=5, duration=0.3)
    route = ["a", "r1", "b"]
    literature = estimate_resource_aware_plan(
        NetworkCapabilities(realistic_chain(1, platform=SIV_2024)), route, intent, generation_model="buffered",
    )
    theoretical = estimate_resource_aware_plan(
        NetworkCapabilities(realistic_chain(1, platform=SIV_2024_THEORETICAL_OPS)), route, intent,
        generation_model="buffered",
    )
    assert literature.fidelity_feasible is False
    assert theoretical.fidelity_feasible is True and theoretical.purification_rounds == 1
