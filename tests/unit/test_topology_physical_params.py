"""Tests for the physical-parameter plumbing in
`ibqn.network.topology.NetworkTopologySpec.to_router_net_topo_config`
(docs/physical_model.md): every hardware parameter must reach SeQUeNCe
through `RouterNetTopo` templates, and only the parameters the active
formalism's protocols understand may be emitted.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ibqn.network.topology import (
    DEFAULT_COHERENCE_TIME_S,
    DEFAULT_CUTOFF_RATIO,
    DEFAULT_FORMALISM,
    NetworkTopologySpec,
    NodeSpec,
    QuantumLinkSpec,
)


def _spec(formalism=None, *, detector_efficiency=None, **node_kwargs) -> NetworkTopologySpec:
    kwargs = {"formalism": formalism} if formalism else {}
    return NetworkTopologySpec(
        nodes=[NodeSpec(id="a", memories=4, **node_kwargs), NodeSpec(id="b", memories=4)],
        quantum_links=[QuantumLinkSpec(source="a", destination="b", distance_m=1000, attenuation_db_per_m=1e-5,
                                       detector_efficiency=detector_efficiency)],
        stop_time_s=1.0, **kwargs,
    )


@pytest.mark.unit
def test_defaults_are_the_physically_realistic_model():
    spec = _spec()
    assert spec.formalism == DEFAULT_FORMALISM == "bell_diagonal"
    node = spec.nodes[0]
    assert node.coherence_time_s == DEFAULT_COHERENCE_TIME_S > 0
    assert node.cutoff_ratio == DEFAULT_CUTOFF_RATIO
    assert node.gate_fidelity == node.measurement_fidelity == node.swapping_success_prob == 1.0
    assert node.decoherence_errors is None  # -> SeQUeNCe's depolarizing default


@pytest.mark.unit
def test_bell_diagonal_config_uses_single_heralded_bsm_and_omits_swapping_degradation():
    config = _spec(gate_fidelity=0.9, decoherence_errors=(0.5, 0.25, 0.25), memory_efficiency=0.8,
                   memory_frequency_hz=2e8).to_router_net_topo_config(seed=0)
    assert config["formalism"] == "bell_diagonal"
    a_template = config["templates"][config["nodes"][0]["template"]]
    assert a_template["MemoryArray"] == {
        "fidelity": 0.85, "coherence_time": DEFAULT_COHERENCE_TIME_S, "cutoff_ratio": DEFAULT_CUTOFF_RATIO,
        "efficiency": 0.8, "frequency": 2e8, "decoherence_errors": [0.5, 0.25, 0.25],
    }
    assert a_template["EntanglementSwapping"] == {"swapping_success_prob": 1.0}  # no `degradation` kwarg for the BDS class
    b_template = config["templates"][config["nodes"][1]["template"]]
    assert "decoherence_errors" not in b_template["MemoryArray"]  # None -> let MemoryArray apply its default
    bsm_template = config["templates"][config["qconnections"][0]["template"]]
    assert bsm_template == {"encoding_type": "single_heralded"}  # detectors: SeQUeNCe defaults


@pytest.mark.unit
def test_ket_vector_config_keeps_the_legacy_barrett_kok_wiring():
    config = _spec("ket_vector", swapping_degradation=0.9, coherence_time_s=-1, detector_efficiency=0.95,
                   decoherence_errors=(0.5, 0.25, 0.25)).to_router_net_topo_config(seed=0)
    assert config["formalism"] == "ket_vector"
    a_template = config["templates"][config["nodes"][0]["template"]]
    assert a_template["EntanglementSwapping"] == {"swapping_success_prob": 1.0, "swapping_degradation": 0.9}
    assert a_template["MemoryArray"]["coherence_time"] == -1
    assert "decoherence_errors" not in a_template["MemoryArray"]  # MemoryArray asserts BDS-only for this key
    bsm_template = config["templates"][config["qconnections"][0]["template"]]
    assert bsm_template == {
        "encoding_type": "single_atom",
        "SingleAtomBSM": {"detectors": [{"efficiency": 0.95}, {"efficiency": 0.95}]},
    }


@pytest.mark.unit
def test_seeds_and_structure_are_unchanged_by_the_templates():
    config = _spec().to_router_net_topo_config(seed=7)
    assert [n["seed"] for n in config["nodes"]] == [7, 8]
    assert config["qconnections"][0]["seed"] == 9
    assert config["qconnections"][0]["type"] == "meet_in_the_middle"
    assert config["cconnections"] == [{"node1": "a", "node2": "b", "delay": int(1e-3 * 1e12)}]
    assert config["stop_time"] == int(1e12)


@pytest.mark.unit
def test_validation_of_new_parameters():
    with pytest.raises(ValidationError):
        NodeSpec(id="x", memories=1, decoherence_errors=(0.5, 0.5, 0.5))
    with pytest.raises(ValidationError):
        NodeSpec(id="x", memories=1, gate_fidelity=1.2)
    with pytest.raises(ValidationError):
        NodeSpec(id="x", memories=1, cutoff_ratio=0)
    with pytest.raises(ValidationError):
        _spec("density_matrix")
    with pytest.raises(ValidationError, match="unique"):
        NetworkTopologySpec(
            nodes=[NodeSpec(id="a", memories=1), NodeSpec(id="a", memories=1)],
            quantum_links=[QuantumLinkSpec(source="a", destination="a", distance_m=1, attenuation_db_per_m=1e-5)],
            stop_time_s=1.0,
        )
    assert NodeSpec(id="x", memories=1, coherence_time_s=-1).infinite_coherence
    assert not NodeSpec(id="x", memories=1).infinite_coherence
