"""Tests for `ibqn.experiments.programmatic_campaign` (Fase J10) - the
in-memory variant of `CampaignRunner` used by the F02/F03/F07/F08 final
campaigns, whose topologies come from `experiments.topology_catalog`
rather than checked-in YAML fixtures.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.persistence import read_trials_dataframe, trials_csv_path
from ibqn.experiments.programmatic_campaign import run_programmatic_campaign


@pytest.mark.unit
def test_runs_expected_trials_and_persists_them(tmp_path):
    spec = three_node_spec()
    intent = simple_intent(intent_id="prog-1", source="a", destination="b", min_fidelity=0.6, requested_pairs=10)

    summary = run_programmatic_campaign(
        campaign_name="TEST_PROG", scenario_name="three_node", base_topology=spec, base_intents=[intent],
        parameter_grid={}, seeds=[0, 1], output_directory=str(tmp_path),
    )

    assert summary.expected_trials == 2
    assert summary.completed_trials == 2
    assert summary.failed_trials == 0

    df = read_trials_dataframe(trials_csv_path(tmp_path, "TEST_PROG"))
    assert len(df) == 2
    assert set(df["seed"]) == {0, 1}


@pytest.mark.unit
def test_resume_skips_already_completed_trials(tmp_path):
    spec = three_node_spec()
    intent = simple_intent(intent_id="prog-2", source="a", destination="b", min_fidelity=0.6, requested_pairs=10)

    run_programmatic_campaign(
        campaign_name="TEST_PROG_RESUME", scenario_name="three_node", base_topology=spec, base_intents=[intent],
        parameter_grid={}, seeds=[0], output_directory=str(tmp_path),
    )
    second = run_programmatic_campaign(
        campaign_name="TEST_PROG_RESUME", scenario_name="three_node", base_topology=spec, base_intents=[intent],
        parameter_grid={}, seeds=[0, 1], output_directory=str(tmp_path),
    )

    assert second.skipped_trials == 1
    assert second.completed_trials == 1

    df = read_trials_dataframe(trials_csv_path(tmp_path, "TEST_PROG_RESUME"))
    assert len(df) == 2


@pytest.mark.unit
def test_parameter_grid_is_swept_correctly(tmp_path):
    spec = three_node_spec()
    intent = simple_intent(intent_id="prog-3", source="a", destination="b", min_fidelity=0.5, requested_pairs=10)

    summary = run_programmatic_campaign(
        campaign_name="TEST_PROG_GRID", scenario_name="three_node", base_topology=spec, base_intents=[intent],
        parameter_grid={"min_fidelity": [0.5, 0.6]}, seeds=[0], output_directory=str(tmp_path),
    )

    assert summary.expected_trials == 2
    df = read_trials_dataframe(trials_csv_path(tmp_path, "TEST_PROG_GRID"))
    assert set(df["requested_fidelity"]) == {0.5, 0.6}
