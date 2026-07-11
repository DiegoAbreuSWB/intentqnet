"""Tests for `ibqn.assurance.telemetry.collect_intent_evidence` - built
against a fake metrics storage (not the real `sequence.utils.metrics`
singleton), so these stay fast, pure unit tests. The real, end-to-end path
(genuine SeQUeNCe DELIVERY events, source-node metrics) is covered by
tests/integration/test_assurance_pipeline.py.
"""
import pytest
from sequence.utils.metrics.event_types import EventTypes

from ibqn.assurance.telemetry import collect_intent_evidence
from ibqn.intent.models import (
    EntanglementIntent, IntentEndpoints, IntentRequirements, IntentValidation, SuccessCondition,
)


class FakeStorage:
    def __init__(self, records):
        self._records = records

    def get_all(self):
        return list(self._records)


def build_intent(intent_id="intent-001") -> EntanglementIntent:
    return EntanglementIntent(
        id=intent_id,
        endpoints=IntentEndpoints(source="a", destination="b"),
        requirements=IntentRequirements(
            min_fidelity=0.8, min_throughput=1, max_latency=1, requested_pairs=3, start_time=0.0, duration=10.0,
        ),
        validation=IntentValidation(
            metrics=["delivered_pairs"],
            success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=3)],
        ),
    )


def delivery_record(intent_id, pair_number, fidelity, sim_time_ps, owner="a"):
    return {
        "event_type": EventTypes.DELIVERY,
        "owner_name": owner,
        "sim_time": sim_time_ps,
        "intent_id": intent_id,
        "fidelity": fidelity,
        "pair_number": pair_number,
    }


@pytest.mark.unit
def test_collect_intent_evidence_filters_by_intent_id():
    storage = FakeStorage(
        [
            delivery_record("intent-001", 1, 0.9, 1_000_000_000_000),
            delivery_record("intent-002", 1, 0.7, 1_000_000_000_000),  # different intent, must be excluded
            delivery_record("intent-001", 2, 0.95, 2_000_000_000_000),
        ]
    )

    evidence = collect_intent_evidence(build_intent("intent-001"), storage=storage)

    assert len(evidence.delivered_pairs) == 2
    assert {p.fidelity for p in evidence.delivered_pairs} == {0.9, 0.95}


@pytest.mark.unit
def test_collect_intent_evidence_ignores_non_delivery_events():
    storage = FakeStorage(
        [
            {"event_type": EventTypes.EG_SUCCESS, "owner_name": "a", "sim_time": 0, "fidelity": 0.9},
            delivery_record("intent-001", 1, 0.9, 1_000_000_000_000),
        ]
    )

    evidence = collect_intent_evidence(build_intent("intent-001"), storage=storage)

    assert len(evidence.delivered_pairs) == 1


@pytest.mark.unit
def test_collect_intent_evidence_converts_sim_time_to_seconds():
    storage = FakeStorage([delivery_record("intent-001", 1, 0.9, 1_500_000_000_000)])  # 1.5e12 ps = 1.5 s

    evidence = collect_intent_evidence(build_intent("intent-001"), storage=storage)

    assert evidence.delivered_pairs[0].sim_time_s == pytest.approx(1.5)


@pytest.mark.unit
def test_collect_intent_evidence_sorts_by_pair_number():
    storage = FakeStorage(
        [
            delivery_record("intent-001", 3, 0.9, 3_000_000_000_000),
            delivery_record("intent-001", 1, 0.8, 1_000_000_000_000),
            delivery_record("intent-001", 2, 0.85, 2_000_000_000_000),
        ]
    )

    evidence = collect_intent_evidence(build_intent("intent-001"), storage=storage)

    assert [p.pair_number for p in evidence.delivered_pairs] == [1, 2, 3]


@pytest.mark.unit
def test_collect_intent_evidence_deduplicates_repeated_pair_numbers():
    """Defensive dedup (see docs/assurance_design.md, section 6): even if a
    pair_number appeared twice (should not happen given how
    IntentRequestApp assigns it, but defended against anyway), only the
    first occurrence is kept."""
    storage = FakeStorage(
        [
            delivery_record("intent-001", 1, 0.8, 1_000_000_000_000),
            delivery_record("intent-001", 1, 0.99, 1_000_000_000_000),  # duplicate pair_number=1
        ]
    )

    evidence = collect_intent_evidence(build_intent("intent-001"), storage=storage)

    assert len(evidence.delivered_pairs) == 1
    assert evidence.delivered_pairs[0].fidelity == 0.8


@pytest.mark.unit
def test_collect_intent_evidence_empty_when_no_matching_records():
    storage = FakeStorage([])

    evidence = collect_intent_evidence(build_intent("intent-001"), storage=storage)

    assert evidence.delivered_pairs == []
    assert evidence.intent_id == "intent-001"
