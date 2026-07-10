"""Unit tests for the SeQUeNCe discrete-event kernel (Timeline/Event/Process/EventList).

These tests do not touch any network/hardware code: they exercise the kernel
in isolation, using a plain Python object as the `Process` owner (any object
exposing the named method works as a `Process` owner - see
`sequence/kernel/process.py`, `Process.run` calls `getattr(owner, activation)(...)`).
"""
import pytest

from sequence.kernel.timeline import Timeline
from sequence.kernel.event import Event
from sequence.kernel.process import Process


class Recorder:
    """Minimal Process owner: appends its own name to a shared log when run."""

    def __init__(self, log: list[str]):
        self.log = log

    def record(self, tag: str) -> None:
        self.log.append(tag)


def test_events_execute_in_time_order():
    tl = Timeline(stop_time=10 ** 12)
    log: list[str] = []
    recorder = Recorder(log)

    tl.schedule(Event(300, Process(recorder, "record", ["third"])))
    tl.schedule(Event(100, Process(recorder, "record", ["first"])))
    tl.schedule(Event(200, Process(recorder, "record", ["second"])))

    tl.run()

    assert log == ["first", "second", "third"]
    assert tl.time == 300
    assert tl.run_counter == 3


def test_same_time_events_execute_in_priority_order():
    tl = Timeline(stop_time=10 ** 12)
    log: list[str] = []
    recorder = Recorder(log)

    tl.schedule(Event(500, Process(recorder, "record", ["low_priority"]), priority=5))
    tl.schedule(Event(500, Process(recorder, "record", ["high_priority"]), priority=1))

    tl.run()

    assert log == ["high_priority", "low_priority"]


def test_stop_time_cutoff_prevents_execution():
    tl = Timeline(stop_time=1000)
    log: list[str] = []
    recorder = Recorder(log)

    tl.schedule(Event(500, Process(recorder, "record", ["before_cutoff"])))
    tl.schedule(Event(1500, Process(recorder, "record", ["after_cutoff"])))

    tl.run()

    assert log == ["before_cutoff"]
    assert tl.run_counter == 1
    # the event beyond stop_time is pushed back onto the event list, not discarded
    assert len(tl.events) == 1


def test_removed_event_never_executes():
    tl = Timeline(stop_time=10 ** 12)
    log: list[str] = []
    recorder = Recorder(log)

    kept = Event(100, Process(recorder, "record", ["kept"]))
    removed = Event(50, Process(recorder, "record", ["removed"]))
    tl.schedule(kept)
    tl.schedule(removed)
    tl.remove_event(removed)

    tl.run()

    assert log == ["kept"]


def test_update_event_time_reorders_heap():
    tl = Timeline(stop_time=10 ** 12)
    log: list[str] = []
    recorder = Recorder(log)

    event_a = Event(100, Process(recorder, "record", ["a"]))
    event_b = Event(200, Process(recorder, "record", ["b"]))
    tl.schedule(event_a)
    tl.schedule(event_b)

    # push "b" before "a" by rescheduling it earlier
    tl.update_event_time(event_b, 10)

    tl.run()

    assert log == ["b", "a"]


def test_run_on_empty_event_list_is_a_noop():
    tl = Timeline(stop_time=10 ** 12)
    tl.run()
    assert tl.run_counter == 0
    assert tl.time == 0


@pytest.mark.unit
def test_entities_are_registered_and_initialized():
    from sequence.kernel.entity import Entity

    class DummyEntity(Entity):
        def __init__(self, name, timeline):
            super().__init__(name, timeline)
            self.initialized = False

        def init(self):
            self.initialized = True

    tl = Timeline(stop_time=10 ** 12)
    entity = DummyEntity("dummy", tl)

    assert tl.get_entity_by_name("dummy") is entity
    assert entity.initialized is False

    tl.init()

    assert entity.initialized is True
