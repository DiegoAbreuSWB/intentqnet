"""End-to-end tests of the physical-realism revision (docs/physical_model.md):
the IBQN pipeline (`SequenceExecutor.deploy` on a real `SequenceAdapter`)
under the default `bell_diagonal` formalism really runs single-heralded
generation -> Bell-diagonal swapping -> BBPSSW purification on Bell-diagonal
states, reports fidelities READ FROM THE QUANTUM STATE, decoheres idle
memories, and executes the plan's purification policy.

Every expectation is either read back from the simulator (states, events)
or computed with the exact SeQUeNCe formula ports in `ibqn.physics`, which
`tests/unit/test_physics.py` pins to the real protocol code.
"""
from __future__ import annotations

from collections import Counter

import pytest
from sequence.components.bsm import SingleAtomBSM, SingleHeraldedBSM
from sequence.constants import BELL_DIAGONAL_STATE_FORMALISM, KET_VECTOR_FORMALISM
from sequence.utils import metrics
from sequence.utils.metrics.event_types import EventTypes

from ibqn.execution.sequence_executor import IntentRequestApp, SequenceExecutor
from ibqn.intent.models import (
    EntanglementIntent,
    IntentEndpoints,
    IntentRequirements,
    IntentStatus,
    IntentValidation,
    SuccessCondition,
)
from ibqn.intent.repository import IntentRepository
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.sequence_adapter import SequenceAdapter, active_sequence_globals
from ibqn.network.sequence_patches import sequence_patches_applied
from ibqn.network.topology import NetworkTopologySpec, NodeSpec, QuantumLinkSpec
from ibqn.physics import bds_purification_step, bds_swap_fidelity
from ibqn.planning.models import ExecutionPlan
from ibqn.planning.planner import IntentPlanner
from ibqn.planning.purification import NeverPurify, PurifyOnce, PurifyUntilTarget

RAW = 0.85
SWAP_FIDELITY = bds_swap_fidelity(RAW, RAW, gate_fidelity=1.0, measurement_fidelity=1.0)  # 0.73 exactly
ONE_ROUND = bds_purification_step(
    SWAP_FIDELITY, SWAP_FIDELITY, own_gate_fidelity=1, own_measurement_fidelity=1,
    remote_gate_fidelity=1, remote_measurement_fidelity=1,
)[1]


def chain_spec(n_repeaters=1, *, coherence_time_s=1.0, formalism=BELL_DIAGONAL_STATE_FORMALISM, stop_time_s=0.2,
               **node_kwargs) -> NetworkTopologySpec:
    names = ["a"] + [f"r{i}" for i in range(1, n_repeaters + 1)] + ["b"]
    nodes = [
        NodeSpec(id=n, memories=10 if n in ("a", "b") else 20, raw_fidelity=RAW, coherence_time_s=coherence_time_s,
                 **node_kwargs)
        for n in names
    ]
    links = [
        QuantumLinkSpec(source=names[i], destination=names[i + 1], distance_m=1000, attenuation_db_per_m=1e-5)
        for i in range(len(names) - 1)
    ]
    return NetworkTopologySpec(nodes=nodes, quantum_links=links, classical_delay_s=1e-4, stop_time_s=stop_time_s,
                               formalism=formalism)


def build_intent(min_fidelity: float, *, duration_s=0.1, slots=10) -> EntanglementIntent:
    return EntanglementIntent(
        id="bds-intent", endpoints=IntentEndpoints(source="a", destination="b"),
        requirements=IntentRequirements(
            min_fidelity=min_fidelity, min_throughput=1, max_latency=1.0,
            reserved_memory_slots=slots, start_time_s=0.02, duration_s=duration_s,
        ),
        validation=IntentValidation(
            metrics=["delivered_pairs"],
            success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=1)],
        ),
    )


class StateProbeApp(IntentRequestApp):
    """Records, for every memory handed to the application, the scalar
    fidelity SeQUeNCe reports AND the fidelity of the Bell-diagonal state
    actually stored for it - so the test can show the two agree."""

    def __init__(self, node, intent_id, repository):
        super().__init__(node, intent_id, repository)
        self.observations: list[tuple[str, float, float]] = []

    def get_memory(self, info):
        if info.state in ("ENTANGLED", "PURIFIED") and info.remote_node is not None:
            state = self.node.timeline.quantum_manager.get(info.memory.qstate_key)
            self.observations.append((info.state, info.fidelity, float(state.state[0].real)))
        super().get_memory(info)


def run_chain(min_fidelity, *, mode="until_target", n_repeaters=1, coherence_time_s=1.0, seed=0, probe=False,
              formalism=BELL_DIAGONAL_STATE_FORMALISM, **node_kwargs):
    metrics.configure()
    metrics.reset_metrics()
    spec = chain_spec(n_repeaters, coherence_time_s=coherence_time_s, formalism=formalism, **node_kwargs)
    adapter = SequenceAdapter(spec, seed=seed)
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    if probe:
        # swap the app class for the probing subclass (same constructor contract)
        original = SequenceExecutor._start_reservation

        def _start(self, intent, purification_mode):
            source = adapter.get_router(intent.endpoints.source)
            destination = adapter.get_router(intent.endpoints.destination)
            source_app = StateProbeApp(source, intent.id, repository)
            destination_app = StateProbeApp(destination, intent.id, repository)
            self._source_apps[intent.id] = source_app
            self._destination_apps[intent.id] = destination_app
            start_ps = int(intent.requirements.start_time_s * 1e12)
            end_ps = int((intent.requirements.start_time_s + intent.requirements.duration_s) * 1e12)
            source_app.start_intent(intent.endpoints.destination, start_ps, end_ps,
                                    intent.requirements.reserved_memory_slots, intent.requirements.min_fidelity,
                                    purification_mode=purification_mode)

        executor._start_reservation = _start.__get__(executor, SequenceExecutor)
    intent = build_intent(min_fidelity)
    route = [n.id for n in spec.nodes]
    plan = ExecutionPlan(intent_id=intent.id, feasible=True, route=route, purification_mode=mode)
    executor.deploy(intent, plan)
    executor.run()
    deliveries = [r for r in metrics.storage.get_all() if r["event_type"] is EventTypes.DELIVERY]
    events = Counter(r["event_type"].name for r in metrics.storage.get_all())
    return adapter, executor, repository, deliveries, events


@pytest.mark.unit
def test_adapter_makes_the_bell_diagonal_formalism_effective_everywhere():
    """All four SeQUeNCe switches, the BSM hardware, the memory decoherence
    parameters and the gate/measurement fidelities must reflect the spec -
    `Timeline(formalism=...)` alone sets only the first switch."""
    spec = chain_spec(gate_fidelity=0.97, measurement_fidelity=0.98, cutoff_ratio=0.4)
    adapter = SequenceAdapter(spec, seed=0)

    switches = active_sequence_globals()
    assert switches["quantum_manager"] == BELL_DIAGONAL_STATE_FORMALISM
    assert switches["generation"] == switches["generation_bsm_side"] == "single_heralded"
    assert switches["swapping_a"] == switches["swapping_b"] == switches["purification"] == BELL_DIAGONAL_STATE_FORMALISM
    assert sequence_patches_applied()

    bsm_node = adapter.get_timeline().get_entity_by_name("BSM.a.r1")
    assert isinstance(bsm_node.components[f"{bsm_node.name}.BSM"], SingleHeraldedBSM)

    r1 = adapter.get_router("r1")
    assert r1.gate_fid == 0.97 and r1.meas_fid == 0.98
    assert r1.swapping_degradation is None  # BDS swap noise comes from gate/measurement fidelity, not this
    memory = r1.get_components_by_type("MemoryArray")[0][0]
    assert memory.raw_fidelity == RAW
    assert memory.coherence_time == 1.0
    assert memory.decoherence_rate == pytest.approx(1.0)  # set at construction from coherence_time
    assert memory.decoherence_errors == pytest.approx([1 / 3, 1 / 3, 1 / 3])
    assert memory.cutoff_ratio == 0.4


@pytest.mark.unit
def test_adapter_keeps_the_legacy_ket_vector_wiring_when_asked():
    spec = chain_spec(formalism=KET_VECTOR_FORMALISM, coherence_time_s=-1)
    adapter = SequenceAdapter(spec, seed=0)
    switches = active_sequence_globals()
    assert switches["quantum_manager"] == KET_VECTOR_FORMALISM
    assert switches["generation"] == "barret_kok"
    assert switches["swapping_a"] == switches["purification"] == KET_VECTOR_FORMALISM
    bsm_node = adapter.get_timeline().get_entity_by_name("BSM.a.r1")
    assert isinstance(bsm_node.components[f"{bsm_node.name}.BSM"], SingleAtomBSM)
    r1 = adapter.get_router("r1")
    assert r1.swapping_degradation == 0.95
    memory = r1.get_components_by_type("MemoryArray")[0][0]
    assert memory.coherence_time == -1 and memory.decoherence_rate == 0


@pytest.mark.unit
def test_delivered_fidelity_is_read_from_the_quantum_state_and_reflects_swapping():
    adapter, executor, repository, deliveries, events = run_chain(0.6, probe=True)

    assert repository.get("bds-intent").lifecycle.status == IntentStatus.ACTIVE
    assert events["ES_SUCCESS"] > 0 and events["EG_SUCCESS"] > 0
    assert len(deliveries) > 50
    app = executor.get_app("bds-intent")
    e2e = [(state, scalar, from_state) for state, scalar, from_state in app.observations]
    assert e2e, "the source app must have seen end-to-end pairs"
    for _, scalar, from_state in e2e:
        assert scalar == pytest.approx(from_state, abs=1e-12)  # scalar bookkeeping == stored state
    fidelities = [r["fidelity"] for r in deliveries]
    # every pair went through exactly one swap of two raw pairs, minus a little idle decoherence
    assert max(fidelities) <= SWAP_FIDELITY + 1e-12
    assert min(fidelities) > SWAP_FIDELITY - 0.02
    assert len(set(round(f, 9) for f in fidelities)) > 1, "with finite coherence time fidelities must not be a single constant"


@pytest.mark.unit
def test_with_infinite_coherence_the_swap_output_is_exactly_the_closed_form():
    _, _, _, deliveries, _ = run_chain(0.6, coherence_time_s=-1)
    assert deliveries
    for record in deliveries:
        assert record["fidelity"] == pytest.approx(SWAP_FIDELITY, abs=1e-12)


@pytest.mark.unit
def test_purification_really_runs_with_physical_failures_and_state_derived_output():
    _, _, _, deliveries, events = run_chain(0.78)  # 0.78 > 0.73: purification required

    assert events["EP_SUCCESS"] > 0
    assert events["EP_FAILURE"] > 0, "BBPSSW must fail with its physical probability, not always succeed"
    failure_rate = events["EP_FAILURE"] / (events["EP_FAILURE"] + events["EP_SUCCESS"])
    p_success = bds_purification_step(SWAP_FIDELITY, SWAP_FIDELITY, own_gate_fidelity=1, own_measurement_fidelity=1,
                                      remote_gate_fidelity=1, remote_measurement_fidelity=1)[0]
    assert abs(failure_rate - (1 - p_success)) < 0.08  # ~0.295 expected; loose band for one seed
    assert deliveries
    for record in deliveries:
        assert record["fidelity"] >= 0.78
    assert min(r["fidelity"] for r in deliveries) <= ONE_ROUND + 0.05


@pytest.mark.unit
def test_purification_mode_is_installed_on_the_shared_reservation_object():
    adapter, executor, _, _, _ = run_chain(0.78, mode="once")
    app = executor.get_app("bds-intent")
    assert app.reservation is not None
    assert app.reservation.purification_mode == "once"
    # the interior and destination routers hold the very same object, so they saw the mode too
    for router_id in ("r1", "b"):
        accepted = adapter.get_router(router_id).network_manager.rsvp.accepted_reservations
        assert accepted and accepted[0] is app.reservation


@pytest.mark.unit
def test_never_mode_disables_purification_at_execution_time():
    _, _, _, deliveries, events = run_chain(0.78, mode="never")
    assert events["EP_SUCCESS"] == 0 and events["EP_FAILURE"] == 0
    assert deliveries == []  # swapped pairs (0.73) never reach 0.78 without purification


@pytest.mark.unit
def test_once_mode_purifies_each_pair_at_most_one_time():
    _, _, _, deliveries_once, events_once = run_chain(0.78, mode="once")
    _, _, _, deliveries_until, events_until = run_chain(0.78, mode="until_target")

    # one round from 0.73 gives ~0.7676 < 0.78, so a single-round policy cannot deliver...
    assert deliveries_once == []
    assert 0 < events_once["EP_SUCCESS"]
    # ...while until_target keeps going and does
    assert len(deliveries_until) > 0
    assert events_until["EP_SUCCESS"] > events_once["EP_SUCCESS"]


@pytest.mark.unit
def test_stronger_decoherence_lowers_delivered_fidelity_without_crashing():
    _, _, repo_slow, slow, _ = run_chain(0.6, coherence_time_s=1.0)
    _, _, repo_fast, fast, _ = run_chain(0.6, coherence_time_s=0.01)

    assert repo_slow.get("bds-intent").lifecycle.status == IntentStatus.ACTIVE
    assert repo_fast.get("bds-intent").lifecycle.status == IntentStatus.ACTIVE  # no SIMULATION_ERROR
    mean = lambda rows: sum(r["fidelity"] for r in rows) / len(rows)
    assert fast and slow
    assert mean(fast) < mean(slow) - 0.03
    assert min(r["fidelity"] for r in fast) >= 0.6  # delivered pairs still honor the reservation target


@pytest.mark.unit
def test_gate_noise_lowers_the_swap_output_as_the_closed_form_predicts():
    _, _, _, deliveries, _ = run_chain(0.6, coherence_time_s=-1, gate_fidelity=0.98, measurement_fidelity=0.98)
    expected = bds_swap_fidelity(RAW, RAW, gate_fidelity=0.98, measurement_fidelity=0.98)
    assert deliveries
    for record in deliveries:
        assert record["fidelity"] == pytest.approx(expected, abs=1e-12)
    assert expected < SWAP_FIDELITY


@pytest.mark.unit
def test_planner_estimate_matches_the_simulated_swap_output_under_bell_diagonal():
    spec = chain_spec(coherence_time_s=-1)
    capabilities = NetworkCapabilities(spec)
    intent = build_intent(0.6)
    plan = IntentPlanner(capabilities).plan(intent)
    assert plan.feasible and plan.purification_mode == "until_target"
    assert plan.estimated_metrics.fidelity == pytest.approx(SWAP_FIDELITY)

    _, _, _, deliveries, _ = run_chain(0.6, coherence_time_s=-1)
    assert deliveries[0]["fidelity"] == pytest.approx(plan.estimated_metrics.fidelity, abs=1e-12)


@pytest.mark.unit
@pytest.mark.parametrize("strategy,mode", [(NeverPurify(), "never"), (PurifyOnce(), "once"), (PurifyUntilTarget(), "until_target")])
def test_planner_records_the_strategy_execution_mode_on_the_plan(strategy, mode):
    capabilities = NetworkCapabilities(chain_spec())
    plan = IntentPlanner(capabilities, purification_strategy=strategy).plan(build_intent(0.6))
    assert plan.feasible
    assert plan.purification_mode == mode


@pytest.mark.unit
def test_purified_pairs_are_delivered_and_counted_under_bell_diagonal():
    """`RequestApp.get_memory` ignores `PURIFIED` memories; IBQN's app must
    still count them (the pre-revision fix), now on Bell-diagonal states."""
    _, executor, _, deliveries, _ = run_chain(0.78, probe=True)
    app = executor.get_app("bds-intent")
    purified_seen = [obs for obs in app.observations if obs[0] == "PURIFIED"]
    assert purified_seen
    assert len(deliveries) == app.memory_counter > 0
