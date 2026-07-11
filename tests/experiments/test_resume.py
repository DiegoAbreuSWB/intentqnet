"""End-to-end tests for `CampaignRunner`: resume/idempotency and failure
handling (Fase H3.2, sections 6/13/35).
"""
import pytest

import ibqn.experiments.runner as runner_module
from ibqn.experiments.campaigns import load_campaign_file
from ibqn.experiments.manifests import manifest_path, read_manifest
from ibqn.experiments.persistence import errors_jsonl_path, read_errors, read_trials_dataframe, trials_csv_path
from ibqn.experiments.runner import CampaignRunner

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


def _write_tiny_campaign(tmp_path, *, seeds, continue_on_error=True, resume=True, name="C-test"):
    (tmp_path / "scenario.yaml").write_text(_SCENARIO_YAML, encoding="utf-8")
    (tmp_path / "intent.yaml").write_text(_INTENT_YAML, encoding="utf-8")
    seeds_yaml = ", ".join(str(s) for s in seeds)
    campaign_yaml = f"""
campaign:
  name: {name}
  scenario_file: scenario.yaml
  intents: [intent.yaml]
  seeds: [{seeds_yaml}]
  output_directory: {tmp_path.as_posix()}/results
  execution:
    continue_on_error: {str(continue_on_error).lower()}
    resume: {str(resume).lower()}
"""
    campaign_path = tmp_path / "campaign.yaml"
    campaign_path.write_text(campaign_yaml, encoding="utf-8")
    return campaign_path


@pytest.mark.unit
def test_run_executes_every_expected_trial(tmp_path):
    campaign_path = _write_tiny_campaign(tmp_path, seeds=[0, 1])
    spec = load_campaign_file(campaign_path)

    summary = CampaignRunner(spec, campaign_file=campaign_path).run()

    assert summary.expected_trials == 2
    assert summary.completed_trials == 2
    assert summary.skipped_trials == 0
    assert summary.failed_trials == 0

    df = read_trials_dataframe(trials_csv_path(spec.output_directory, spec.name))
    assert len(df) == 2
    assert set(df["seed"]) == {0, 1}


@pytest.mark.unit
def test_resume_skips_already_completed_trials(tmp_path):
    campaign_path = _write_tiny_campaign(tmp_path, seeds=[0, 1])
    spec = load_campaign_file(campaign_path)

    first_summary = CampaignRunner(spec, campaign_file=campaign_path).run()
    assert first_summary.completed_trials == 2

    second_summary = CampaignRunner(spec, campaign_file=campaign_path).run()
    assert second_summary.completed_trials == 0
    assert second_summary.skipped_trials == 2

    df = read_trials_dataframe(trials_csv_path(spec.output_directory, spec.name))
    assert len(df) == 2  # no duplicate rows from the second run


@pytest.mark.unit
def test_resume_runs_only_the_missing_trials_after_adding_a_seed(tmp_path):
    campaign_path = _write_tiny_campaign(tmp_path, seeds=[0])
    spec = load_campaign_file(campaign_path)
    CampaignRunner(spec, campaign_file=campaign_path).run()

    campaign_path_2 = _write_tiny_campaign(tmp_path, seeds=[0, 1])
    spec_2 = load_campaign_file(campaign_path_2)
    summary = CampaignRunner(spec_2, campaign_file=campaign_path_2).run()

    assert summary.completed_trials == 1  # only the new seed=1 trial
    assert summary.skipped_trials == 1  # seed=0 already existed

    df = read_trials_dataframe(trials_csv_path(spec.output_directory, spec.name))
    assert len(df) == 2
    assert set(df["seed"]) == {0, 1}


@pytest.mark.unit
def test_manifest_reflects_progress_after_a_run(tmp_path):
    campaign_path = _write_tiny_campaign(tmp_path, seeds=[0, 1])
    spec = load_campaign_file(campaign_path)
    CampaignRunner(spec, campaign_file=campaign_path).run()

    manifest = read_manifest(manifest_path(spec.output_directory, spec.name))
    assert manifest["expected_trials"] == 2
    assert manifest["completed_trials"] == 2
    assert manifest["failed_trials"] == 0


@pytest.mark.unit
def test_run_without_resume_raises_when_results_already_exist(tmp_path):
    campaign_path = _write_tiny_campaign(tmp_path, seeds=[0])
    spec = load_campaign_file(campaign_path)
    CampaignRunner(spec, campaign_file=campaign_path).run()

    fresh_campaign_path = _write_tiny_campaign(tmp_path, seeds=[0], resume=False)
    fresh_spec = load_campaign_file(fresh_campaign_path)
    with pytest.raises(RuntimeError, match="resume"):
        CampaignRunner(fresh_spec, campaign_file=fresh_campaign_path).run()


@pytest.mark.unit
def test_continue_on_error_records_failure_and_keeps_running(tmp_path, monkeypatch):
    campaign_path = _write_tiny_campaign(tmp_path, seeds=[0, 1], continue_on_error=True)
    spec = load_campaign_file(campaign_path)

    original_execute_trial = runner_module.execute_trial
    call_count = {"n": 0}

    def flaky_execute_trial(identity, params, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("synthetic failure for testing")
        return original_execute_trial(identity, params, **kwargs)

    monkeypatch.setattr(runner_module, "execute_trial", flaky_execute_trial)

    summary = CampaignRunner(spec, campaign_file=campaign_path).run()

    assert summary.failed_trials == 1
    assert summary.completed_trials == 1
    assert call_count["n"] == 2  # both trials were attempted despite the first failing

    errors = read_errors(errors_jsonl_path(spec.output_directory, spec.name))
    assert len(errors) == 1
    assert errors[0]["error_type"] == "RuntimeError"
    assert "synthetic failure" in errors[0]["error_message"]

    df = read_trials_dataframe(trials_csv_path(spec.output_directory, spec.name))
    assert len(df) == 1  # only the successful trial was persisted


@pytest.mark.unit
def test_abort_on_error_stops_after_the_first_failure(tmp_path, monkeypatch):
    campaign_path = _write_tiny_campaign(tmp_path, seeds=[0, 1], continue_on_error=False)
    spec = load_campaign_file(campaign_path)

    call_count = {"n": 0}

    def always_fails(identity, params, **kwargs):
        call_count["n"] += 1
        raise RuntimeError("synthetic failure for testing")

    monkeypatch.setattr(runner_module, "execute_trial", always_fails)

    summary = CampaignRunner(spec, campaign_file=campaign_path).run()

    assert summary.failed_trials == 1
    assert summary.completed_trials == 0
    assert call_count["n"] == 1  # the second trial was never attempted
