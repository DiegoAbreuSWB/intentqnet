"""Tests for the Fase J2 intent resource/delivery-goal split
(`ibqn.intent.models.IntentRequirements.reserved_memory_slots` vs.
`min_delivered_pairs`) - see docs/intent_resource_semantics.md.
"""
import pytest
from pydantic import ValidationError

from ibqn.intent.models import (
    EntanglementIntent,
    IntentEndpoints,
    IntentRequirements,
    IntentValidation,
    SuccessCondition,
)
from ibqn.intent.parser import parse_intent_dict


def _requirements(**overrides) -> dict:
    defaults = dict(min_fidelity=0.9, min_throughput=1.0, max_latency=1.0)
    defaults.update(overrides)
    return defaults


@pytest.mark.unit
def test_new_style_intent_declares_slots_and_delivery_goal_independently():
    requirements = IntentRequirements(
        **_requirements(reserved_memory_slots=10, min_delivered_pairs=25, start_time_s=0.0, duration_s=1.0)
    )
    assert requirements.reserved_memory_slots == 10
    assert requirements.min_delivered_pairs == 25


@pytest.mark.unit
def test_legacy_style_intent_migrates_requested_pairs_to_reserved_memory_slots():
    requirements = IntentRequirements(
        **_requirements(requested_pairs=10, start_time=0.0, duration=1.0)
    )
    assert requirements.reserved_memory_slots == 10
    assert requirements.min_delivered_pairs is None  # never silently inferred from requested_pairs


@pytest.mark.unit
def test_legacy_and_new_style_construction_are_equivalent():
    legacy = IntentRequirements(**_requirements(requested_pairs=10, start_time=0.02, duration=0.1))
    new_style = IntentRequirements(
        **_requirements(reserved_memory_slots=10, start_time_s=0.02, duration_s=0.1)
    )
    assert legacy == new_style


@pytest.mark.unit
def test_absence_of_min_delivered_pairs_is_a_valid_explicit_state():
    requirements = IntentRequirements(**_requirements(reserved_memory_slots=10, start_time_s=0.0, duration_s=1.0))
    assert requirements.min_delivered_pairs is None


@pytest.mark.unit
def test_conflicting_legacy_and_new_field_values_are_rejected():
    with pytest.raises(ValidationError, match="requested_pairs.*reserved_memory_slots|reserved_memory_slots.*requested_pairs"):
        IntentRequirements(
            **_requirements(requested_pairs=10, reserved_memory_slots=5, start_time_s=0.0, duration_s=1.0)
        )


@pytest.mark.unit
def test_identical_legacy_and_new_field_values_do_not_conflict():
    requirements = IntentRequirements(
        **_requirements(requested_pairs=10, reserved_memory_slots=10, start_time_s=0.0, duration_s=1.0)
    )
    assert requirements.reserved_memory_slots == 10


@pytest.mark.unit
def test_reserved_memory_slots_smaller_than_delivery_goal_is_representable():
    """A slot pool smaller than the delivery goal is a legitimate scenario
    to explore (can memory reuse still reach the goal within the window?),
    not a schema error - see docs/intent_resource_semantics.md."""
    requirements = IntentRequirements(
        **_requirements(reserved_memory_slots=5, min_delivered_pairs=50, start_time_s=0.0, duration_s=1.0)
    )
    assert requirements.reserved_memory_slots == 5
    assert requirements.min_delivered_pairs == 50


@pytest.mark.unit
def test_reserved_memory_slots_and_min_delivered_pairs_vary_independently():
    base = IntentRequirements(
        **_requirements(reserved_memory_slots=10, min_delivered_pairs=10, start_time_s=0.0, duration_s=1.0)
    )
    more_slots_same_goal = base.model_copy(update={"reserved_memory_slots": 40})
    assert more_slots_same_goal.min_delivered_pairs == base.min_delivered_pairs
    assert more_slots_same_goal.reserved_memory_slots != base.reserved_memory_slots


@pytest.mark.unit
def test_resources_and_time_yaml_sibling_blocks_merge_into_requirements():
    intent = parse_intent_dict(
        {
            "id": "intent-new-style",
            "endpoints": {"source": "a", "destination": "b"},
            "requirements": {
                "min_fidelity": 0.9, "min_throughput": 1.0, "max_latency": 1.0, "min_delivered_pairs": 10,
            },
            "resources": {"reserved_memory_slots": 10},
            "time": {"start_time_s": 0.01, "duration_s": 0.1},
            "validation": {
                "metrics": ["delivered_pairs"],
                "success_conditions": {"delivered_pairs": ">= 10"},
            },
        }
    )
    assert intent.requirements.reserved_memory_slots == 10
    assert intent.requirements.min_delivered_pairs == 10
    assert intent.requirements.start_time_s == pytest.approx(0.01)
    assert intent.requirements.duration_s == pytest.approx(0.1)


@pytest.mark.unit
def test_resources_block_conflicting_with_requirements_block_is_rejected():
    with pytest.raises(ValueError, match="reserved_memory_slots"):
        parse_intent_dict(
            {
                "id": "intent-conflict",
                "endpoints": {"source": "a", "destination": "b"},
                "requirements": {
                    "min_fidelity": 0.9, "min_throughput": 1.0, "max_latency": 1.0,
                    "reserved_memory_slots": 10, "start_time_s": 0.0, "duration_s": 1.0,
                },
                "resources": {"reserved_memory_slots": 999},
                "validation": {
                    "metrics": ["delivered_pairs"],
                    "success_conditions": {"delivered_pairs": ">= 10"},
                },
            }
        )


@pytest.mark.unit
def test_entanglement_intent_round_trips_min_delivered_pairs():
    intent = EntanglementIntent(
        id="intent-001",
        endpoints=IntentEndpoints(source="a", destination="b"),
        requirements=IntentRequirements(
            **_requirements(reserved_memory_slots=10, min_delivered_pairs=15, start_time_s=0.0, duration_s=1.0)
        ),
        validation=IntentValidation(
            metrics=["delivered_pairs"],
            success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=15)],
        ),
    )
    dumped = intent.model_dump()
    assert dumped["requirements"]["min_delivered_pairs"] == 15
    assert dumped["requirements"]["reserved_memory_slots"] == 10
