"""Centralizes every direct interaction with SeQUeNCe's application/reservation
API (`RequestApp`, `NetworkManager.request`, `sequence.utils.metrics`), so the
rest of `ibqn` only ever deals with `EntanglementIntent`/`ExecutionPlan`/
`IntentRepository` (see docs/architecture.md).

Two entry points:
- `submit(intent)` (Etapa D): no planning at all - route/purification/swap
  decisions are entirely delegated to SeQUeNCe's default reservation
  mechanism (`NetworkManager.request` -> `RSVPProtocol`/
  `ResourceManager.generate_load_rules`, see docs/sequence_code_analysis.md
  section 4.2). Kept for callers that don't need `planning.IntentPlanner`.
- `deploy(intent, plan)` (Etapa E): takes a real `planning.ExecutionPlan`,
  rejects the intent outright if it was infeasible, otherwise forces the
  reservation onto `plan.route` (via `execution.compiler.apply_route`)
  before submitting it - the plan's purification/swapping fields are
  estimates recorded for later comparison against observed telemetry
  (`assurance.evaluator`, Etapa G), not additional instructions given to
  SeQUeNCe: it still decides purification/swap order on its own, exactly as
  `submit()` does.
"""
from __future__ import annotations

from sequence.app.request_app import RequestApp
from sequence.constants import SECOND
from sequence.resource_management.memory_manager import MemoryInfo
from sequence.topology.node import QuantumRouter
from sequence.utils import metrics
from sequence.utils.metrics.event_types import EventTypes

from ..intent.models import EntanglementIntent, IntentStatus
from ..intent.repository import IntentRepository
from ..network.sequence_adapter import SequenceAdapter
from ..planning.models import ExecutionPlan
from ..utils.logging import get_logger
from .compiler import apply_route

logger = get_logger(__name__)

_TELEMETRY_EVENTS = [
    EventTypes.EG_SUCCESS,
    EventTypes.EG_FAILURE,
    EventTypes.EP_SUCCESS,
    EventTypes.EP_FAILURE,
    EventTypes.ES_SUCCESS,
    EventTypes.ES_FAILURE,
    EventTypes.DELIVERY,
]


class IntentRequestApp(RequestApp):
    """A `RequestApp` that reports reservation approval/rejection and every
    genuinely delivered pair back into an `IntentRepository`, and mirrors
    delivered pairs into `sequence.utils.metrics` as `EventTypes.DELIVERY`
    (a native event type the SeQUeNCe core never triggers itself - see
    docs/sequence_code_analysis.md, section 4.7).

    `RequestApp.get_memory` only increments `memory_counter` on the
    reservation's *initiator* side (`info.remote_node == reservation.responder`);
    on the responder side it only resets the memory to RAW without counting
    (`sequence/app/request_app.py:133-143`) - so `_delivered_pairs`/the
    DELIVERY metric only ever fire from the app attached to the intent's
    source router, never from the destination one. The destination app is
    still required though: without *any* app attached, `Node.get_idle_memory`
    never resets delivered memories back to RAW, which would starve any
    reservation asking for more pairs than it has memories for."""

    def __init__(self, node: QuantumRouter, intent_id: str, repository: IntentRepository):
        super().__init__(node)
        self.intent_id = intent_id
        self._repository = repository
        self._delivered_pairs = 0

    def _now_s(self) -> float:
        return self.node.timeline.now() / SECOND

    def get_reservation_result(self, reservation, result: bool) -> None:
        super().get_reservation_result(reservation, result)
        if result:
            self._repository.transition(
                self.intent_id, IntentStatus.ACTIVE, "reservation approved", sim_time=self._now_s()
            )
        else:
            self._repository.transition(
                self.intent_id, IntentStatus.FAILED, "reservation rejected by NetworkManager", sim_time=self._now_s()
            )

    def get_memory(self, info: MemoryInfo) -> None:
        # `info.fidelity` must be read *before* calling super(): on a
        # successful match, RequestApp.get_memory resets the memory to RAW
        # (MemoryInfo.to_raw() zeroes `fidelity` in place on this same,
        # mutable `info` object) as a side effect - reading it afterwards
        # would always observe 0.
        fidelity_at_delivery = info.fidelity
        pairs_before = self.memory_counter
        super().get_memory(info)
        if self.memory_counter > pairs_before:
            self._delivered_pairs += 1
            metrics.record(
                EventTypes.DELIVERY,
                self.node.name,
                intent_id=self.intent_id,
                fidelity=fidelity_at_delivery,
                pair_number=self._delivered_pairs,
            )


class SequenceExecutor:
    """Compiles one `EntanglementIntent` at a time into a real SeQUeNCe
    reservation and runs the simulation. One `IntentRequestApp` is attached
    to the source and destination router of each intent - since
    `QuantumRouter` supports only one application at a time (see
    docs/sequence_code_analysis.md, section 4.6), submitting a second intent
    that shares a source or destination router with an already-submitted one
    is not supported in this version.
    """

    def __init__(self, adapter: SequenceAdapter, repository: IntentRepository):
        self._adapter = adapter
        self._repository = repository
        self._source_apps: dict[str, IntentRequestApp] = {}
        self._destination_apps: dict[str, IntentRequestApp] = {}
        metrics.enable(_TELEMETRY_EVENTS)

    def _now_s(self) -> float:
        return self._adapter.get_timeline().now() / SECOND

    def submit(self, intent: EntanglementIntent) -> None:
        """Registers `intent`, walks it through RECEIVED -> ... -> DEPLOYING
        with no real planning step, and issues the real
        `NetworkManager.request(...)` call. The terminal outcome of that
        request (ACTIVE/FAILED) arrives later, asynchronously, through
        `IntentRequestApp.get_reservation_result` once the simulation runs.
        """
        now_s = self._now_s()
        self._repository.add(intent, sim_time=now_s)
        self._repository.transition(intent.id, IntentStatus.VALIDATED, "schema validated", sim_time=now_s)
        self._repository.transition(
            intent.id, IntentStatus.PLANNING,
            "no planner used: delegating route/purification decisions to SeQUeNCe's default reservation mechanism",
            sim_time=now_s,
        )
        self._repository.transition(intent.id, IntentStatus.PLANNED, "trivial pass-through plan", sim_time=now_s)
        self._repository.transition(
            intent.id, IntentStatus.DEPLOYING, "submitting reservation to NetworkManager", sim_time=now_s
        )
        self._start_reservation(intent)

    def deploy(self, intent: EntanglementIntent, plan: ExecutionPlan) -> None:
        """Registers `intent` and executes `plan`: rejects it immediately if
        `plan.feasible` is False, otherwise forces the reservation onto
        `plan.route` and submits it."""
        now_s = self._now_s()
        self._repository.add(intent, sim_time=now_s)
        self._repository.transition(intent.id, IntentStatus.VALIDATED, "schema validated", sim_time=now_s)
        self._repository.transition(intent.id, IntentStatus.PLANNING, "invoking IntentPlanner", sim_time=now_s)

        if not plan.feasible:
            self._repository.transition(
                intent.id, IntentStatus.REJECTED,
                plan.infeasibility_reason or "no feasible execution plan", sim_time=now_s,
            )
            return

        self._repository.transition(intent.id, IntentStatus.PLANNED, plan.route_rationale, sim_time=now_s)
        self._repository.transition(
            intent.id, IntentStatus.DEPLOYING,
            f"applying route {'->'.join(plan.route)} and submitting reservation to NetworkManager",
            sim_time=now_s,
        )
        if len(plan.route) > 2:
            apply_route(self._adapter, plan.route)
        self._start_reservation(intent)

    def _start_reservation(self, intent: EntanglementIntent) -> None:
        source = self._adapter.get_router(intent.endpoints.source)
        destination = self._adapter.get_router(intent.endpoints.destination)

        source_app = IntentRequestApp(source, intent.id, self._repository)
        destination_app = IntentRequestApp(destination, intent.id, self._repository)
        self._source_apps[intent.id] = source_app
        self._destination_apps[intent.id] = destination_app

        start_ps = int(intent.requirements.start_time * SECOND)
        end_ps = int((intent.requirements.start_time + intent.requirements.duration) * SECOND)
        logger.info(
            "submitting reservation %s -> %s, pairs=%d, min_fidelity=%.3f",
            intent.endpoints.source, intent.endpoints.destination,
            intent.requirements.requested_pairs, intent.requirements.min_fidelity,
            extra={"intent_id": intent.id},
        )
        source_app.start(
            intent.endpoints.destination, start_ps, end_ps,
            intent.requirements.requested_pairs, intent.requirements.min_fidelity,
        )

    def run(self) -> None:
        self._adapter.run()

    def get_app(self, intent_id: str) -> IntentRequestApp:
        """Returns the source (initiator) app - the only one that receives
        `get_reservation_result` and therefore drives the intent's
        ACTIVE/FAILED lifecycle transitions (see
        docs/sequence_code_analysis.md, section 4.2: only the reservation's
        initiator gets `get_reservation_result`, the responder gets
        `get_other_reservation` instead)."""
        return self._source_apps[intent_id]

    def get_destination_app(self, intent_id: str) -> IntentRequestApp:
        return self._destination_apps[intent_id]
