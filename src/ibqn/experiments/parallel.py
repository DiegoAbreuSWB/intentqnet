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
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any

from .records import TrialIdentity, TrialRecord
from .sweeps import TrialParameters


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
) -> Iterator[tuple[Any, Any]]:
    """Yields `(job, outcome)` as each job finishes. `workers <= 1` runs the
    jobs inline, in order, in this process (the pre-existing sequential
    behavior). `job_runner` must be a picklable top-level function."""
    jobs = list(jobs)
    if workers <= 1 or len(jobs) <= 1:
        for job in jobs:
            yield job, job_runner(job)
        return

    # "spawn" everywhere (the only start method on Windows): every worker
    # imports SeQUeNCe fresh, so no global switch or metrics state is
    # inherited from the parent.
    context = multiprocessing.get_context("spawn")
    pool = ProcessPoolExecutor(max_workers=min(workers, len(jobs)), mp_context=context, initializer=_quiet_worker)
    try:
        futures = {pool.submit(job_runner, job): job for job in jobs}
        for future in as_completed(futures):
            yield futures[future], future.result()
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
