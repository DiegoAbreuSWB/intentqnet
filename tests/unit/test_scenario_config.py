"""Tests for `ibqn.config.schemas.ScenarioSpec` / `ibqn.config.loader` -
pure parsing/validation, no SeQUeNCe simulation involved.
"""
import pytest
from pydantic import ValidationError

from ibqn.config.loader import load_scenario_file
from ibqn.config.schemas import IntentReference, ScenarioSpec, SimulationSpec
from ibqn.network.topology import NodeSpec, QuantumLinkSpec


def build_scenario_spec(**overrides) -> ScenarioSpec:
    defaults = dict(
        name="test-scenario",
        simulation=SimulationSpec(duration_s=0.1, seed=1),
        nodes=[NodeSpec(id="A", memories=10), NodeSpec(id="B", memories=10)],
        quantum_links=[QuantumLinkSpec(source="A", destination="B", distance_m=1000, attenuation_db_per_m=1e-5)],
        intents=[IntentReference(file="intents/intent_001.yaml")],
    )
    defaults.update(overrides)
    return ScenarioSpec(**defaults)


@pytest.mark.unit
def test_scenario_spec_converts_to_network_topology_spec():
    scenario = build_scenario_spec()
    topology_spec = scenario.to_network_topology_spec()

    assert [n.id for n in topology_spec.nodes] == ["A", "B"]
    assert topology_spec.stop_time_s == 0.1
    assert topology_spec.classical_delay_s == scenario.classical_delay_s


@pytest.mark.unit
def test_scenario_spec_rejects_undeclared_node_in_quantum_link_at_conversion_time():
    scenario = build_scenario_spec(
        quantum_links=[QuantumLinkSpec(source="A", destination="ghost", distance_m=1000, attenuation_db_per_m=1e-5)]
    )
    with pytest.raises(ValidationError, match="undeclared node"):
        scenario.to_network_topology_spec()


@pytest.mark.unit
def test_scenario_spec_requires_at_least_one_intent():
    with pytest.raises(ValidationError):
        build_scenario_spec(intents=[])


@pytest.mark.unit
def test_load_scenario_file_accepts_bare_mapping_without_scenario_wrapper(tmp_path):
    scenario_file = tmp_path / "bare.yaml"
    scenario_file.write_text(
        """
name: bare-scenario
simulation:
  duration_s: 0.1
  seed: 1
nodes:
  - id: A
    memories: 10
  - id: B
    memories: 10
quantum_links:
  - source: A
    destination: B
    distance_m: 1000
    attenuation_db_per_m: 0.00001
intents:
  - file: intents/intent_001.yaml
""",
        encoding="utf-8",
    )
    spec = load_scenario_file(scenario_file)
    assert spec.name == "bare-scenario"


@pytest.mark.unit
def test_load_scenario_file_accepts_scenario_wrapper(tmp_path):
    scenario_file = tmp_path / "wrapped.yaml"
    scenario_file.write_text(
        """
scenario:
  name: wrapped-scenario
  simulation:
    duration_s: 0.1
    seed: 1
  nodes:
    - id: A
      memories: 10
    - id: B
      memories: 10
  quantum_links:
    - source: A
      destination: B
      distance_m: 1000
      attenuation_db_per_m: 0.00001
  intents:
    - file: intents/intent_001.yaml
""",
        encoding="utf-8",
    )
    spec = load_scenario_file(scenario_file)
    assert spec.name == "wrapped-scenario"
