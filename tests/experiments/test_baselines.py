"""Tests for `ibqn.experiments.baselines` (Fase J3) - see docs/baselines.md.

Uses the same diamond topology/intent calibration as
`tests/integration/test_reconciliation.py` (`bad` fast-but-lossy,
`good1`/`good2` slow-but-sufficient) so the three baselines can be
compared against each other and against the real IBQN pipeline on a
topology where the "right" route genuinely matters.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import diamond_intent, simple_intent
from ibqn.demos.topologies import diamond_spec, three_node_spec
from ibqn.experiments.baselines import (
    run_native_sequence_baseline,
    run_offline_oracle_baseline,
    run_static_provisioning_baseline,
)
from ibqn.planning.routing import LeastLossRouting, ShortestHopCountRouting


@pytest.mark.unit
def test_native_sequence_baseline_uses_default_forwarding_and_no_planner():
    """`RouterNetTopo`'s auto-generated static routing table weights each
    edge by physical distance (`router_net_topo.py:192-208`), not hop
    count - confirmed empirically here: on the diamond topology, the
    3-hop good1/good2 detour (1500 m total) is shorter in DISTANCE than
    the 2-hop bad link (2000 m total), so native SeQUeNCe routing picks
    the detour despite it having more hops. This is genuinely different
    from `ShortestHopCountRouting`'s own (hop-count-only) criterion - see
    the correction in planning.routing.ShortestHopCountRouting's
    docstring and docs/baselines.md."""
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    result = run_native_sequence_baseline(spec, intent, seed=0)

    assert result.baseline_name == "native_sequence"
    assert result.accepted is True
    assert result.planning_wall_time_s == 0.0
    assert result.delivered_pairs is not None
    assert result.route == ["r1", "good1", "good2", "r3"]


@pytest.mark.unit
def test_native_sequence_baseline_reports_fidelity_via_passive_probe():
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    result = run_native_sequence_baseline(spec, intent, seed=0)

    assert result.average_fidelity is not None
    assert 0.0 <= result.average_fidelity <= 1.0


@pytest.mark.unit
def test_static_provisioning_baseline_never_rejects_upfront():
    """A static baseline with an impossibly high fidelity target must
    still attempt the reservation (no feasibility check exists) rather
    than reject it the way IntentPlanner would - it can only fail at
    runtime (VIOLATED after evaluation), never REJECTED before running."""
    spec = three_node_spec()
    intent = simple_intent(
        intent_id="unreachable-fidelity", source="a", destination="b",
        min_fidelity=0.999999, requested_pairs=10,  # unreachable, even with purification
    )

    result = run_static_provisioning_baseline(spec, intent, seed=0, routing_strategy=ShortestHopCountRouting())

    assert result.route  # a route was chosen and actually attempted
    assert result.accepted is True  # RSVPProtocol only checks memory/time, not fidelity feasibility
    assert result.satisfied is False  # but the delivered fidelity falls short


@pytest.mark.unit
def test_static_provisioning_baseline_picks_the_strategys_first_candidate():
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    shortest = run_static_provisioning_baseline(spec, intent, seed=0, routing_strategy=ShortestHopCountRouting())
    least_loss = run_static_provisioning_baseline(spec, intent, seed=0, routing_strategy=LeastLossRouting())

    assert shortest.route == ["r1", "bad", "r3"]
    assert least_loss.route == ["r1", "good1", "good2", "r3"]
    assert shortest.candidates_evaluated == 1
    assert least_loss.candidates_evaluated == 1


@pytest.mark.unit
def test_offline_oracle_evaluates_every_candidate_and_picks_the_best():
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    result = run_offline_oracle_baseline(spec, intent, seed=0)

    assert result.baseline_name == "offline_oracle"
    assert result.candidates_evaluated == 2  # exactly two simple paths exist in the diamond topology
    assert result.satisfied is True
    # the oracle must do at least as well as the best single fixed strategy on this topology
    least_loss = run_static_provisioning_baseline(spec, intent, seed=0, routing_strategy=LeastLossRouting())
    assert (result.delivered_pairs or 0) >= (least_loss.delivered_pairs or 0)


@pytest.mark.unit
def test_offline_oracle_rejects_topologies_with_too_many_candidate_paths():
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    with pytest.raises(ValueError, match="offline oracle only supports small topologies"):
        run_offline_oracle_baseline(spec, intent, seed=0, max_candidates=1)


@pytest.mark.unit
def test_offline_oracle_notes_it_is_not_an_online_strategy():
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    result = run_offline_oracle_baseline(spec, intent, seed=0)

    assert "not an online-implementable strategy" in result.notes


@pytest.mark.unit
def test_all_three_baselines_share_the_same_seed_topology_and_intent():
    """A minimal fairness check (docs/baselines.md, "Comparação justa"):
    every baseline accepts the exact same topology_spec/intent/seed
    arguments, so none of them can silently vary the physical setup."""
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    native = run_native_sequence_baseline(spec, intent, seed=0)
    static = run_static_provisioning_baseline(spec, intent, seed=0)
    oracle = run_offline_oracle_baseline(spec, intent, seed=0)

    assert {native.seed, static.seed, oracle.seed} == {0}
    assert {native.intent_id, static.intent_id, oracle.intent_id} == {intent.id}
