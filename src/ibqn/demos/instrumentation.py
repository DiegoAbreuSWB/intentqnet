"""Non-invasive memory-lifecycle observer for
`notebooks/05_sequence_memory_lifecycle.ipynb`.

Records every *real* `MemoryInfo` state transition (never a manually forced
state), with a timestamp and the protocol/mechanism responsible, by
monkeypatching bound methods on one router's live objects - no SeQUeNCe
source file is modified; the classes and every other instance are untouched.

Getting "responsible" right required reading the actual call graph
(`sequence/resource_management/resource_manager.py`), not guessing:
`MemoryInfo.to_raw/to_occupied/to_entangled/to_purified` (`memory_manager.py:135-165`)
are the *only* places `MemoryInfo.state` is ever assigned, but they carry no
argument identifying who called them. There are exactly three call sites:

1. `MemoryManager.update(memory, state)` (`memory_manager.py:48-69`), the
   sole caller for `state`-driven transitions - itself only ever called
   from `ResourceManager.update(protocol, memory, state)` (`resource_manager.py:322-361`),
   which *does* carry `protocol`.
2. `ResourceManager.update(...)` also calls `info.to_occupied()` directly
   (`resource_manager.py:358`) when re-evaluating rules finds an immediate
   match after the state above lands.
3. `ResourceManager.load(rule)` (`resource_manager.py:271-294`) calls
   `info.to_occupied()` directly when a freshly-installed rule matches
   immediately.

So this recorder wraps `ResourceManager.update`/`.load` only to track *who*
is currently responsible (a synchronous, single-threaded context - safe
because SeQUeNCe's kernel runs strictly one process at a time, see
docs/sequence_code_analysis.md section 4.1), and wraps each `MemoryInfo`'s
four `to_*` methods to record the actual, complete transition sequence.
"""
from __future__ import annotations

from dataclasses import dataclass

from sequence.constants import SECOND
from sequence.topology.node import QuantumRouter

_STATE_METHODS = ("to_raw", "to_occupied", "to_entangled", "to_purified")


@dataclass(frozen=True)
class MemoryTransition:
    sim_time_s: float
    memory_name: str
    old_state: str
    new_state: str
    responsible: str


class MemoryLifecycleRecorder:
    """Attach to a router *before* `Timeline.run()`; read `.transitions`
    afterwards. `.detach()` restores everything this patched (harmless to
    skip - the router is normally discarded with its `Timeline` anyway)."""

    def __init__(self, router: QuantumRouter):
        self._router = router
        self._resource_manager = router.resource_manager
        self.transitions: list[MemoryTransition] = []
        self._responsible = "(unattributed)"

        self._original_update = self._resource_manager.update
        self._original_load = self._resource_manager.load
        self._resource_manager.update = self._wrapped_update
        self._resource_manager.load = self._wrapped_load

        self._original_methods: dict[tuple[int, str], object] = {}
        for info in self._resource_manager.memory_manager:
            self._patch_memory_info(info)

    def _patch_memory_info(self, info) -> None:
        for method_name in _STATE_METHODS:
            original = getattr(info, method_name)
            self._original_methods[(id(info), method_name)] = original
            setattr(info, method_name, self._make_recording_method(info, original))

    def _make_recording_method(self, info, original):
        def recording_method():
            old_state = info.state
            original()
            self.transitions.append(
                MemoryTransition(
                    sim_time_s=self._router.timeline.now() / SECOND,
                    memory_name=info.memory.name,
                    old_state=old_state,
                    new_state=info.state,
                    responsible=self._responsible,
                )
            )

        return recording_method

    def _wrapped_update(self, protocol, memory, state) -> None:
        previous = self._responsible
        self._responsible = (
            type(protocol).__name__ if protocol is not None
            else "(no protocol - explicit reset, e.g. by an application or a reservation's end-time cleanup)"
        )
        try:
            self._original_update(protocol, memory, state)
        finally:
            self._responsible = previous

    def _wrapped_load(self, rule):
        previous = self._responsible
        self._responsible = f"Rule installation (priority={rule.priority})"
        try:
            return self._original_load(rule)
        finally:
            self._responsible = previous

    def detach(self) -> None:
        self._resource_manager.update = self._original_update
        self._resource_manager.load = self._original_load
        for info in self._resource_manager.memory_manager:
            for method_name in _STATE_METHODS:
                original = self._original_methods.get((id(info), method_name))
                if original is not None:
                    setattr(info, method_name, original)
