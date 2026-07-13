"""Tests for `ibqn.intent.models` and `ibqn.intent.parser`: construction,
defaults, and round-trip (de)serialization of the intent object model.
"""
import pytest
from pydantic import ValidationError

from ibqn.intent.models import (
    EntanglementIntent,
    IntentEndpoints,
    IntentPolicy,
    IntentRequirements,
    IntentValidation,
    SuccessCondition,
)
from ibqn.intent.parser import parse_intent_dict, parse_intent_yaml

EXAMPLE_INTENT_YAML = """
intent:
  id: intent-001
  service: entanglement_distribution
  endpoints:
    source: node_a
    destination: node_b
  requirements:
    min_fidelity: 0.90
    min_throughput: 10
    max_latency: 0.5
    requested_pairs: 100
    start_time: 0
    duration: 10
  policy:
    priority: normal
    allow_rerouting: true
    allow_purification: true
    allow_multiple_paths: false
  validation:
    metrics:
      - delivered_pairs
      - average_fidelity
      - throughput
      - completion_time
    success_conditions:
      delivered_pairs: ">= 100"
      average_fidelity: ">= 0.90"
      throughput: ">= 10"
"""


def build_minimal_intent(**overrides) -> EntanglementIntent:
    defaults = dict(
        id="intent-001",
        endpoints=IntentEndpoints(source="node_a", destination="node_b"),
        requirements=IntentRequirements(
            min_fidelity=0.9, min_throughput=10, max_latency=0.5,
            requested_pairs=100, start_time=0, duration=10,
        ),
        validation=IntentValidation(
            metrics=["delivered_pairs", "average_fidelity"],
            success_conditions=[
                SuccessCondition(metric="delivered_pairs", operator=">=", expected=100),
                SuccessCondition(metric="average_fidelity", operator=">=", expected=0.9),
            ],
        ),
    )
    defaults.update(overrides)
    return EntanglementIntent(**defaults)


@pytest.mark.unit
def test_minimal_intent_construction_uses_default_policy():
    intent = build_minimal_intent()

    assert intent.service == "entanglement_distribution"
    assert intent.policy == IntentPolicy()  # priority=normal, allow_rerouting=True, ...
    assert intent.requirements.min_fidelity == 0.9


@pytest.mark.unit
def test_parse_intent_dict_from_yaml_example_matches_prompt_schema():
    intent = parse_intent_yaml(EXAMPLE_INTENT_YAML)

    assert intent.id == "intent-001"
    assert intent.endpoints.source == "node_a"
    assert intent.endpoints.destination == "node_b"
    assert intent.requirements.min_fidelity == pytest.approx(0.90)
    assert intent.requirements.reserved_memory_slots == 100
    assert intent.policy.allow_multiple_paths is False

    conditions_by_metric = {c.metric: c for c in intent.validation.success_conditions}
    assert conditions_by_metric["delivered_pairs"] == SuccessCondition(
        metric="delivered_pairs", operator=">=", expected=100
    )
    assert conditions_by_metric["average_fidelity"].expected == pytest.approx(0.90)


@pytest.mark.unit
def test_parse_intent_dict_accepts_bare_mapping_without_intent_wrapper():
    intent = parse_intent_dict(
        {
            "id": "intent-002",
            "endpoints": {"source": "a", "destination": "b"},
            "requirements": {
                "min_fidelity": 0.8, "min_throughput": 5, "max_latency": 1.0,
                "requested_pairs": 10, "start_time": 0, "duration": 5,
            },
            "validation": {
                "metrics": ["delivered_pairs"],
                "success_conditions": {"delivered_pairs": ">= 10"},
            },
        }
    )
    assert intent.id == "intent-002"
    assert intent.validation.success_conditions[0].expected == 10


@pytest.mark.unit
def test_success_condition_parse_supports_all_operators():
    for op in (">=", "<=", ">", "<", "==", "!="):
        condition = SuccessCondition.parse("some_metric", f"{op} 42")
        assert condition.operator == op
        assert condition.expected == 42.0


@pytest.mark.unit
def test_models_are_frozen():
    endpoints = IntentEndpoints(source="a", destination="b")
    with pytest.raises(ValidationError):
        endpoints.source = "c"


@pytest.mark.unit
def test_intent_round_trips_through_dict_export():
    intent = build_minimal_intent()
    exported = intent.model_dump(mode="json")
    reloaded = EntanglementIntent.model_validate(exported)

    assert reloaded == intent
