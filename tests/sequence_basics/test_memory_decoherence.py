"""Tests for the two decoherence mechanisms of `sequence.components.memory.Memory`
(see docs/sequence_code_analysis.md, section 4.1 "Hardware"):

1. Hard cutoff/expiration: `update_state` schedules an `expire` Event at
   `now + cutoff_ratio * coherence_time` (in ps) when `coherence_time > 0`.
2. Continuous Bell-Diagonal-State (BDS) decoherence: `bds_decohere()`, an
   opt-in analytic Pauli-channel decay applied only when `decoherence_errors`
   is set (default `None` -> no-op).

These tests instantiate `Memory` directly (no full router/topology needed),
since `Memory` is a concrete `Entity` (see `sequence/components/memory.py`).
"""
import pytest

from sequence.kernel.timeline import Timeline
from sequence.kernel.quantum_manager import QuantumManager
from sequence.components.memory import Memory
from sequence.constants import BELL_DIAGONAL_STATE_FORMALISM, SECOND


@pytest.fixture(autouse=True)
def _reset_global_quantum_formalism():
    """`Timeline(formalism=...)` mutates `QuantumManager._global_formalism`,
    a process-wide class attribute (see
    `sequence/kernel/quantum_manager/base.py:48,55-64`) that otherwise leaks
    into every later test in the same pytest session - the same class of
    cross-module state pollution documented for the upstream SeQUeNCe test
    suite in docs/sequence_code_analysis.md, section 0.2."""
    yield
    QuantumManager.clear_active_formalism()


class RecordingObserver:
    def __init__(self):
        self.expired_memories = []

    def memory_expire(self, memory):
        self.expired_memories.append(memory)


@pytest.mark.unit
def test_memory_expires_and_notifies_observers_after_coherence_time():
    tl = Timeline(stop_time=10_000)
    memory = Memory("mem0", tl, fidelity=0.9, frequency=0, efficiency=1,
                     coherence_time=1e-9, wavelength=500)  # 1e-9 s -> 1000 ps
    observer = RecordingObserver()
    memory.attach(observer)

    tl.init()
    memory.update_state([1, 0])
    assert memory.expiration_event is not None

    tl.run()

    assert memory.fidelity == 0
    assert memory.entangled_memory == {"node_id": None, "memo_id": None}
    assert memory.expiration_event is None
    assert observer.expired_memories == [memory]
    assert tl.time == 1000  # cutoff_ratio(=1) * coherence_time(1e-9s) in ps


@pytest.mark.unit
def test_no_expiration_scheduled_with_infinite_coherence_time():
    tl = Timeline(stop_time=10_000)
    memory = Memory("mem0", tl, fidelity=0.9, frequency=0, efficiency=1,
                     coherence_time=-1, wavelength=500)  # default: infinite
    tl.init()
    memory.fidelity = 0.9  # simulate post-entanglement bookkeeping
    memory.update_state([1, 0])

    assert memory.expiration_event is None

    tl.run()

    assert tl.run_counter == 0
    assert memory.fidelity == 0.9  # never reset: no expire() was ever scheduled/called


@pytest.mark.unit
def test_update_expire_time_reschedules_expiration():
    tl = Timeline(stop_time=100_000)
    memory = Memory("mem0", tl, fidelity=0.9, frequency=0, efficiency=1,
                     coherence_time=1e-9, wavelength=500)
    tl.init()
    memory.update_state([1, 0])
    assert memory.get_expire_time() == 1000

    memory.update_expire_time(5000)
    assert memory.get_expire_time() == 5000

    tl.run()

    assert tl.time == 5000
    assert memory.fidelity == 0


@pytest.mark.unit
def test_bds_decohere_is_noop_without_decoherence_errors():
    # QuantumManagerBellDiagonal.set() requires exactly 2 keys (an entangled
    # pair) - a Bell diagonal state cannot exist for a single, unentangled key
    # (sequence/kernel/quantum_manager/bell_diagonal.py:48-63).
    tl = Timeline(stop_time=10 ** 12, formalism=BELL_DIAGONAL_STATE_FORMALISM)
    memory = Memory("mem0", tl, fidelity=0.9, frequency=0, efficiency=1,
                     coherence_time=-1, wavelength=500)  # decoherence_errors=None by default
    remote_memory = Memory("mem1", tl, fidelity=0.9, frequency=0, efficiency=1,
                            coherence_time=-1, wavelength=500)
    tl.init()

    initial_fidelity = 0.9
    tl.quantum_manager.set([memory.qstate_key, remote_memory.qstate_key],
                            [initial_fidelity, (1 - initial_fidelity) / 3,
                             (1 - initial_fidelity) / 3, (1 - initial_fidelity) / 3])
    memory.last_update_time = 0
    tl.time = 5 * SECOND

    memory.bds_decohere()

    assert memory.get_bds_fidelity() == pytest.approx(initial_fidelity)


@pytest.mark.unit
def test_bds_decohere_reduces_fidelity_monotonically_over_time():
    # coherence_time must be > 0 for `decoherence_rate` to be nonzero
    # (memory.py: `decoherence_rate = 1/coherence_time if coherence_time > 0 else 0`).
    # `bds_decohere()` is called directly here (never via `update_state`), so no
    # cutoff/expiration Event is scheduled despite the finite coherence_time.
    tl = Timeline(stop_time=10 ** 12, formalism=BELL_DIAGONAL_STATE_FORMALISM)
    memory = Memory("mem0", tl, fidelity=0.9, frequency=0, efficiency=1,
                     coherence_time=10, wavelength=500, decoherence_errors=[1 / 3, 1 / 3, 1 / 3])
    remote_memory = Memory("mem1", tl, fidelity=0.9, frequency=0, efficiency=1,
                            coherence_time=-1, wavelength=500)
    tl.init()

    initial_fidelity = 0.9
    tl.quantum_manager.set([memory.qstate_key, remote_memory.qstate_key],
                            [initial_fidelity, (1 - initial_fidelity) / 3,
                             (1 - initial_fidelity) / 3, (1 - initial_fidelity) / 3])
    # NOTE: `bds_decohere()` only applies decay when `self.last_update_time > 0`
    # (strictly), treating 0 the same as the "unset" sentinel -1
    # (memory.py:387) - so the baseline reference must be a positive time.
    memory.last_update_time = 1 * SECOND

    # calling with no elapsed time since the baseline must be a no-op
    tl.time = 1 * SECOND
    memory.bds_decohere()
    assert memory.get_bds_fidelity() == pytest.approx(initial_fidelity)

    # advancing time must strictly reduce fidelity toward the maximally-mixed
    # state (1/4), and last_update_time must track the call time
    tl.time = 2 * SECOND
    memory.bds_decohere()
    fidelity_after_1s = memory.get_bds_fidelity()
    assert fidelity_after_1s < initial_fidelity
    assert memory.last_update_time == 2 * SECOND

    tl.time = 11 * SECOND
    memory.bds_decohere()
    fidelity_after_10s = memory.get_bds_fidelity()
    assert fidelity_after_10s < fidelity_after_1s
    assert fidelity_after_10s >= 0.25 - 1e-9  # Bell-diagonal states never go below the maximally mixed fidelity 1/4
