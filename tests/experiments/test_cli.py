"""Tests for `ibqn.experiments.cli` (Fase H3.3, section 18) - the CLI
functions are called directly (`cli.main([...])`), not via subprocess, so
these tests run in-process and stay fast; `monkeypatch.chdir` controls
where `output_directory` (a path relative to the current working
directory) actually writes.
"""
import pytest

from ibqn.experiments import cli

_SCENARIO_YAML = """
scenario:
  name: tiny_two_node
  simulation:
    duration_s: 0.03
    seed: 0
  nodes:
    - id: a
      memories: 5
    - id: b
      memories: 5
  quantum_links:
    - source: a
      destination: b
      distance_m: 1000
      attenuation_db_per_m: 0.0001
  classical_delay_s: 0.0001
  intents:
    - file: intent.yaml
"""

_INTENT_YAML = """
intent:
  id: intent-001
  endpoints:
    source: a
    destination: b
  requirements:
    min_fidelity: 0.5
    min_throughput: 1
    max_latency: 1.0
    requested_pairs: 5
    start_time: 0.005
    duration: 0.02
  validation:
    metrics: [delivered_pairs]
    success_conditions:
      delivered_pairs: ">= 1"
"""

_CAMPAIGN_YAML = """
campaign:
  name: CLI-test
  scenario_file: scenario.yaml
  intents: [intent.yaml]
  seeds: [0, 1]
  output_directory: results
"""


@pytest.fixture
def campaign_dir(tmp_path, monkeypatch):
    (tmp_path / "scenario.yaml").write_text(_SCENARIO_YAML, encoding="utf-8")
    (tmp_path / "intent.yaml").write_text(_INTENT_YAML, encoding="utf-8")
    (tmp_path / "campaign.yaml").write_text(_CAMPAIGN_YAML, encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # output_directory="results" resolves relative to cwd
    return tmp_path


@pytest.mark.unit
def test_validate_reports_success(campaign_dir, capsys):
    rc = cli.main(["validate", "--campaign", "campaign.yaml"])
    assert rc == 0
    assert "is valid" in capsys.readouterr().out


@pytest.mark.unit
def test_validate_reports_failure_for_bad_campaign(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "bad_campaign.yaml").write_text("campaign:\n  name: ''\n  scenario_file: s.yaml\n  intents: []\n  seeds: []\n", encoding="utf-8")
    rc = cli.main(["validate", "--campaign", "bad_campaign.yaml"])
    assert rc == 1
    assert "error:" in capsys.readouterr().err


@pytest.mark.unit
def test_plan_reports_expected_trial_count_without_running(campaign_dir, capsys):
    rc = cli.main(["plan", "--campaign", "campaign.yaml"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2 expected trial(s)" in out
    assert not (campaign_dir / "results").exists()  # plan never executes anything


@pytest.mark.unit
def test_run_then_status_then_aggregate(campaign_dir, capsys):
    rc_run = cli.main(["run", "--campaign", "campaign.yaml"])
    assert rc_run == 0
    run_out = capsys.readouterr().out
    assert "completed: 2" in run_out

    rc_status = cli.main(["status", "--campaign", "campaign.yaml"])
    assert rc_status == 0
    status_out = capsys.readouterr().out
    assert "completed: 2" in status_out
    assert "remaining: 0" in status_out

    rc_aggregate = cli.main(["aggregate", "--campaign", "campaign.yaml", "--group-by", "routing_strategy"])
    assert rc_aggregate == 0
    aggregate_out = capsys.readouterr().out
    assert "Wrote" in aggregate_out
    assert (campaign_dir / "results" / "processed" / "CLI-test" / "aggregated.csv").exists()


@pytest.mark.unit
def test_resume_after_run_skips_everything(campaign_dir, capsys):
    cli.main(["run", "--campaign", "campaign.yaml"])
    capsys.readouterr()

    rc = cli.main(["resume", "--campaign", "campaign.yaml"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "completed: 0" in out
    assert "skipped:   2" in out


@pytest.mark.unit
def test_aggregate_without_any_trials_reports_error(campaign_dir, capsys):
    rc = cli.main(["aggregate", "--campaign", "campaign.yaml"])
    assert rc == 1
    assert "run it first" in capsys.readouterr().err


@pytest.mark.unit
def test_main_reports_unknown_command_argument_error():
    with pytest.raises(SystemExit):
        cli.main(["not-a-real-command", "--campaign", "campaign.yaml"])
