"""M10.8: tail-event diagnostic instrumentation. Distinguishes three
hypotheses for the ~48723s P02B outlier (section 13 of the governing
brief) - (1) a legitimate stochastic tail event, (2) an RNG/replay
problem, (3) a bug/loop/pathological condition - by periodically sampling
SeQUeNCe's `Timeline` (read-only, composition-safe; never modifies
SeQUeNCe) WHILE a trial's simulation is running, from a background
daemon thread that runs concurrently with the main thread's blocking
`executor.run()` call (Python's GIL is released periodically during
normal bytecode execution, letting the watcher thread sample and write
a heartbeat even while the main thread is deep inside SeQUeNCe's
discrete-event loop).

Samples, per heartbeat:
- `sim_time_s` (`Timeline.now()` / SECOND) - is SIMULATED time advancing?
- `run_counter` (`Timeline.run_counter`) - cumulative events actually
  processed - is REAL event-processing work happening?
- `pending_events` (`len(Timeline.events)`) - is the event QUEUE growing
  faster than it drains (a sign of a runaway rescheduling loop)?

Written incrementally to a JSONL file so the trail survives even if the
OS-level subprocess timeout (predictability_m10_common.run_trial_with_
timeout) kills the process mid-simulation - post-mortem classification
reads whatever heartbeats were flushed before death.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from sequence.constants import SECOND


@dataclass
class HeartbeatSample:
    wall_elapsed_s: float
    sim_time_s: float
    run_counter: int
    pending_events: int


class HeartbeatMonitor:
    """Usage: `with HeartbeatMonitor(timeline, path, interval_s=2.0,
    max_events=...): ... executor.run() ...` - samples are flushed to
    `path` (JSONL) as they are taken, not buffered only in memory, so a
    killed process still leaves a usable trail.

    If `max_events` is set and `Timeline.run_counter` exceeds it, this
    monitor writes a final heartbeat marked `event_limit_exceeded: true`
    and calls `os._exit(1)` - the ONLY reliable way to stop a runaway
    simulation from a background thread in Python, since the main thread
    is blocked inside SeQUeNCe's synchronous event loop and cannot be
    cooperatively interrupted (this project already relies on an
    external subprocess-level wall-clock kill for the same reason -
    running inside an isolated subprocess is what makes this abrupt
    self-termination safe: it never corrupts shared state outside this
    one trial's process)."""

    def __init__(self, timeline, heartbeat_path: str | Path, interval_s: float = 2.0, max_events: int | None = None):
        self._timeline = timeline
        self._path = Path(heartbeat_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._interval_s = interval_s
        self._max_events = max_events
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0 = time.perf_counter()

    def _run(self) -> None:
        import os

        with open(self._path, "w", encoding="utf-8") as f:
            while not self._stop_event.wait(self._interval_s):
                run_counter = self._timeline.run_counter
                limit_exceeded = self._max_events is not None and run_counter > self._max_events
                sample = {
                    **asdict(HeartbeatSample(
                        wall_elapsed_s=round(time.perf_counter() - self._t0, 3),
                        sim_time_s=self._timeline.now() / SECOND,
                        run_counter=run_counter,
                        pending_events=len(self._timeline.events),
                    )),
                    "event_limit_exceeded": limit_exceeded,
                }
                f.write(json.dumps(sample) + "\n")
                f.flush()
                if limit_exceeded:
                    os._exit(1)

    def __enter__(self) -> "HeartbeatMonitor":
        self._t0 = time.perf_counter()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval_s + 1.0)


def read_heartbeats(heartbeat_path: str | Path) -> list[dict]:
    path = Path(heartbeat_path)
    if not path.exists():
        return []
    samples = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    samples.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # a partially-written last line from a killed process - ignore, not a crash
    return samples


NO_PROGRESS_STALL_SAMPLES = 3
"""How many consecutive heartbeats with an unchanged `run_counter` before
classifying a trial as NO_PROGRESS - one stalled sample alone could just
be a slow-but-real single event; a documented threshold, not a random
choice."""


def classify_termination(heartbeat_path: str | Path, *, final_status: str, timed_out: bool) -> str:
    """One of TIMEOUT, NO_PROGRESS, MAX_RETRIES, SIMULATION_COMPLETE,
    ERROR (section 13's exact vocabulary - never silently turned into a
    SATISFIED/VIOLATED verdict when a safety limit fired). Whether the
    event limit was exceeded is read directly from the heartbeat trail
    (the last sample's `event_limit_exceeded` flag), not passed in
    separately - the trial process self-terminates the instant that
    happens (see `HeartbeatMonitor._run`), so the flag and the process's
    death are the same event."""
    if final_status == "SIMULATION_ERROR":
        return "ERROR"

    samples = read_heartbeats(heartbeat_path)
    if samples and samples[-1].get("event_limit_exceeded"):
        return "MAX_RETRIES"
    if timed_out:
        if len(samples) >= NO_PROGRESS_STALL_SAMPLES:
            recent = samples[-NO_PROGRESS_STALL_SAMPLES:]
            if len({s["run_counter"] for s in recent}) == 1:
                return "NO_PROGRESS"
        return "TIMEOUT"
    if final_status in ("SATISFIED", "VIOLATED"):
        return "SIMULATION_COMPLETE"
    return "TIMEOUT" if timed_out else "SIMULATION_COMPLETE"
