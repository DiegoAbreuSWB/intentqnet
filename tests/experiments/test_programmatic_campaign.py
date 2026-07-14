"""Tests for `ibqn.experiments.programmatic_campaign` (Fase J10) - the
in-memory variant of `CampaignRunner` used by the F02/F03/F07/F08 final
campaigns, whose topologies come from `experiments.topology_catalog`
rather than checked-in YAML fixtures.
"""
from __future__ import annotations

import tempfile

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import diamond_spec, three_node_spec
from ibqn.experiments.manifests import manifest_path, read_manifest
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


@pytest.mark.unit
def test_manifest_accumulates_across_scenario_blocks_instead_of_overwriting():
    """Regression test (Fase K1): found empirically auditing F02/F03's
    manifests - calling run_programmatic_campaign twice under the same
    campaign_name (once per topology, exactly what the F02/F03 scripts
    do) used to leave the manifest reporting only the SECOND call's own
    scenario/trial count, even though trials.csv correctly held every
    trial from both calls. The manifest must instead report the union of
    scenarios and the sum of trials across every block."""
    with tempfile.TemporaryDirectory() as tmp_path:
        three_node = three_node_spec()
        three_node_intent = simple_intent(intent_id="prog-block-a", source="a", destination="b", min_fidelity=0.6, requested_pairs=10)
        run_programmatic_campaign(
            campaign_name="TEST_PROG_BLOCKS", scenario_name="three_node", base_topology=three_node,
            base_intents=[three_node_intent], parameter_grid={"min_fidelity": [0.5, 0.6]}, seeds=[0, 1],
            output_directory=tmp_path,
        )
        diamond = diamond_spec()
        diamond_intent_obj = simple_intent(intent_id="prog-block-b", source="a", destination="b", min_fidelity=0.6, requested_pairs=10)
        run_programmatic_campaign(
            campaign_name="TEST_PROG_BLOCKS", scenario_name="diamond", base_topology=diamond,
            base_intents=[diamond_intent_obj], parameter_grid={}, seeds=[0, 1, 2], output_directory=tmp_path,
        )

        manifest = read_manifest(manifest_path(tmp_path, "TEST_PROG_BLOCKS"))
        assert set(manifest["scenario_files"]) == {"three_node", "diamond"}
        assert manifest["expected_trials"] == 4 + 3  # 2 fidelities x 2 seeds, plus 1 x 3 seeds
        assert manifest["completed_trials"] == 4 + 3
        assert len(manifest["blocks"]) == 2

        three_node_block = next(b for b in manifest["blocks"] if b["scenario"] == "three_node")
        assert three_node_block["completed_trials"] == 4
        assert three_node_block["swept_factors"] == {"min_fidelity": [0.5, 0.6]}

        diamond_block = next(b for b in manifest["blocks"] if b["scenario"] == "diamond")
        assert diamond_block["completed_trials"] == 3
        assert diamond_block["swept_factors"] == {}
        # nothing swept in this block, so every strategy kwarg is "fixed" (base_configuration)
        assert diamond_block["base_configuration"]["routing_strategy"] == "shortest_hop_count"


@pytest.mark.unit
def test_manifest_excludes_swept_dimensions_from_base_configuration():
    """A dimension that's actually being varied via parameter_grid must
    never also appear in base_configuration - found ambiguous in the
    original manifest schema (Fase K1): `strategies.routing` held only
    the unused kwarg default even when routing_strategy was the swept
    factor, contradicting parameter_grid."""
    with tempfile.TemporaryDirectory() as tmp_path:
        spec = three_node_spec()
        intent = simple_intent(intent_id="prog-basecfg", source="a", destination="b", min_fidelity=0.5, requested_pairs=10)
        run_programmatic_campaign(
            campaign_name="TEST_PROG_BASECFG", scenario_name="three_node", base_topology=spec, base_intents=[intent],
            parameter_grid={"routing_strategy": ["shortest_hop_count", "least_loss"]}, seeds=[0],
            output_directory=tmp_path,
        )
        manifest = read_manifest(manifest_path(tmp_path, "TEST_PROG_BASECFG"))
        block = manifest["blocks"][0]
        assert "routing_strategy" not in block["base_configuration"]
        # order is not significant (swept_factors is sorted for deterministic merging - see
        # test_manifest_merges_grid_when_extending_an_existing_scenario_block), only membership
        assert set(block["swept_factors"]["routing_strategy"]) == {"shortest_hop_count", "least_loss"}
        assert block["base_configuration"]["purification_policy"] == "automatic"


@pytest.mark.unit
def test_manifest_skipped_trials_is_derived_not_double_counted_on_replay():
    """Regression test (Fase K1): a "replay" call over an already-complete
    campaign (every trial_id already known, e.g. while repairing a
    manifest without re-running any simulation) must report
    skipped_trials=0, not the session-local "trials skipped this call"
    count - completed_trials is already ground truth (it counts trials
    completed in ANY session), so treating a session-local skip count as
    a separate additive bucket would double-count against it and break
    expected == completed + failed + skipped."""
    with tempfile.TemporaryDirectory() as tmp_path:
        spec = three_node_spec()
        intent = simple_intent(intent_id="prog-replay", source="a", destination="b", min_fidelity=0.6, requested_pairs=10)
        run_programmatic_campaign(
            campaign_name="TEST_PROG_REPLAY", scenario_name="three_node", base_topology=spec, base_intents=[intent],
            parameter_grid={}, seeds=[0, 1, 2], output_directory=tmp_path,
        )
        # replay: same call again, every trial_id already known, 0 new simulations
        run_programmatic_campaign(
            campaign_name="TEST_PROG_REPLAY", scenario_name="three_node", base_topology=spec, base_intents=[intent],
            parameter_grid={}, seeds=[0, 1, 2], output_directory=tmp_path,
        )

        manifest = read_manifest(manifest_path(tmp_path, "TEST_PROG_REPLAY"))
        assert manifest["expected_trials"] == 3
        assert manifest["completed_trials"] == 3
        assert manifest["skipped_trials"] == 0
        assert manifest["failed_trials"] == 0
        assert manifest["expected_trials"] == manifest["completed_trials"] + manifest["failed_trials"] + manifest["skipped_trials"]


@pytest.mark.unit
def test_manifest_merges_grid_when_extending_an_existing_scenario_block():
    """Regression test (Fase K2): found while designing F03's
    purification-density supplementary campaign - extending an existing
    scenario's grid with a few new values (e.g. denser thresholds) in a
    second call must UNION into the block's swept_factors/expected_trials,
    not overwrite them down to just the new call's own (smaller) grid."""
    with tempfile.TemporaryDirectory() as tmp_path:
        spec = three_node_spec()
        intent = simple_intent(intent_id="prog-density", source="a", destination="b", min_fidelity=0.6, requested_pairs=10)
        run_programmatic_campaign(
            campaign_name="TEST_PROG_DENSITY", scenario_name="three_node", base_topology=spec, base_intents=[intent],
            parameter_grid={"min_fidelity": [0.65, 0.70]}, seeds=[0, 1], output_directory=tmp_path,
        )
        run_programmatic_campaign(
            campaign_name="TEST_PROG_DENSITY", scenario_name="three_node", base_topology=spec, base_intents=[intent],
            parameter_grid={"min_fidelity": [0.72, 0.75]}, seeds=[0, 1], output_directory=tmp_path,
        )

        manifest = read_manifest(manifest_path(tmp_path, "TEST_PROG_DENSITY"))
        block = manifest["blocks"][0]
        assert block["swept_factors"]["min_fidelity"] == [0.65, 0.7, 0.72, 0.75]
        assert block["expected_trials"] == 4 * 2  # 4 fidelities x 2 seeds, not just the second call's 2x2=4
        assert block["completed_trials"] == 8
        assert manifest["expected_trials"] == 8
        assert manifest["completed_trials"] == 8
