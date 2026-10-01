"""Measures how fast a calibrated network actually generates entanglement,
so the planners' generation models can be fitted to - and checked against -
the simulator instead of assumed (docs/generation_model_audit.md).

The pre-revision audit (docs/l3_attempt_rate_audit.md) did this for the
legacy Barrett-Kok protocol from frozen campaign data. Under the
Bell-diagonal model generation is single-heralded with realistic emission/
detection efficiencies, so per-attempt success is ~1e-3 instead of ~0.5,
links complete at different times and wait in memory, and both the attempt
cycle and the end-to-end rate law change. One job here runs one linear
chain with purification disabled and a fidelity target low enough that
every swap proceeds, and reports per-node generation counters and
end-to-end deliveries.
"""
from __future__ import annotations

import time
from collections import Counter

from sequence.utils import metrics
from sequence.utils.metrics.event_types import EventTypes

from ..demos.intents import simple_intent
from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import SuccessCondition
from ..intent.repository import IntentRepository
from ..network.platforms import resolve_platform
from ..network.sequence_adapter import SequenceAdapter
from ..planning.models import ExecutionPlan
from .realistic_topologies import realistic_chain

WINDOW_START_S = 0.01


def run_generation_audit_job(job: dict) -> dict:
    """`job` keys: platform, n_repeaters, link_m, slots, duration_s, seed,
    min_fidelity, [reverse]. `reverse` runs the reservation from `b` to `a`
    over the same chain, which swaps which end of every link requests the
    pairing (the attempt cycle depends on it - `generation_models.
    single_heralded_cycle_factor`). Returns `job` plus measured counters.
    Top-level and dict-in/dict-out so it can run in a worker process
    (`experiments.parallel.execute_jobs`)."""
    platform = resolve_platform(job["platform"])
    slots = job["slots"]
    spec = realistic_chain(
        job["n_repeaters"], platform=platform, link_m=job["link_m"],
        end_memories=slots, repeater_memories=2 * slots, stop_time_s=WINDOW_START_S + job["duration_s"] + 0.01,
    )
    route = [node.id for node in spec.nodes]
    if job.get("reverse", False):
        route = route[::-1]

    metrics.configure()
    metrics.reset_metrics()
    adapter = SequenceAdapter(spec, seed=job["seed"])
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    intent = simple_intent(
        intent_id="generation-audit", source=route[0], destination=route[-1], min_fidelity=job["min_fidelity"],
        requested_pairs=slots, start_time=WINDOW_START_S, duration=job["duration_s"],
        success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=1)],
    )
    plan = ExecutionPlan(intent_id=intent.id, feasible=True, route=route, purification_mode="never")
    executor.deploy(intent, plan)
    t0 = time.perf_counter()
    executor.run()
    wall_time_s = time.perf_counter() - t0

    successes: Counter[str] = Counter()
    failures: Counter[str] = Counter()
    swaps: Counter[str] = Counter()
    fidelities: list[float] = []
    delivery_times_s: list[float] = []
    for record in metrics.storage.get_all():
        event, owner = record["event_type"], record["owner_name"]
        if event is EventTypes.EG_SUCCESS:
            successes[owner] += 1
        elif event is EventTypes.EG_FAILURE:
            failures[owner] += 1
        elif event is EventTypes.ES_SUCCESS:
            swaps[owner] += 1
        elif event is EventTypes.DELIVERY:
            fidelities.append(record["fidelity"])
            delivery_times_s.append(record["sim_time"] * 1e-12 - WINDOW_START_S)
    half = job["duration_s"] / 2

    source, destination = route[0], route[-1]
    result = dict(job)
    result.update(
        reverse=bool(job.get("reverse", False)), route="->".join(route),
        status=repository.get(intent.id).lifecycle.status.value,
        hops=len(route) - 1,
        classical_delay_s=spec.classical_delay_between(route[0], route[1]),
        # endpoints own exactly one link, so their counters are that link's
        first_link_attempts=successes[source] + failures[source], first_link_successes=successes[source],
        last_link_attempts=successes[destination] + failures[destination], last_link_successes=successes[destination],
        total_generation_events=sum(successes.values()) + sum(failures.values()),
        total_generation_successes=sum(successes.values()),
        swaps=sum(swaps.values()),
        delivered_pairs=len(fidelities),
        # start-up transient: the window opens on empty memories
        first_delivery_s=min(delivery_times_s) if delivery_times_s else None,
        delivered_second_half=sum(1 for t in delivery_times_s if t >= half),
        mean_fidelity=(sum(fidelities) / len(fidelities)) if fidelities else None,
        events=adapter.get_timeline().run_counter, wall_time_s=round(wall_time_s, 3),
    )
    return result
