"""P01 campaign configs must load, validate, and expand exactly as
intended - and must never reference F01-F08's raw/processed data (planner
study writes to its own `results/planner_study/` tree, per
docs/planner_study_baseline.md).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from ibqn.experiments.campaigns import load_campaign_file
from ibqn.experiments.sweeps import expand_parameter_grid

PROJECT_ROOT = Path(__file__).resolve().parents[3]
CAMPAIGN_DIR = PROJECT_ROOT / "configs" / "campaigns" / "planner_study"

P01_CAMPAIGNS = [
    "P01_l1_l2_purification_three_node.yaml",
    "P01_l1_l2_purification_four_node.yaml",
]

DENSIFIED_THRESHOLDS = [0.65, 0.70, 0.72, 0.73, 0.735, 0.74, 0.745, 0.75]


@pytest.mark.unit
@pytest.mark.parametrize("filename", P01_CAMPAIGNS)
def test_p01_campaign_loads_and_validates(filename):
    spec = load_campaign_file(CAMPAIGN_DIR / filename)
    assert spec.name.startswith("P01_l1_l2_purification")


@pytest.mark.unit
@pytest.mark.parametrize("filename", P01_CAMPAIGNS)
def test_p01_campaign_sweeps_both_planner_levels(filename):
    spec = load_campaign_file(CAMPAIGN_DIR / filename)
    assert set(spec.strategies["purification"]) == {"automatic", "iterative_analytical"}


@pytest.mark.unit
@pytest.mark.parametrize("filename", P01_CAMPAIGNS)
def test_p01_campaign_sweeps_the_exact_densified_threshold_range(filename):
    spec = load_campaign_file(CAMPAIGN_DIR / filename)
    assert spec.parameter_grid["min_fidelity"] == DENSIFIED_THRESHOLDS


@pytest.mark.unit
@pytest.mark.parametrize("filename", P01_CAMPAIGNS)
def test_p01_campaign_uses_20_seeds(filename):
    spec = load_campaign_file(CAMPAIGN_DIR / filename)
    assert len(spec.seeds) == 20
    assert spec.seeds == list(range(20))


@pytest.mark.unit
@pytest.mark.parametrize("filename", P01_CAMPAIGNS)
def test_p01_campaign_expects_320_trials(filename):
    spec = load_campaign_file(CAMPAIGN_DIR / filename)
    combinations = expand_parameter_grid(spec.effective_parameter_grid())
    expected = len(combinations) * len(spec.seeds) * len(spec.intents)
    assert expected == 320


@pytest.mark.unit
@pytest.mark.parametrize("filename", P01_CAMPAIGNS)
def test_p01_campaign_writes_to_its_own_results_tree_never_f0x(filename):
    spec = load_campaign_file(CAMPAIGN_DIR / filename)
    assert spec.output_directory == "results/planner_study"
    assert "F0" not in spec.output_directory


@pytest.mark.unit
@pytest.mark.parametrize("filename", P01_CAMPAIGNS)
def test_p01_campaign_records_planner_level_metadata(filename):
    spec = load_campaign_file(CAMPAIGN_DIR / filename)
    mapping = spec.metadata["planner_level_by_purification_policy"]
    assert mapping == {"automatic": "L1", "iterative_analytical": "L2"}


@pytest.mark.unit
def test_p01_three_node_topology_matches_f03_three_node_1_repeater():
    """Same physical parameters as F03's three_node_1_repeater - any
    behavioral difference P01 finds must be attributable to the planner
    change alone (docs/planner_study_baseline.md)."""
    from ibqn.demos.topologies import three_node_spec
    from ibqn.experiments.scenarios import Scenario

    scenario = Scenario.load(CAMPAIGN_DIR / "../scenarios/three_node.yaml")
    p01_spec = scenario.topology_spec()
    f03_spec = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)

    p01_by_id = {n.id: n for n in p01_spec.nodes}
    f03_by_id = {n.id: n for n in f03_spec.nodes}
    assert set(p01_by_id) == set(f03_by_id)
    for node_id in p01_by_id:
        assert p01_by_id[node_id].raw_fidelity == f03_by_id[node_id].raw_fidelity
        assert p01_by_id[node_id].swapping_degradation == f03_by_id[node_id].swapping_degradation


@pytest.mark.unit
def test_p01_four_node_topology_matches_f03_linear_chain_2_repeaters():
    from ibqn.experiments.scenarios import Scenario
    from ibqn.experiments.topology_catalog import linear_chain_spec

    scenario = Scenario.load(CAMPAIGN_DIR / "scenarios" / "four_node_chain.yaml")
    p01_spec = scenario.topology_spec()
    f03_spec = linear_chain_spec(2, attenuation_db_per_m=1e-5, stop_time_s=0.2)

    p01_by_id = {n.id: n for n in p01_spec.nodes}
    f03_by_id = {n.id: n for n in f03_spec.nodes}
    assert set(p01_by_id) == set(f03_by_id)
    for node_id in p01_by_id:
        assert p01_by_id[node_id].raw_fidelity == f03_by_id[node_id].raw_fidelity
        assert p01_by_id[node_id].memories == f03_by_id[node_id].memories
