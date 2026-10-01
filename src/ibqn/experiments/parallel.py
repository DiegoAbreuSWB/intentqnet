"""Process-parallel trial execution.

With literature-calibrated hardware (docs/parameter_calibration.md) one
trial costs tens of seconds to minutes of wall time (a 1 s reservation
window on 5 km SiV links is ~0.5 M discrete events), so campaigns of
hundreds of trials are impractical sequentially. Trials are independent by
construction - each builds its own `SequenceAdapter`/`Timeline` from a
`TrialIdentity`'s seed, and `sequence.utils.metrics` plus the SeQUeNCe
protocol switches are per-process singletons - so they can run in separate
worker processes with no shared state.

Results are identical to sequential execution trial for trial (same seed ->
same simulation); only the ORDER in which rows reach `trials.csv` changes,
which nothing depends on (`trial_id` is the key, see
docs/campaign_architecture.md). All persistence stays in the parent
process, so the CSV/manifest writers need no locking.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from typing import Any

from .records import TrialIdentity, TrialRecord
from .sweeps import TrialParameters

logger = logging.getLogger(__name__)

MAX_POOL_RESTARTS = 6

NUMERIC_THREAD_VARIABLES = ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS")


def limit_worker_numeric_threads() -> None:
    """Makes the worker processes spawned from now on load numpy/scipy with
    single-threaded BLAS (workers inherit this process's environment).

    The simulator only ever multiplies 4-element vectors, so BLAS threads
    buy nothing - but every process that loads numpy and scipy reserves a
    buffer per BLAS thread, ~1.1 GB of committed memory per worker on a
    16-thread machine versus ~0.2 GB single-threaded (measured). A dozen
    workers then exhaust the commit limit of a 16 GB machine and the OS
    kills one, breaking the pool. A value the user set explicitly wins."""
    for name in NUMERIC_THREAD_VARIABLES:
        os.environ.setdefault(name, "1")


@dataclass(frozen=True)
class TrialJob:
    identity: TrialIdentity
    params: TrialParameters
    project_commit: str | None
    sequence_commit: str | None


@dataclass(frozen=True)
class TrialOutcome:
    """Exactly one of `record` / `error_type` is set."""

    record: TrialRecord | None = None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def failed(self) -> bool:
        return self.error_type is not None


def run_trial_job(job: TrialJob) -> TrialOutcome:
    """Runs one `experiments.runner.execute_trial`, converting an exception
    into a `TrialOutcome` so it crosses the process boundary as data."""
    from .runner import execute_trial  # local import: keeps this module importable by `runner`'s dependents

    try:
        record = execute_trial(
            job.identity, job.params, project_commit=job.project_commit, sequence_commit=job.sequence_commit,
        )
    except Exception as exc:  # noqa: BLE001 - every failure is reported, never swallowed
        return TrialOutcome(error_type=type(exc).__name__, error_message=str(exc))
    return TrialOutcome(record=record)


def _quiet_worker() -> None:
    """Worker-process initializer: keep per-trial INFO logging (thousands of
    lifecycle lines per campaign, interleaved across workers) out of the
    parent's console; warnings and errors still get through."""
    from ..utils.logging import _configure_root

    _configure_root()
    logging.getLogger("ibqn").setLevel(logging.WARNING)


def execute_jobs(
    jobs: Iterable[Any], *, workers: int = 1, job_runner: Callable[[Any], Any] = run_trial_job,
    max_pool_restarts: int = MAX_POOL_RESTARTS,
) -> Iterator[tuple[Any, Any]]:
    """Yields `(job, outcome)` as each job finishes. `workers <= 1` runs the
    jobs inline, in order, in this process (the pre-existing sequential
    behavior). `job_runner` must be a picklable top-level function.

    A worker process that dies (killed by the OS under memory pressure on a
    shared machine, typically) breaks the whole pool: every job still
    running or queued is lost with it. Those jobs are resubmitted to a
    fresh pool with half the workers, up to `max_pool_restarts` times -
    safe because a job is a pure function of its inputs (same seed, same
    simulation), so a rerun reproduces exactly what was lost."""
    jobs = list(jobs)
    if workers <= 1 or len(jobs) <= 1:
        for job in jobs:
            yield job, job_runner(job)
        return

    # "spawn" everywhere (the only start method on Windows): every worker
    # imports SeQUeNCe fresh, so no global switch or metrics state is
    # inherited from the parent.
    context = multiprocessing.get_context("spawn")
    limit_worker_numeric_threads()
    remaining = dict(enumerate(jobs))
    restarts = 0
    while remaining:
        pool = ProcessPoolExecutor(
            max_workers=min(workers, len(remaining)), mp_context=context, initializer=_quiet_worker,
        )
        try:
            futures = {pool.submit(job_runner, job): index for index, job in remaining.items()}
            try:
                for future in as_completed(futures):
                    result = future.result()
                    yield remaining.pop(futures[future]), result
            except BrokenProcessPool:
                restarts += 1
                if restarts > max_pool_restarts:
                    raise
                # results that finished before the pool broke but were not handed out yet
                for future, index in futures.items():
                    if index in remaining and future.done() and not future.cancelled() and future.exception() is None:
                        yield remaining.pop(index), future.result()
                workers = max(1, workers // 2)
                logger.warning(
                    "a worker process died; resubmitting %d unfinished job(s) with %d worker(s) (restart %d/%d)",
                    len(remaining), workers, restarts, max_pool_restarts,
                )
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
