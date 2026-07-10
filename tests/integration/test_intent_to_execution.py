"""End-to-end integration test: one `EntanglementIntent` compiled by
`SequenceExecutor` into a real `NetworkManager.request(...)` call, executed
on a real 3-node SeQUeNCe topology, with results read back exclusively from
simulator state (`MemoryInfo`, `sequence.utils.metrics`) - never computed
independently of the simulation (see docs/sequence_code_analysis.md,
section 2 constraints).

`min_fidelity` is deliberately kept at/under the achievable single-swap
fidelity (`raw_fidelity**2 * swapping_degradation`, both defaults: 0.85 and
0.95) so this test exercises generation + swapping without also depending on
purification's probabilistic behavior (covered separately in
tests/sequence_basics/test_purification.py).
"""
import pytest

from sequence.utils import metrics
from sequence.utils.metrics.event_types import EventTypes

from ibqn.execution.sequence_executor import SequenceExecutor
from ibqn.intent.models import (
    EntanglementIntent,
    IntentEndpoints,
    IntentRequirements,
    IntentStatus,
    IntentValidation,
    SuccessCondition,
)
from ibqn.intent.repository import IntentRepository
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec

SINGLE_SWAP_FIDELITY = 0.85 * 0.85 * 0.95  # raw_fidelity**2 * default swapping_degradation


def build_linear_three_node_adapter(seed=0, stop_time_s=0.1):
    spec = NetworkTopologySpec(
        nodes=[
            NodeSpec(id="r1", memories=10),
            NodeSpec(id="r2", memories=20),
            NodeSpec(id="r3", memories=10),
        ],
        quantum_links=[
            QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="r2", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
        ],
        classical_delay_s=1e-4,
        stop_time_s=stop_time_s,
    )
    return SequenceAdapter(spec, seed=seed)


def build_intent(min_fidelity=0.65, requested_pairs=10, duration=0.02) -> EntanglementIntent:
    return EntanglementIntent(
        id="intent-001",
        endpoints=IntentEndpoints(source="r1", destination="r3"),
        requirements=IntentRequirements(
            min_fidelity=min_fidelity, min_throughput=1, max_latency=1.0,
            requested_pairs=requested_pairs, start_time=0.05, duration=duration,
        ),
        validation=IntentValidation(
            metrics=["delivered_pairs", "average_fidelity"],
            success_conditions=[
                SuccessCondition(metric="delivered_pairs", operator=">=", expected=requested_pairs),
                SuccessCondition(metric="average_fidelity", operator=">=", expected=min_fidelity),
            ],
        ),
    )


@pytest.fixture(autouse=True)
def _reset_metrics_between_tests():
    metrics.configure()
    metrics.reset_metrics()
    yield
    metrics._enabled = False
    metrics._enabled_events.clear()


@pytest.mark.unit
def test_achievable_intent_reaches_active_and_delivers_pairs():
    adapter = build_linear_three_node_adapter()
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)

    intent = build_intent(min_fidelity=0.65, requested_pairs=10)
    executor.submit(intent)
    executor.run()

    record = repository.get("intent-001")
    assert record.lifecycle.status == IntentStatus.ACTIVE
    assert [t.to_status for t in record.lifecycle.history] == [
        IntentStatus.RECEIVED, IntentStatus.VALIDATED, IntentStatus.PLANNING,
        IntentStatus.PLANNED, IntentStatus.DEPLOYING, IntentStatus.ACTIVE,
    ]

    app = executor.get_app("intent-001")
    assert app.memory_counter >= intent.requirements.requested_pairs


@pytest.mark.unit
def test_delivery_metrics_are_recorded_with_correct_fidelity():
    adapter = build_linear_three_node_adapter()
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)

    intent = build_intent(min_fidelity=0.65, requested_pairs=5)
    executor.submit(intent)
    executor.run()

    delivery_records = [
        r for r in metrics.storage.get_by_owner("r1") if r["event_type"] is EventTypes.DELIVERY
    ]
    assert len(delivery_records) >= intent.requirements.requested_pairs
    for record in delivery_records:
        assert record["intent_id"] == "intent-001"
        assert record["fidelity"] == pytest.approx(SINGLE_SWAP_FIDELITY)
    # pair_number must be a strictly increasing, gap-free sequence
    pair_numbers = [r["pair_number"] for r in delivery_records]
    assert pair_numbers == list(range(1, len(pair_numbers) + 1))


@pytest.mark.unit
def test_infeasible_reservation_moves_intent_to_failed():
    """Requesting more memories than the source router has forces a
    rejection at admission (see docs/sequence_code_analysis.md, section 4.5)
    - the intent must end in FAILED, not silently stay DEPLOYING forever."""
    adapter = build_linear_three_node_adapter()
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)

    intent = build_intent(min_fidelity=0.65, requested_pairs=10_000)  # r1 only has 10 memories
    executor.submit(intent)
    executor.run()

    record = repository.get("intent-001")
    assert record.lifecycle.status == IntentStatus.FAILED
    assert record.result is not None
    assert record.result.satisfied is False


@pytest.mark.unit
def test_collect_trial_metrics_reports_eg_and_es_activity():
    adapter = build_linear_three_node_adapter()
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)

    executor.submit(build_intent(min_fidelity=0.65, requested_pairs=10))
    executor.run()

    trial = metrics.collect_trial_metrics("r1")
    assert trial["eg_success"] > 0
    trial_r2 = metrics.collect_trial_metrics("r2")
    assert trial_r2["es_success"] > 0
    assert trial_r2["es_failures"] == 0  # swapping_success_prob defaults to 1
