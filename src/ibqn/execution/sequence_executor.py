"""Centralizes every direct interaction with SeQUeNCe's application/reservation
API (`RequestApp`, `NetworkManager.request`, `sequence.utils.metrics`), so the
rest of `ibqn` only ever deals with `EntanglementIntent`/`ExecutionPlan`/
`IntentRepository` (see docs/architecture.md).

Three entry points:
- `submit(intent)` (Etapa D): no planning at all - route/purification/swap
  decisions are entirely delegated to SeQUeNCe's default reservation
  mechanism (`NetworkManager.request` -> `RSVPProtocol`/
  `ResourceManager.generate_load_rules`, see docs/sequence_code_analysis.md
  section 4.2). Kept for callers that don't need `planning.IntentPlanner`.
- `deploy(intent, plan)` (Etapa E): registers a brand-new `intent` and
  executes `plan` - rejects it outright if it was infeasible, otherwise
  forces the reservation onto `plan.route` (via
  `execution.compiler.apply_route`) and installs the plan's purification
  policy (`plan.purification_mode` -> `Reservation.purification_mode`, see
  `IntentRequestApp.start_intent` and docs/physical_model.md) before
  submitting it. Everything else the plan carries about purification/
  swapping (`purification_rounds_estimate`, `swapping_strategy_note`) is
  an estimate recorded for later comparison against observed telemetry
  (`assurance.evaluator`, Etapa G): SeQUeNCe still decides swap order (its
  balanced bisection of the path) and the reservation target fidelity is
  the intent's own `min_fidelity`.
- `redeploy(intent, plan)` (Etapa G, `assurance.reconciliation`): same as
  `deploy`, but for an `intent` that is *already registered* in `repository`
  (typically mid-reconciliation, sitting in status `PLANNING`) - does not
  call `repository.add()`/re-validate, so the intent's lifecycle history
  continues instead of restarting.
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
from ..planning.purification import PURIFICATION_MODES
from ..utils.logging import get_logger
from .compiler import apply_route

logger = get_logger(__name__)

DEFAULT_PURIFICATION_MODE = "until_target"
"""SeQUeNCe's own default (`Reservation.purification_mode`) - what every
reservation executed before plans carried a purification policy."""

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
    reservation asking for more pairs than it has memories for.

    CRITICAL: `RequestApp.get_memory` (`sequence/app/request_app.py:133`)
    starts with `if info.state != "ENTANGLED": return` - it silently ignores
    memories in the `"PURIFIED"` state. A successfully purified end-to-end
    pair (`MemoryInfo.to_purified()` populates the exact same `remote_node`/
    `fidelity`/`index` fields as `to_entangled()`, see
    docs/sequence_code_analysis.md section 4.5) would therefore NEVER be
    counted, reset to RAW, or reported as delivered by the stock `RequestApp`
    - confirmed empirically: a purification-forcing scenario produced 9
    EP_SUCCESS events but `memory_counter` stayed at 0 for the entire run
    (see docs/assurance_design.md). `get_memory` below mirrors the same
    matching/counting logic for `"PURIFIED"` that `RequestApp.get_memory`
    already applies to `"ENTANGLED"`, since SeQUeNCe's core does not expose a
    way to do this without duplicating those four lines."""

    def __init__(self, node: QuantumRouter, intent_id: str, repository: IntentRepository):
        super().__init__(node)
        self.intent_id = intent_id
        self._repository = repository
        self._delivered_pairs = 0
        self.reservation = None
        """The `Reservation` this app's `start_intent` created (initiator
        side only), or `None` before `start_intent`/if `RSVPProtocol.push`
        rejected it immediately for lack of local memories."""
        self.purification_mode: str = DEFAULT_PURIFICATION_MODE

    def _now_s(self) -> float:
        return self.node.timeline.now() / SECOND

    def start_intent(
        self, responder: str, start_t: int, end_t: int, memo_size: int, fidelity: float, *, purification_mode: str,
    ) -> None:
        """`RequestApp.start` plus the purification policy the plan chose
        (docs/physical_model.md).

        `RequestApp.start` -> `QuantumRouter.reserve_net_resource` ->
        `NetworkManager.request` -> `RSVPProtocol.push` runs synchronously
        and, if this node has the memories, creates the `Reservation`
        object, books it on the local `MemoryTimeCard`s and hands the SAME
        object to the outgoing `RSVPMessage`. SeQUeNCe relays that one
        object by reference along the whole path (`ClassicalChannel.transmit`
        schedules the message object itself), and every node reads
        `reservation.purification_mode` only later, when the APPROVE comes
        back and `ResourceManager.generate_load_rules` builds its rules -
        so setting the attribute here, right after `start`, is seen by all
        of them. (`RSVPProtocol.purification_mode`/`set_purification_mode`
        exist in SeQUeNCe 1.0 but are never copied into the reservation, so
        they cannot be used for this.)"""
        if purification_mode not in PURIFICATION_MODES:
            raise ValueError(f"unknown purification_mode {purification_mode!r} - supported: {PURIFICATION_MODES}")
        self.purification_mode = purification_mode
        self.start(responder, start_t, end_t, memo_size, fidelity)
        self.reservation = self._find_own_reservation(responder, start_t, end_t)
        if self.reservation is not None:
            self.reservation.purification_mode = purification_mode

    def _find_own_reservation(self, responder: str, start_t: int, end_t: int):
        for card in self.node.network_manager.rsvp.timecards:
            for reservation in card.reservations:
                if (
                    reservation.initiator == self.node.name and reservation.responder == responder
                    and reservation.start_time == start_t and reservation.end_time == end_t
                ):
                    return reservation
        return None

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
        # `info.fidelity`/`info.remote_node`/`info.remote_memo` must be read
        # *before* any state change: a successful match resets the memory to
        # RAW (MemoryInfo.to_raw() zeroes these fields in place on this same,
        # mutable `info` object) as a side effect - reading them afterwards
        # would always observe stale/zeroed values.
        fidelity_at_delivery = info.fidelity
        local_memory = info.memory.name
        remote_node_at_delivery = info.remote_node
        remote_memory_at_delivery = info.remote_memo

        if info.state == "ENTANGLED":
            pairs_before = self.memory_counter
            super().get_memory(info)
            newly_delivered = self.memory_counter > pairs_before
        elif info.state == "PURIFIED":
            newly_delivered = self._count_purified_delivery(info)
        else:
            return

        if newly_delivered:
            self._delivered_pairs += 1
            metrics.record(
                EventTypes.DELIVERY,
                self.node.name,
                intent_id=self.intent_id,
                fidelity=fidelity_at_delivery,
                pair_number=self._delivered_pairs,
                local_memory=local_memory,
                remote_node=remote_node_at_delivery,
                remote_memory=remote_memory_at_delivery,
            )

    def _count_purified_delivery(self, info: MemoryInfo) -> bool:
        """Mirrors `RequestApp.get_memory`'s matching/counting/reset logic
        (`sequence/app/request_app.py:136-143`) for the `"PURIFIED"` state,
        which the stock method never handles (see the class docstring)."""
        if info.index not in self.memo_to_reservation:
            return False
        reservation = self.memo_to_reservation[info.index]
        if info.fidelity < reservation.fidelity:
            return False
        if info.remote_node == reservation.initiator:
            self.node.resource_manager.update(None, info.memory, "RAW")
            return False
        if info.remote_node == reservation.responder:
            self.memory_counter += 1
            self.node.resource_manager.update(None, info.memory, "RAW")
            return True
        return False


class SequenceExecutor:
    """Compiles one or more `EntanglementIntent`s into real SeQUeNCe
    reservations and runs the simulation. One `IntentRequestApp` is attached
    to the source and destination router of each intent - since
    `QuantumRouter` supports only one application at a time (see
    docs/sequence_code_analysis.md, section 4.6), two intents cannot share a
    source or destination router; `_start_reservation` raises `ValueError`
    rather than silently letting the second intent's app overwrite the
    first's (which would misroute `get_reservation_result`/`get_memory`
    callbacks to the wrong `intent_id` - see docs/assurance_design.md).
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
        self._start_reservation(intent, DEFAULT_PURIFICATION_MODE)

    def deploy(self, intent: EntanglementIntent, plan: ExecutionPlan) -> None:
        """Registers a brand-new `intent` and executes `plan`."""
        now_s = self._now_s()
        self._repository.add(intent, sim_time=now_s)
        self._repository.transition(intent.id, IntentStatus.VALIDATED, "schema validated", sim_time=now_s)
        self._repository.transition(intent.id, IntentStatus.PLANNING, "invoking IntentPlanner", sim_time=now_s)
        self._deploy_plan(intent, plan)

    def redeploy(self, intent: EntanglementIntent, plan: ExecutionPlan) -> None:
        """Executes `plan` for an `intent` that is *already registered* in
        `repository` and currently sitting in status `PLANNING` (see
        `assurance.reconciliation.reconcile`) - does not call
        `repository.add()`/re-validate, so the intent's lifecycle history
        continues rather than restarting."""
        self._deploy_plan(intent, plan)

    def _deploy_plan(self, intent: EntanglementIntent, plan: ExecutionPlan) -> None:
        now_s = self._now_s()
        if not plan.feasible:
            self._repository.transition(
                intent.id, IntentStatus.REJECTED,
                plan.infeasibility_reason or "no feasible execution plan", sim_time=now_s,
            )
            return

        self._repository.transition(intent.id, IntentStatus.PLANNED, plan.route_rationale, sim_time=now_s)
        self._repository.transition(
            intent.id, IntentStatus.DEPLOYING,
            f"applying route {'->'.join(plan.route)} and submitting reservation to NetworkManager "
            f"(purification_mode={plan.purification_mode})",
            sim_time=now_s,
        )
        if len(plan.route) > 2:
            apply_route(self._adapter, plan.route)
        self._start_reservation(intent, plan.purification_mode)

    def _start_reservation(self, intent: EntanglementIntent, purification_mode: str) -> None:
        source = self._adapter.get_router(intent.endpoints.source)
        destination = self._adapter.get_router(intent.endpoints.destination)
        self._check_no_node_conflict(intent.id, source)
        self._check_no_node_conflict(intent.id, destination)

        source_app = IntentRequestApp(source, intent.id, self._repository)
        destination_app = IntentRequestApp(destination, intent.id, self._repository)
        self._source_apps[intent.id] = source_app
        self._destination_apps[intent.id] = destination_app

        start_ps = int(intent.requirements.start_time_s * SECOND)
        end_ps = int((intent.requirements.start_time_s + intent.requirements.duration_s) * SECOND)
        logger.info(
            "submitting reservation %s -> %s, reserved_memory_slots=%d, min_fidelity=%.3f, purification_mode=%s",
            intent.endpoints.source, intent.endpoints.destination,
            intent.requirements.reserved_memory_slots, intent.requirements.min_fidelity, purification_mode,
            extra={"intent_id": intent.id},
        )
        source_app.start_intent(
            intent.endpoints.destination, start_ps, end_ps,
            intent.requirements.reserved_memory_slots, intent.requirements.min_fidelity,
            purification_mode=purification_mode,
        )

    @staticmethod
    def _check_no_node_conflict(intent_id: str, router: QuantumRouter) -> None:
        existing_app = router.app
        existing_intent_id = getattr(existing_app, "intent_id", None)
        if existing_app is not None and existing_intent_id != intent_id:
            raise ValueError(
                f"cannot deploy intent '{intent_id}': node '{router.name}' already hosts the app for "
                f"intent '{existing_intent_id}' - a QuantumRouter supports only one application at a "
                f"time (see docs/sequence_code_analysis.md, section 4.6), so these two intents cannot "
                f"share this node as a source or destination"
            )

    def run(self) -> None:
        """Runs the simulation. If SeQUeNCe itself raises mid-run (e.g. an
        internal protocol assertion), every intent this executor deployed
        that has not yet reached a terminal status is transitioned to
        FAILED before the exception is re-raised unchanged - so callers
        that catch it (as every existing experiment runner does, recording
        their own harness-level `final_status="SIMULATION_ERROR"`) still
        see identical control flow, but `IntentRepository`'s own lifecycle
        no longer leaves the intent stuck in a non-terminal status (see
        docs/paper_ibqn_validation/simulation_error_trace.md)."""
        try:
            self._adapter.run()
        except Exception as exc:
            now_s = self._now_s()
            for intent_id in self._source_apps:
                record = self._repository.get(intent_id)
                if not record.lifecycle.is_terminal:
                    self._repository.transition(
                        intent_id, IntentStatus.FAILED,
                        f"simulation raised {type(exc).__name__}: {exc}", sim_time=now_s,
                    )
            raise

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
