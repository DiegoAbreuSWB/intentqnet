"""Tests for `ibqn.experiments.campaigns.CampaignSpec` (Fase H3.1)."""
import pytest
from pydantic import ValidationError

from ibqn.experiments.campaigns import CampaignSpec, load_campaign_file


def _base_kwargs(**overrides):
    kwargs = dict(
        name="test-campaign",
        scenario_file="scenario.yaml",
        intents=["intent.yaml"],
        seeds=[42, 1042],
    )
    kwargs.update(overrides)
    return kwargs


@pytest.mark.unit
def test_valid_campaign_spec_builds():
    spec = CampaignSpec(**_base_kwargs(
        strategies={"routing": ["shortest_hop_count", "least_loss"]},
        parameter_grid={"min_fidelity": [0.6, 0.7]},
    ))
    assert spec.name == "test-campaign"
    assert spec.effective_parameter_grid() == {
        "min_fidelity": [0.6, 0.7],
        "routing_strategy": ["shortest_hop_count", "least_loss"],
    }


@pytest.mark.unit
def test_rejects_empty_name():
    with pytest.raises(ValidationError, match="at least 1 character"):
        CampaignSpec(**_base_kwargs(name=""))


@pytest.mark.unit
def test_rejects_missing_seeds():
    with pytest.raises(ValidationError, match="at least 1 item"):
        CampaignSpec(**_base_kwargs(seeds=[]))


@pytest.mark.unit
def test_rejects_empty_parameter_grid_value():
    with pytest.raises(ValidationError, match="empty value list"):
        CampaignSpec(**_base_kwargs(parameter_grid={"min_fidelity": []}))


@pytest.mark.unit
def test_rejects_unknown_strategy_name():
    with pytest.raises(ValidationError, match="unknown routing strategy"):
        CampaignSpec(**_base_kwargs(strategies={"routing": ["not_a_real_strategy"]}))


@pytest.mark.unit
def test_rejects_unknown_strategy_category():
    with pytest.raises(ValidationError, match="unknown strategy category"):
        CampaignSpec(**_base_kwargs(strategies={"swapping": ["anything"]}))


@pytest.mark.unit
def test_rejects_unsupported_parameter():
    with pytest.raises(ValidationError, match="unsupported sweep parameter"):
        CampaignSpec(**_base_kwargs(parameter_grid={"not_a_real_param": [1]}))


@pytest.mark.unit
def test_rejects_invalid_parameter_value_type():
    with pytest.raises(ValidationError, match="expects float"):
        CampaignSpec(**_base_kwargs(parameter_grid={"min_fidelity": ["not-a-float"]}))


@pytest.mark.unit
def test_load_campaign_file_rejects_missing_scenario_file(tmp_path):
    campaign_path = tmp_path / "camp.yaml"
    campaign_path.write_text(
        "campaign:\n"
        "  name: test\n"
        "  scenario_file: missing_scenario.yaml\n"
        "  intents: [missing_intent.yaml]\n"
        "  seeds: [1]\n",
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="missing_scenario.yaml"):
        load_campaign_file(campaign_path)


@pytest.mark.unit
def test_load_campaign_file_rejects_missing_intent_file(tmp_path):
    (tmp_path / "scenario.yaml").write_text("scenario: {}\n", encoding="utf-8")
    campaign_path = tmp_path / "camp.yaml"
    campaign_path.write_text(
        "campaign:\n"
        "  name: test\n"
        "  scenario_file: scenario.yaml\n"
        "  intents: [missing_intent.yaml]\n"
        "  seeds: [1]\n",
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="missing_intent.yaml"):
        load_campaign_file(campaign_path)


@pytest.mark.unit
def test_default_execution_options():
    spec = CampaignSpec(**_base_kwargs())
    assert spec.execution.continue_on_error is True
    assert spec.execution.resume is True
