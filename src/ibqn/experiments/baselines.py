"""Baselines quantifying what the IBQN layer actually contributes (Fase
J3, see docs/baselines.md): the intent-based pipeline is compared against
three deliberately simpler alternatives, all sharing the same topology,
seed, physical parameters, reservation window, and intent-declared
requirements as the IBQN condition, so any difference in outcome is
attributable to the *architecture*, not to a confound.

- `run_native_sequence_baseline`: stock `sequence.app.request_app.RequestApp`
  directly against `NetworkManager`/the topology's auto-generated static
  routing table - no `EntanglementIntent`, no planner, no assurance, no
  reconciliation.
- `run_static_provisioning_baseline`: a route is picked ONCE, with no
  feasibility check at all (skips `IntentPlanner.plan()` entirely), then
  deployed and run exactly once - no reaction, no reconciliation; success
  is evaluated only after the run, purely for comparison.
- `run_offline_oracle_baseline`: enumerates every simple path for small
  topologies, runs EACH ONE with the same seed, and reports the best
  outcome after seeing every result - a hindsight-only upper bound, never
  an implementable online strategy.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import networkx as nx
from sequence.app.request_app import RequestApp
from sequence.constants import SECOND
from sequence.utils import metrics

from ..assurance.evaluator import evaluate_intent
from ..assurance.telemetry import collect_intent_evidence
from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import NetworkTopologySpec
from ..planning.models import ExecutionPlan
from ..planning.routing import RoutingStrategy, ShortestHopCountRouting


@dataclass
class BaselineResult:
    """One baseline's outcome for one intent/seed - deliberately mirrors
    the subset of `experiments.records.TrialRecord` fields needed for a
    fair cross-baseline comparison (see docs/baselines.md, section
    "Métricas de comparação")."""

    baseline_name: str
    intent_id: str
    seed: int
    route: list[str]
    accepted: bool
    satisfied: bool | None
    delivered_pairs: int | None
    average_fidelity: float | None
    minimum_fidelity: float | None
    throughput_active_window: float | None
    planning_wall_time_s: float
    simulation_wall_time_s: float
    total_wall_time_s: float
    episodes: int
    candidates_evaluated: int
    notes: str = ""


class _FidelityProbeRequestApp(RequestApp):
    """Instruments stock `RequestApp` purely for MEASUREMENT: records each
    delivered memory's fidelity before `get_memory` resets it to `RAW` -
    the same measurement problem IBQN's `IntentRequestApp`/`DELIVERY`
    event solves for intent-scoped telemetry (Etapa G), reused here only
    so `run_native_sequence_baseline` can report a fidelity metric at
    all. Never changes routing/reservation/counting behavior:
    `self.memory_counter` is updated by the unmodified base class exactly
    as stock `RequestApp` would (including its documented undercount of
    `"PURIFIED"`-state pairs, see docs/limitations.md) - preserving that
    behavior faithfully is the point of a *native* baseline."""

    def __init__(self, node):
        super().__init__(node)
        self.observed_fidelities: list[float] = []

    def get_memory(self, info) -> None:
        if info.state == "ENTANGLED":
            self.observed_fidelities.append(info.fidelity)
        super().get_memory(info)


def run_native_sequence_baseline(
    topology_spec: NetworkTopologySpec, intent: EntanglementIntent, *, seed: int,
) -> BaselineResult:
    """Baseline A ("Native SeQUeNCe Request"): `topology -> forwarding
    table -> network_manager.request(...) -> execution`, with no
    `EntanglementIntent`-based planning, assurance, or reconciliation at
    all - routing is whatever `RouterNetTopo`'s auto-generated static
    routing table already computed (unweighted shortest path), the same
    default SeQUeNCe ships with when no external planner intervenes."""
    metrics.configure()
    t0 = time.perf_counter()
    adapter = SequenceAdapter(topology_spec, seed=seed)
    source_router = adapter.get_router(intent.endpoints.source)
    destination_router = adapter.get_router(intent.endpoints.destination)

    source_app = _FidelityProbeRequestApp(source_router)
    _FidelityProbeRequestApp(destination_router)  # required so delivered memories reset to RAW (docs/limitations.md)

    start_ps = int(intent.requirements.start_time_s * SECOND)
    end_ps = int((intent.requirements.start_time_s + intent.requirements.duration_s) * SECOND)
    source_app.start(
        intent.endpoints.destination, start_ps, end_ps,
        intent.requirements.reserved_memory_slots, intent.requirements.min_fidelity,
    )

    t1 = time.perf_counter()
    adapter.run()
    simulation_wall_time_s = time.perf_counter() - t1

    route: list[str] = []
    if source_app.reservation_result:
        accepted_reservations = source_router.network_manager.protocol_stack[-1].accepted_reservations
        if accepted_reservations:
            route = list(accepted_reservations[0].path)

    delivered = source_app.memory_counter
    fidelities = source_app.observed_fidelities
    average_fidelity = sum(fidelities) / len(fidelities) if fidelities else None
    minimum_fidelity = min(fidelities) if fidelities else None
    throughput = delivered / intent.requirements.duration_s if source_app.reservation_result else None
    satisfied = (
        delivered >= (intent.requirements.min_delivered_pairs or intent.requirements.reserved_memory_slots)
        if source_app.reservation_result else False
    )

    return BaselineResult(
        baseline_name="native_sequence", intent_id=intent.id, seed=seed, route=route,
        accepted=source_app.reservation_result, satisfied=satisfied,
        delivered_pairs=delivered if source_app.reservation_result else None,
        average_fidelity=average_fidelity, minimum_fidelity=minimum_fidelity,
        throughput_active_window=throughput,
        planning_wall_time_s=0.0,  # no planning step exists in this baseline, by design
        simulation_wall_time_s=round(simulation_wall_time_s, 6),
        total_wall_time_s=round(time.perf_counter() - t0, 6),
        episodes=1, candidates_evaluated=0,
        notes="no per-pair DELIVERY telemetry: fidelity is measured by a passive probe added only for "
              "comparison (see _FidelityProbeRequestApp); memory_counter inherits stock RequestApp's "
              "known PURIFIED-state undercount",
    )


def run_static_provisioning_baseline(
    topology_spec: NetworkTopologySpec, intent: EntanglementIntent, *,
    seed: int, routing_strategy: RoutingStrategy | None = None,
) -> BaselineResult:
    """Baseline B ("Static Provisioning"): a route is chosen ONCE, with NO
    feasibility check at all (no memory/fidelity estimate, no rejection
    possible before deploying) - just the first candidate path
    `routing_strategy` proposes - then deployed and run exactly once.
    No reaction to intermediate results, no reconciliation. Success is
    evaluated only AFTER the run, purely for scientific comparison - the
    evaluation itself is not part of what this baseline "does"."""
    routing_strategy = routing_strategy or ShortestHopCountRouting()
    t0 = time.perf_counter()
    capabilities = NetworkCapabilities(topology_spec)
    candidates = routing_strategy.find_candidate_paths(
        capabilities, intent.endpoints.source, intent.endpoints.destination
    )
    if not candidates:
        return BaselineResult(
            baseline_name="static_provisioning", intent_id=intent.id, seed=seed, route=[],
            accepted=False, satisfied=False, delivered_pairs=None, average_fidelity=None,
            minimum_fidelity=None, throughput_active_window=None,
            planning_wall_time_s=round(time.perf_counter() - t0, 6), simulation_wall_time_s=0.0,
            total_wall_time_s=round(time.perf_counter() - t0, 6), episodes=0, candidates_evaluated=0,
            notes="no candidate route found by the fixed routing strategy",
        )
    route = candidates[0]
    plan = ExecutionPlan(
        intent_id=intent.id, feasible=True, route=route,
        route_rationale=f"static provisioning: fixed {type(routing_strategy).__name__} choice, no feasibility check",
        fidelity_estimator="none (static provisioning baseline never estimates)",
    )
    planning_wall_time_s = time.perf_counter() - t0

    repository = IntentRepository()
    metrics.configure()
    adapter = SequenceAdapter(topology_spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, plan)

    t1 = time.perf_counter()
    executor.run()
    simulation_wall_time_s = time.perf_counter() - t1

    record_status = repository.get(intent.id).lifecycle.status
    if record_status != IntentStatus.ACTIVE:
        return BaselineResult(
            baseline_name="static_provisioning", intent_id=intent.id, seed=seed, route=route,
            accepted=False, satisfied=False, delivered_pairs=None, average_fidelity=None,
            minimum_fidelity=None, throughput_active_window=None,
            planning_wall_time_s=round(planning_wall_time_s, 6),
            simulation_wall_time_s=round(simulation_wall_time_s, 6),
            total_wall_time_s=round(time.perf_counter() - t0, 6), episodes=1, candidates_evaluated=1,
            notes=f"reservation ended in {record_status.value}, not ACTIVE",
        )

    evidence = collect_intent_evidence(intent)
    evaluation = evaluate_intent(intent, evidence)
    fidelities = [p.fidelity for p in evidence.delivered_pairs]

    return BaselineResult(
        baseline_name="static_provisioning", intent_id=intent.id, seed=seed, route=route,
        accepted=True, satisfied=evaluation.satisfied, delivered_pairs=len(evidence.delivered_pairs),
        average_fidelity=(sum(fidelities) / len(fidelities)) if fidelities else None,
        minimum_fidelity=min(fidelities) if fidelities else None,
        throughput_active_window=len(evidence.delivered_pairs) / intent.requirements.duration_s,
        planning_wall_time_s=round(planning_wall_time_s, 6),
        simulation_wall_time_s=round(simulation_wall_time_s, 6),
        total_wall_time_s=round(time.perf_counter() - t0, 6), episodes=1, candidates_evaluated=1,
    )


def run_offline_oracle_baseline(
    topology_spec: NetworkTopologySpec, intent: EntanglementIntent, *,
    seed: int, max_candidates: int = 10,
) -> BaselineResult:
    """Baseline C ("Offline Oracle"): enumerates every simple path between
    the intent's endpoints, runs EACH ONE (same seed, same intent, fully
    isolated Timelines), and reports whichever result is best AFTER
    seeing every outcome. An offline, hindsight-only upper bound - NOT an
    implementable online strategy (a real planner cannot see the
    future); only defined for topologies small enough to enumerate
    exhaustively (raises if there are more than `max_candidates` simple
    paths, rather than silently sampling a subset)."""
    t0 = time.perf_counter()
    capabilities = NetworkCapabilities(topology_spec)
    graph = capabilities.graph()
    try:
        all_paths = list(nx.all_simple_paths(graph, intent.endpoints.source, intent.endpoints.destination))
    except nx.NodeNotFound:
        all_paths = []
    if len(all_paths) > max_candidates:
        raise ValueError(
            f"offline oracle only supports small topologies (<= {max_candidates} simple paths between "
            f"'{intent.endpoints.source}' and '{intent.endpoints.destination}'), found {len(all_paths)} - "
            f"this baseline is a hindsight upper bound, not a scalable strategy (see docs/baselines.md)"
        )
    if not all_paths:
        return BaselineResult(
            baseline_name="offline_oracle", intent_id=intent.id, seed=seed, route=[],
            accepted=False, satisfied=False, delivered_pairs=None, average_fidelity=None,
            minimum_fidelity=None, throughput_active_window=None,
            planning_wall_time_s=round(time.perf_counter() - t0, 6), simulation_wall_time_s=0.0,
            total_wall_time_s=round(time.perf_counter() - t0, 6), episodes=0, candidates_evaluated=0,
            notes="no path exists between source and destination",
        )

    candidate_results: list[BaselineResult] = []
    total_simulation_wall_time_s = 0.0
    for route in all_paths:
        plan = ExecutionPlan(
            intent_id=intent.id, feasible=True, route=route,
            route_rationale="offline oracle candidate - evaluated only in hindsight",
            fidelity_estimator="none (oracle baseline never estimates)",
        )
        repository = IntentRepository()
        metrics.configure()
        adapter = SequenceAdapter(topology_spec, seed=seed)
        executor = SequenceExecutor(adapter, repository)
        executor.deploy(intent, plan)

        t1 = time.perf_counter()
        executor.run()
        candidate_wall_time_s = time.perf_counter() - t1
        total_simulation_wall_time_s += candidate_wall_time_s

        record_status = repository.get(intent.id).lifecycle.status
        if record_status != IntentStatus.ACTIVE:
            candidate_results.append(BaselineResult(
                baseline_name="offline_oracle", intent_id=intent.id, seed=seed, route=route,
                accepted=False, satisfied=False, delivered_pairs=None, average_fidelity=None,
                minimum_fidelity=None, throughput_active_window=None,
                planning_wall_time_s=0.0, simulation_wall_time_s=round(candidate_wall_time_s, 6),
                total_wall_time_s=0.0, episodes=1, candidates_evaluated=1,
                notes=f"reservation ended in {record_status.value}, not ACTIVE",
            ))
            continue

        evidence = collect_intent_evidence(intent)
        evaluation = evaluate_intent(intent, evidence)
        fidelities = [p.fidelity for p in evidence.delivered_pairs]
        candidate_results.append(BaselineResult(
            baseline_name="offline_oracle", intent_id=intent.id, seed=seed, route=route,
            accepted=True, satisfied=evaluation.satisfied, delivered_pairs=len(evidence.delivered_pairs),
            average_fidelity=(sum(fidelities) / len(fidelities)) if fidelities else None,
            minimum_fidelity=min(fidelities) if fidelities else None,
            throughput_active_window=len(evidence.delivered_pairs) / intent.requirements.duration_s,
            planning_wall_time_s=0.0, simulation_wall_time_s=round(candidate_wall_time_s, 6),
            total_wall_time_s=0.0, episodes=1, candidates_evaluated=1,
        ))

    def _score(result: BaselineResult) -> tuple[bool, int]:
        return (bool(result.satisfied), result.delivered_pairs or -1)

    best = max(candidate_results, key=_score)
    best.candidates_evaluated = len(candidate_results)
    best.planning_wall_time_s = round(time.perf_counter() - t0 - total_simulation_wall_time_s, 6)
    best.simulation_wall_time_s = round(total_simulation_wall_time_s, 6)
    best.total_wall_time_s = round(time.perf_counter() - t0, 6)
    best.notes = (
        f"best of {len(candidate_results)} candidate route(s) evaluated in hindsight - "
        f"not an online-implementable strategy" + (f"; {best.notes}" if best.notes else "")
    )
    return best
