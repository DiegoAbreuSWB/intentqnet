"""Tests for `ibqn.experiments.sweeps.apply_parameters` (Fase H3.1)."""
import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.sweeps import UnknownStrategyError, apply_parameters


@pytest.fixture
def base():
    spec = three_node_spec()
    intent = simple_intent(intent_id="x", source="a", destination="b", min_fidelity=0.6, requested_pairs=10, duration=0.1)
    return spec, intent


@pytest.mark.unit
def test_apply_parameters_does_not_mutate_originals(base):
    spec, intent = base
    original_attenuation = spec.quantum_links[0].attenuation_db_per_m
    original_min_fidelity = intent.requirements.min_fidelity

    apply_parameters(spec, intent, {"attenuation_db_per_m": 9e-4, "min_fidelity": 0.99})

    assert spec.quantum_links[0].attenuation_db_per_m == original_attenuation
    assert intent.requirements.min_fidelity == original_min_fidelity


@pytest.mark.unit
def test_apply_parameters_updates_topology_fields_on_every_link_and_node(base):
    spec, intent = base
    params = apply_parameters(spec, intent, {"attenuation_db_per_m": 9e-4, "distance_m": 500, "raw_fidelity": 0.7})
    assert all(link.attenuation_db_per_m == 9e-4 for link in params.topology_spec.quantum_links)
    assert all(link.distance_m == 500 for link in params.topology_spec.quantum_links)
    assert all(node.raw_fidelity == 0.7 for node in params.topology_spec.nodes)


@pytest.mark.unit
def test_apply_parameters_updates_intent_requirements(base):
    spec, intent = base
    params = apply_parameters(spec, intent, {"min_fidelity": 0.9, "reserved_memory_slots": 20, "duration_s": 0.5})
    assert params.intent.requirements.min_fidelity == 0.9
    assert params.intent.requirements.reserved_memory_slots == 20
    assert params.intent.requirements.duration_s == 0.5


@pytest.mark.unit
def test_apply_parameters_selects_strategies(base):
    spec, intent = base
    params = apply_parameters(spec, intent, {"routing_strategy": "least_loss", "purification_policy": "disabled", "reconciliation_enabled": True})
    assert params.routing_strategy_name == "least_loss"
    assert params.purification_policy_name == "disabled"
    assert params.reconciliation_enabled is True


@pytest.mark.unit
def test_apply_parameters_rejects_unknown_strategy_name(base):
    spec, intent = base
    with pytest.raises(UnknownStrategyError):
        apply_parameters(spec, intent, {"routing_strategy": "not_a_real_strategy"})


@pytest.mark.unit
def test_apply_parameters_default_strategy_selection_when_not_swept(base):
    spec, intent = base
    params = apply_parameters(spec, intent, {"min_fidelity": 0.7})
    assert params.routing_strategy_name == "shortest_hop_count"
    assert params.purification_policy_name == "automatic"
    assert params.reconciliation_enabled is False
