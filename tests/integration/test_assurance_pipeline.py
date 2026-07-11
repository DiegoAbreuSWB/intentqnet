"""Integration tests for the full assurance pipeline
(telemetry -> evaluator -> violations) driven by `experiments.runner.run_scenario`
against real SeQUeNCe simulations - covering the SATISFIED, VIOLATED, and
REJECTED cases (RECONCILED is covered by tests/integration/test_reconciliation.py).
"""
import pytest
from sequence.utils import metrics
from sequence.utils.metrics.event_types import EventTypes

from ibqn.assurance.violations import ViolationCategory, classify_violations
from ibqn.execution.sequence_executor import SequenceExecutor
from ibqn.experiments.runner import run_scenario
from ibqn.experiments.scenarios import Scenario
from ibqn.intent.models import (
    EntanglementIntent, IntentEndpoints, IntentRequirements, IntentStatus, IntentValidation, SuccessCondition,
)
from ibqn.intent.repository import IntentRepository
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec
from ibqn.planning.planner import IntentPlanner

RAW_FIDELITY = 0.85
DEGRADATION = 0.95
SWAP_ONLY_FIDELITY = RAW_FIDELITY * RAW_FIDELITY * DEGRADATION


def linear_three_node_spec(stop_time_s=0.1) -> NetworkTopologySpec:
    return NetworkTopologySpec(
        nodes=[
            NodeSpec(id="r1", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="r2", memories=20, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="r3", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
        ],
        quantum_links=[
            QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="r2", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
        ],
        classical_delay_s=1e-4,
        stop_time_s=stop_time_s,
    )


def build_intent(min_fidelity, requested_pairs=10, start_time=0.02, duration=0.05) -> EntanglementIntent:
    return EntanglementIntent(
        id="intent-001",
        endpoints=IntentEndpoints(source="r1", destination="r3"),
        requirements=IntentRequirements(
            min_fidelity=min_fidelity, min_throughput=1, max_latency=1.0,
            requested_pairs=requested_pairs, start_time=start_time, duration=duration,
        ),
        validation=IntentValidation(
            metrics=["delivered_pairs", "average_fidelity"],
            success_conditions=[
                SuccessCondition(metric="delivered_pairs", operator=">=", expected=requested_pairs),
                SuccessCondition(metric="average_fidelity", operator=">=", expected=min_fidelity),
            ],
        ),
    )


class _FakeScenarioSpec:
    def __init__(self, seed):
        self.name = "assurance-pipeline-test"
        self.simulation = type("Sim", (), {"seed": seed})()


class _FakeScenario:
    """Bypasses `config.schemas.ScenarioSpec`/YAML loading so these tests can
    drive `run_scenario` directly from a `NetworkTopologySpec` built in code."""

    def __init__(self, topology_spec: NetworkTopologySpec, intents: list[EntanglementIntent], seed: int = 0):
        self._topology_spec = topology_spec
        self.intents = intents
        self.spec = _FakeScenarioSpec(seed)

    def topology_spec(self) -> NetworkTopologySpec:
        return self._topology_spec


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.configure()
    metrics.reset_metrics()
    yield


@pytest.mark.unit
def test_satisfied_case():
    scenario = _FakeScenario(linear_three_node_spec(), [build_intent(min_fidelity=0.65)])

    result = run_scenario(scenario, seed=0)

    intent_result = result.get("intent-001")
    assert intent_result.final_status == IntentStatus.SATISFIED
    assert intent_result.satisfied is True
    assert intent_result.evaluation is not None
    assert all(r.passed for r in intent_result.evaluation.condition_results)
    assert classify_violations(intent_result.evaluation) == []


@pytest.mark.unit
def test_rejected_case():
    """min_fidelity above what even purification can reach analytically ->
    the planner rejects the intent before it ever touches SeQUeNCe."""
    scenario = _FakeScenario(linear_three_node_spec(), [build_intent(min_fidelity=0.999)])

    result = run_scenario(scenario, seed=0)

    intent_result = result.get("intent-001")
    assert intent_result.final_status == IntentStatus.REJECTED
    assert intent_result.satisfied is False
    assert intent_result.evaluation is None  # no delivery evidence exists to judge
    assert intent_result.plan.feasible is False


@pytest.mark.unit
def test_violated_case():
    """High link attenuation slows entanglement generation drastically
    without lowering fidelity (attenuation only affects photon-loss
    probability, not `raw_fidelity`/`swapping_degradation` - see
    docs/sequence_code_analysis.md, section 4.1). The plan is therefore
    feasible at planning time (fidelity/memory are both fine), but the real
    run cannot deliver `requested_pairs` within the short window - a
    genuine, observed violation the v1 planner cannot predict (no
    throughput estimate, see docs/limitations.md), as opposed to
    `test_rejected_case`'s planning-time rejection."""
    spec = NetworkTopologySpec(
        nodes=[
            NodeSpec(id="r1", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="r2", memories=20, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="r3", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
        ],
        quantum_links=[
            QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=0.02),
            QuantumLinkSpec(source="r2", destination="r3", distance_m=1000, attenuation_db_per_m=0.02),
        ],
        classical_delay_s=1e-4,
        stop_time_s=0.2,
    )
    scenario = _FakeScenario(
        spec, [build_intent(min_fidelity=0.6, requested_pairs=10, start_time=0.02, duration=0.1)]
    )

    result = run_scenario(scenario, seed=0)

    intent_result = result.get("intent-001")
    assert intent_result.plan.feasible is True  # fidelity/memory both fine at planning time
    assert intent_result.final_status == IntentStatus.VIOLATED
    assert intent_result.satisfied is False
    assert intent_result.evaluation is not None
    violations = classify_violations(intent_result.evaluation)
    assert len(violations) >= 1
    assert any(v.category == ViolationCategory.DELIVERED_PAIRS for v in violations)


@pytest.mark.unit
def test_purified_pairs_are_counted_as_delivered_and_satisfy_the_intent():
    """Regression test for the critical bug documented in
    docs/assurance_design.md, section 2: `RequestApp.get_memory` ignores
    the `"PURIFIED"` state entirely, so before the fix in
    `IntentRequestApp._count_purified_delivery`, this scenario delivered 0
    pairs despite dozens of successful purifications."""
    spec = NetworkTopologySpec(
        nodes=[
            NodeSpec(id="r1", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="r2", memories=20, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="r3", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
        ],
        quantum_links=[
            QuantumLinkSpec(source="r1", destination="r2", distance_m=1000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="r2", destination="r3", distance_m=1000, attenuation_db_per_m=1e-5),
        ],
        classical_delay_s=1e-4,
        stop_time_s=0.3,
    )
    # target above SWAP_ONLY_FIDELITY (~0.686) forces purification
    scenario = _FakeScenario(spec, [build_intent(min_fidelity=0.72, requested_pairs=10, start_time=0.05, duration=0.2)])

    result = run_scenario(scenario, seed=0)

    intent_result = result.get("intent-001")
    assert intent_result.final_status == IntentStatus.SATISFIED
    assert intent_result.evaluation is not None
    delivered_condition = next(r for r in intent_result.evaluation.condition_results if r.metric == "delivered_pairs")
    assert delivered_condition.observed > 0
    fidelity_condition = next(r for r in intent_result.evaluation.condition_results if r.metric == "average_fidelity")
    assert fidelity_condition.observed >= 0.72
    assert fidelity_condition.observed > SWAP_ONLY_FIDELITY  # genuinely improved by purification


@pytest.mark.unit
def test_multi_intent_metric_isolation_end_to_end():
    """Two intents sharing an interior swap node ('center'), each evaluated
    using only its own intent_id-tagged DELIVERY evidence (see
    docs/assurance_design.md, section 3)."""
    spec = NetworkTopologySpec(
        nodes=[
            NodeSpec(id="center", memories=80, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="leaf1", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="leaf2", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="leaf3", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
            NodeSpec(id="leaf4", memories=10, raw_fidelity=RAW_FIDELITY, swapping_degradation=DEGRADATION),
        ],
        quantum_links=[
            QuantumLinkSpec(source="center", destination="leaf1", distance_m=1000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="center", destination="leaf2", distance_m=1000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="center", destination="leaf3", distance_m=1000, attenuation_db_per_m=1e-5),
            QuantumLinkSpec(source="center", destination="leaf4", distance_m=1000, attenuation_db_per_m=1e-5),
        ],
        classical_delay_s=1e-4,
        stop_time_s=0.1,
    )
    intent_a = build_intent(min_fidelity=0.6, requested_pairs=5)
    intent_a = intent_a.model_copy(update={"id": "intent-A", "endpoints": IntentEndpoints(source="leaf1", destination="leaf2")})
    intent_b = build_intent(min_fidelity=0.6, requested_pairs=5)
    intent_b = intent_b.model_copy(update={"id": "intent-B", "endpoints": IntentEndpoints(source="leaf3", destination="leaf4")})

    scenario = _FakeScenario(spec, [intent_a, intent_b])

    result = run_scenario(scenario, seed=0)

    result_a = result.get("intent-A")
    result_b = result.get("intent-B")
    assert result_a.final_status == IntentStatus.SATISFIED
    assert result_b.final_status == IntentStatus.SATISFIED

    delivery_a = [r for r in metrics.storage.get_all() if r["event_type"] is EventTypes.DELIVERY and r["intent_id"] == "intent-A"]
    delivery_b = [r for r in metrics.storage.get_all() if r["event_type"] is EventTypes.DELIVERY and r["intent_id"] == "intent-B"]
    assert all(r["owner_name"] == "leaf1" for r in delivery_a)
    assert all(r["owner_name"] == "leaf3" for r in delivery_b)
    # neither intent's evaluation is contaminated by the other's delivery count
    assert result_a.evaluation.condition_results[0].observed == len(delivery_a)
    assert result_b.evaluation.condition_results[0].observed == len(delivery_b)


@pytest.mark.unit
def test_conflicting_node_usage_raises_instead_of_misrouting_callbacks():
    """Regression test for docs/assurance_design.md, section 4: two intents
    that would share a node as source/destination must fail loudly, not
    silently misattribute one intent's callbacks to another's intent_id."""
    spec = linear_three_node_spec()
    adapter = SequenceAdapter(spec, seed=0)
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    capabilities = NetworkCapabilities(spec)
    planner = IntentPlanner(capabilities)

    intent_a = build_intent(min_fidelity=0.6, requested_pairs=3)
    intent_b = build_intent(min_fidelity=0.6, requested_pairs=3).model_copy(
        update={"id": "intent-002", "endpoints": IntentEndpoints(source="r3", destination="r1")}
    )

    executor.deploy(intent_a, planner.plan(intent_a))
    with pytest.raises(ValueError, match="already hosts the app for intent"):
        executor.deploy(intent_b, planner.plan(intent_b))
