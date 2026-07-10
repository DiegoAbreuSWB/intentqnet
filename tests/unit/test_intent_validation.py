"""Tests that invalid intents are rejected at construction time by pydantic
validation, before ever reaching the lifecycle/planner (see
docs/intent_model.md).
"""
import pytest
from pydantic import ValidationError

from ibqn.intent.models import (
    IntentEndpoints,
    IntentRequirements,
    IntentValidation,
    SuccessCondition,
)
from ibqn.intent.parser import parse_intent_dict

VALID_REQUIREMENTS = dict(
    min_fidelity=0.9, min_throughput=10, max_latency=0.5,
    requested_pairs=100, start_time=0, duration=10,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "overrides",
    [
        {"min_fidelity": -0.1},
        {"min_fidelity": 1.1},
        {"min_throughput": 0},
        {"min_throughput": -5},
        {"max_latency": 0},
        {"requested_pairs": 0},
        {"requested_pairs": -1},
        {"start_time": -1},
        {"duration": 0},
    ],
)
def test_requirements_reject_out_of_range_values(overrides):
    params = {**VALID_REQUIREMENTS, **overrides}
    with pytest.raises(ValidationError):
        IntentRequirements(**params)


@pytest.mark.unit
def test_endpoints_reject_identical_source_and_destination():
    with pytest.raises(ValidationError, match="source and destination must differ"):
        IntentEndpoints(source="node_a", destination="node_a")


@pytest.mark.unit
def test_endpoints_reject_empty_node_names():
    with pytest.raises(ValidationError):
        IntentEndpoints(source="", destination="node_b")


@pytest.mark.unit
def test_policy_rejects_unknown_priority():
    from ibqn.intent.models import IntentPolicy

    with pytest.raises(ValidationError):
        IntentPolicy(priority="urgent")  # only low/normal/high are valid


@pytest.mark.unit
def test_success_condition_rejects_malformed_expression():
    with pytest.raises(ValueError, match="invalid success condition expression"):
        SuccessCondition.parse("delivered_pairs", "at least 100")


@pytest.mark.unit
def test_success_condition_rejects_unknown_operator():
    with pytest.raises(ValueError):
        SuccessCondition.parse("delivered_pairs", "~= 100")


@pytest.mark.unit
def test_validation_rejects_condition_for_undeclared_metric():
    with pytest.raises(ValidationError, match="not listed in 'metrics'"):
        IntentValidation(
            metrics=["delivered_pairs"],
            success_conditions=[
                SuccessCondition(metric="average_fidelity", operator=">=", expected=0.9),
            ],
        )


@pytest.mark.unit
def test_validation_rejects_empty_metrics_list():
    with pytest.raises(ValidationError):
        IntentValidation(metrics=[], success_conditions=[])


@pytest.mark.unit
def test_parse_intent_dict_reports_error_for_missing_required_field():
    incomplete = {
        "id": "intent-broken",
        "endpoints": {"source": "a", "destination": "b"},
        # requirements missing entirely
        "validation": {"metrics": ["delivered_pairs"], "success_conditions": {"delivered_pairs": ">= 1"}},
    }
    with pytest.raises(ValidationError, match="requirements"):
        parse_intent_dict(incomplete)


@pytest.mark.unit
def test_parse_intent_dict_reports_error_for_malformed_success_condition_string():
    broken = {
        "id": "intent-broken",
        "endpoints": {"source": "a", "destination": "b"},
        "requirements": VALID_REQUIREMENTS,
        "validation": {
            "metrics": ["delivered_pairs"],
            "success_conditions": {"delivered_pairs": "greater than 100"},
        },
    }
    with pytest.raises(ValueError, match="invalid success condition expression"):
        parse_intent_dict(broken)
