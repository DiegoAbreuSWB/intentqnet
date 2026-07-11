"""End-to-end scenario test: loads the real `scenarios/linear_three_nodes.yaml`
+ `scenarios/intents/intent_001.yaml` files shipped with this project and
runs them through `experiments.runner.run_scenario` - the same declarative
path a notebook or article-experiment script would use (see the project
brief, section 15 "Estrutura de cenários").
"""
from pathlib import Path

import pytest

from sequence.utils import metrics

from ibqn.experiments.runner import run_scenario
from ibqn.experiments.scenarios import Scenario
from ibqn.experiments.seeds import seeds_for_trials
from ibqn.intent.models import IntentStatus

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_PATH = PROJECT_ROOT / "scenarios" / "linear_three_nodes.yaml"


@pytest.mark.unit
def test_scenario_file_loads_and_resolves_intent_file_relative_to_itself():
    scenario = Scenario.load(SCENARIO_PATH)

    assert scenario.spec.name == "linear_three_nodes"
    assert [node.id for node in scenario.spec.nodes] == ["A", "R1", "B"]
    assert len(scenario.intents) == 1
    assert scenario.intents[0].id == "intent-001"
    assert scenario.intents[0].endpoints.source == "A"
    assert scenario.intents[0].endpoints.destination == "B"


@pytest.mark.unit
def test_run_scenario_delivers_the_requested_pairs():
    scenario = Scenario.load(SCENARIO_PATH)

    result = run_scenario(scenario)

    assert result.scenario_name == "linear_three_nodes"
    assert result.seed == 42
    intent_result = result.get("intent-001")
    assert intent_result.final_status == IntentStatus.SATISFIED
    assert intent_result.satisfied is True
    assert intent_result.evaluation is not None
    assert intent_result.plan.feasible is True
    assert intent_result.plan.route == ["A", "R1", "B"]
    assert intent_result.metrics["eg_success"] > 0

    # `IntentRunResult.metrics` is scoped to the intent's *source* router
    # (`collect_trial_metrics(intent.endpoints.source)`); swap events are
    # owned by the interior node instead, so they're checked directly here.
    interior_node = intent_result.plan.route[1]
    assert metrics.get_counter("es").successes(interior_node) > 0


@pytest.mark.probabilistic
def test_run_scenario_seed_override_reproduces_across_repeated_calls():
    """Same seed -> same eg_success count; different seeds (via
    `seeds_for_trials`) -> independent trials that all still reach SATISFIED."""
    scenario = Scenario.load(SCENARIO_PATH)
    seeds = seeds_for_trials(base_seed=7, n_trials=2)

    first_run = run_scenario(scenario, seed=seeds[0])
    repeat_run = run_scenario(scenario, seed=seeds[0])
    other_seed_run = run_scenario(scenario, seed=seeds[1])

    assert first_run.get("intent-001").metrics["eg_success"] == repeat_run.get("intent-001").metrics["eg_success"]
    for run in (first_run, repeat_run, other_seed_run):
        assert run.get("intent-001").final_status == IntentStatus.SATISFIED
        assert run.get("intent-001").satisfied is True
