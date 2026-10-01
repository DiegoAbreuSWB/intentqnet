"""Tests for `ibqn.network.platforms` (docs/parameter_calibration.md): the
literature-calibrated hardware profiles and how they are applied to
topologies, scenarios, sweeps and trial records.
"""
from __future__ import annotations

import pytest

from ibqn.config.schemas import IntentReference, ScenarioSpec, SimulationSpec
from ibqn.demos.intents import simple_intent
from ibqn.experiments.records import TrialRecord
from ibqn.experiments.sweeps import SWEEP_PARAMETERS, apply_parameters
from ibqn.experiments.topology_catalog import linear_chain_spec
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.platforms import (
    DEFAULT_PLATFORM,
    NV_2022,
    PLATFORMS,
    SIV_2024,
    TRAPPED_ION_2023,
    UnknownPlatformError,
    apply_platform,
    classical_delay_s,
    resolve_platform,
)
from ibqn.network.topology import NodeSpec, QuantumLinkSpec
from ibqn.physics import bds_swap_fidelity


@pytest.mark.unit
def test_every_profile_is_physically_bounded_and_sourced():
    for name, profile in PLATFORMS.items():
        assert profile.name == name
        assert 0.5 < profile.raw_fidelity <= 1.0
        assert 0.0 < profile.gate_fidelity <= 1.0 and 0.0 < profile.measurement_fidelity <= 1.0
        assert 0.0 <= profile.swapping_success_prob <= 1.0
        assert profile.coherence_time_s > 0
        assert abs(sum(profile.decoherence_errors) - 1.0) < 1e-9
        assert 0.0 < profile.memory_efficiency <= 1.0
        assert profile.memory_frequency_hz > 0
        assert 0.0 < profile.detector_efficiency <= 1.0
        assert profile.attenuation_db_per_m > 0
        if name != "idealized_legacy":
            assert profile.sources, f"{name} must cite at least one peer-reviewed source"


@pytest.mark.unit
def test_demonstrated_profiles_are_not_the_idealized_legacy_values():
    """Guards the point of the calibration: no demonstrated platform has
    ideal gates, unit emission efficiency or a 0.01 dB/km fiber."""
    for name in ("siv_2024", "trapped_ion_2023", "nv_2022", "atomic_ensemble_2024"):
        profile = PLATFORMS[name]
        assert profile.memory_efficiency < 1.0
        assert profile.attenuation_db_per_m >= 1.4e-4  # the world-record fiber is 0.14 dB/km
        assert profile.gate_fidelity < 1.0 or profile.swapping_success_prob < 1.0


@pytest.mark.unit
def test_default_platform_is_the_siv_baseline():
    assert DEFAULT_PLATFORM is SIV_2024
    assert resolve_platform("siv_2024") is SIV_2024
    with pytest.raises(UnknownPlatformError, match="unknown platform"):
        resolve_platform("unobtainium_2099")


@pytest.mark.unit
def test_profile_node_and_link_builders_apply_every_field_and_allow_overrides():
    node = TRAPPED_ION_2023.node("r1", 6, raw_fidelity=0.9)
    assert node.id == "r1" and node.memories == 6
    assert node.raw_fidelity == 0.9  # explicit override wins
    assert node.gate_fidelity == TRAPPED_ION_2023.gate_fidelity
    assert node.coherence_time_s == TRAPPED_ION_2023.coherence_time_s
    assert node.decoherence_errors == TRAPPED_ION_2023.decoherence_errors == (0.0, 0.0, 1.0)
    assert node.memory_efficiency == TRAPPED_ION_2023.memory_efficiency
    link = TRAPPED_ION_2023.link("a", "b", 5000)
    assert link.attenuation_db_per_m == TRAPPED_ION_2023.attenuation_db_per_m
    assert link.detector_efficiency == TRAPPED_ION_2023.detector_efficiency


@pytest.mark.unit
def test_apply_platform_keeps_structure_and_replaces_hardware():
    base = linear_chain_spec(2, distance_m=5000, end_memories=4, repeater_memories=8)
    spec = apply_platform(base, SIV_2024)
    assert [n.id for n in spec.nodes] == [n.id for n in base.nodes]
    assert [n.memories for n in spec.nodes] == [4, 8, 8, 4]
    assert [l.distance_m for l in spec.quantum_links] == [5000.0] * 3
    assert spec.platform == "siv_2024"
    assert spec.formalism == base.formalism
    assert spec.classical_delay_s == pytest.approx(classical_delay_s(5000)) == pytest.approx(2.5e-5)
    for node in spec.nodes:
        assert node.raw_fidelity == SIV_2024.raw_fidelity
        assert node.gate_fidelity == SIV_2024.gate_fidelity
        assert node.coherence_time_s == SIV_2024.coherence_time_s
    for link in spec.quantum_links:
        assert link.attenuation_db_per_m == SIV_2024.attenuation_db_per_m
    # the planner's physics sees the profile's gate noise
    swap = NetworkCapabilities(spec).physics.swap_fidelity(SIV_2024.raw_fidelity, SIV_2024.raw_fidelity, "r1")
    assert swap == pytest.approx(bds_swap_fidelity(0.86, 0.86, gate_fidelity=0.937, measurement_fidelity=0.995))


@pytest.mark.unit
def test_scenario_yaml_platform_key_applies_the_profile():
    scenario = ScenarioSpec(
        name="s", simulation=SimulationSpec(duration_s=1.0, seed=0),
        nodes=[NodeSpec(id="a", memories=4), NodeSpec(id="b", memories=4)],
        quantum_links=[QuantumLinkSpec(source="a", destination="b", distance_m=10_000, attenuation_db_per_m=1e-5)],
        platform="trapped_ion_2023", intents=[IntentReference(file="i.yaml")],
    )
    spec = scenario.to_network_topology_spec()
    assert spec.platform == "trapped_ion_2023"
    assert spec.quantum_links[0].attenuation_db_per_m == TRAPPED_ION_2023.attenuation_db_per_m  # YAML value replaced
    assert spec.nodes[0].memory_efficiency == TRAPPED_ION_2023.memory_efficiency
    assert spec.classical_delay_s == pytest.approx(5e-5)
    # without the key, hand-set values stand
    plain = scenario.model_copy(update={"platform": None}).to_network_topology_spec()
    assert plain.platform is None and plain.quantum_links[0].attenuation_db_per_m == 1e-5


@pytest.mark.unit
def test_platform_is_a_sweep_parameter_and_a_trial_record_column():
    assert "platform" in SWEEP_PARAMETERS
    base = linear_chain_spec(1)
    intent = simple_intent(intent_id="x", source="a", destination="b", min_fidelity=0.6, requested_pairs=4, duration=0.1)
    params = apply_parameters(base, intent, {"platform": "nv_2022"})
    assert params.topology_spec.platform == "nv_2022"
    assert params.topology_spec.nodes[0].memory_efficiency == NV_2022.memory_efficiency
    assert "platform" in TrialRecord.fieldnames()


@pytest.mark.unit
def test_single_field_sweeps_are_applied_on_top_of_the_platform_not_overwritten_by_it():
    """Grid order is alphabetical (`coherence_time_s` < `gate_fidelity` <
    `platform`), but a platform replaces every hardware field - it has to go
    first so a one-parameter sweep around a platform survives."""
    base = linear_chain_spec(1)
    intent = simple_intent(intent_id="x", source="a", destination="b", min_fidelity=0.6, requested_pairs=4, duration=0.1)
    params = apply_parameters(
        base, intent, {"coherence_time_s": 0.05, "gate_fidelity": 0.99, "platform": "siv_2024"},
    )
    node = params.topology_spec.nodes[1]
    assert params.topology_spec.platform == "siv_2024"
    assert node.gate_fidelity == 0.99 and node.coherence_time_s == 0.05   # the swept values
    assert node.raw_fidelity == SIV_2024.raw_fidelity                       # everything else from the profile
    assert node.measurement_fidelity == SIV_2024.measurement_fidelity
