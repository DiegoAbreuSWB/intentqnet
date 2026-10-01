"""R00b - integrity audit of the Bell-diagonal pair states
(docs/physical_model.md, "Desvios em relacao ao SeQUeNCe de fabrica").

The two ends of a pair learn a protocol's outcome at different times, so
one end can consume its half while the other still holds its own. This
audit runs representative reservations and classifies, for every
`Memory.bds_decohere` call, every swap input and every purification input,
whether the memory's entry in the quantum manager still describes a pair
both ends hold:

  ok               both keys of the pair map to the same state object
  reset_noop       memory reset, no state, last_update_time <= 0 (stock no-op)
  no_state         no state but last_update_time > 0 (stock SeQUeNCe: KeyError)
  stale_recreate   the partner key has no state (stock: re-creates one for it)
  stale_overwrite  the partner key holds ANOTHER pair (stock: overwrites it)

What the patched simulator must show: swaps and purification rounds only
ever consume `ok` pairs, and no dangling state is left at the end of a run.

Writes results/realistic/audit/state_integrity_audit.csv.
Run: python scripts/realistic/audit_state_integrity.py [workers] [seeds]
"""
from __future__ import annotations

import sys
import traceback
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.experiments.parallel import execute_jobs  # noqa: E402

OUT = PROJECT_ROOT / "results" / "realistic" / "audit" / "state_integrity_audit.csv"
CLASSES = ("ok", "reset_noop", "no_state", "stale_recreate", "stale_overwrite")

CASES = [
    # topology, hardware, route, target fidelity, purification mode, window (s), coherence-time override (s)
    ("diamond", "theoretical_ops", ["r1", "good1", "good2", "r3"], 0.65, "until_target", 0.3, None),
    ("diamond", "theoretical_ops", ["r1", "good1", "good2", "r3"], 0.60, "never", 0.3, None),
    ("diamond", "literature", ["r1", "bad", "r3"], 0.60, "never", 0.5, None),
    ("chain1", "theoretical_ops", ["a", "r1", "b"], 0.78, "until_target", 0.3, None),
    ("chain1", "theoretical_ops", ["a", "r1", "b"], 0.78, "once", 0.3, None),
    ("chain1", "literature", ["a", "r1", "b"], 0.70, "never", 0.3, None),
    ("chain2", "theoretical_ops", ["a", "r1", "r2", "b"], 0.68, "until_target", 0.3, None),
    ("chain2", "theoretical_ops", ["a", "r1", "r2", "b"], 0.70, "until_target", 0.3, None),
    ("chain2", "literature", ["a", "r1", "r2", "b"], 0.55, "never", 0.3, None),
    # short memories: the cutoff expires pairs all the time
    ("chain2", "theoretical_ops", ["a", "r1", "r2", "b"], 0.66, "until_target", 0.3, 0.02),
    ("chain1", "theoretical_ops", ["a", "r1", "b"], 0.75, "until_target", 0.3, 0.005),
    ("mesh", "theoretical_ops", ["a0", "a1", "a2", "b2"], 0.67, "until_target", 0.3, None),
    ("mesh", "theoretical_ops", ["a0", "a1", "a2", "a3", "b3"], 0.60, "until_target", 0.3, None),
]


def classify(memory) -> str:
    states = memory.timeline.quantum_manager.states
    state = states.get(memory.qstate_key)
    if state is None:
        return "no_state" if memory.last_update_time > 0 else "reset_noop"
    for key in state.keys:
        if key == memory.qstate_key:
            continue
        other = states.get(key)
        if other is None:
            return "stale_recreate"
        if other is not state:
            return "stale_overwrite"
    return "ok"


def run_integrity_job(job: dict) -> dict:
    """One audited reservation. Instruments SeQUeNCe in this process only
    (the wrappers are removed before returning)."""
    from sequence.components.memory import Memory
    from sequence.entanglement_management.purification.bbpssw_bds import BBPSSW_BDS
    from sequence.entanglement_management.swapping.swapping_bds import EntanglementSwappingA_BDS
    from sequence.utils import metrics

    from ibqn.assurance.telemetry import collect_intent_evidence
    from ibqn.execution.sequence_executor import SequenceExecutor
    from ibqn.experiments.realistic_suite import HARDWARE, STOP_MARGIN_S, WINDOW_START_S, build_intent
    from ibqn.experiments.realistic_topologies import realistic_chain, realistic_diamond, realistic_mesh
    from ibqn.intent.repository import IntentRepository
    from ibqn.network import sequence_patches
    from ibqn.network.platforms import resolve_platform
    from ibqn.network.sequence_adapter import SequenceAdapter
    from ibqn.planning.models import ExecutionPlan

    topology, hardware, route, target, mode, duration, coherence = job["case"]
    platform = resolve_platform(HARDWARE[hardware])
    if coherence is not None:
        platform = replace(platform, coherence_time_s=coherence)
    stop = WINDOW_START_S + duration + STOP_MARGIN_S
    if topology.startswith("chain"):
        spec = realistic_chain(int(topology[5:]), platform=platform, stop_time_s=stop)
    else:
        spec = {"diamond": realistic_diamond, "mesh": realistic_mesh}[topology](platform=platform, stop_time_s=stop)

    decohere, decohere_callers, swap_inputs, purification_inputs = Counter(), Counter(), Counter(), Counter()
    stock_swap_start, stock_purification_start = EntanglementSwappingA_BDS.start, BBPSSW_BDS.start

    def monitored_decohere(memory):
        kind = classify(memory)
        decohere[kind] += 1
        if kind not in ("ok", "reset_noop"):
            frame = [f for f in traceback.extract_stack()[:-1] if "sequence" in f.filename.replace("\\", "/")][-1]
            decohere_callers[f"{kind}@{Path(frame.filename).name}:{frame.name}"] += 1
        sequence_patches.ibqn_bds_decohere(memory)

    def monitored_swap_start(protocol):
        for memory in (protocol.left_memo, protocol.right_memo):
            swap_inputs[classify(memory)] += 1
        stock_swap_start(protocol)

    def monitored_purification_start(protocol):
        remote = [protocol.owner.timeline.get_entity_by_name(name) for name in protocol.remote_memories]
        for memory in (protocol.kept_memo, protocol.meas_memo, *remote):
            purification_inputs[classify(memory)] += 1
        stock_purification_start(protocol)

    combo = dict(min_fidelity=target, reserved_memory_slots=4, min_delivered_pairs=1, duration_s=duration,
                 allow_purification=mode != "never")
    intent = build_intent("integrity", route[0], route[-1], combo)
    metrics.configure()
    metrics.reset_metrics()
    adapter = SequenceAdapter(spec, seed=job["seed"])
    Memory.bds_decohere = monitored_decohere
    EntanglementSwappingA_BDS.start = monitored_swap_start
    BBPSSW_BDS.start = monitored_purification_start
    error = None
    try:
        executor = SequenceExecutor(adapter, IntentRepository())
        executor.deploy(intent, ExecutionPlan(intent_id=intent.id, feasible=True, route=route, purification_mode=mode))
        executor.run()
    except Exception as exc:  # noqa: BLE001 - an aborted simulation is itself an audit finding
        error = f"{type(exc).__name__}: {exc}"
    finally:
        Memory.bds_decohere = sequence_patches.ibqn_bds_decohere
        EntanglementSwappingA_BDS.start = stock_swap_start
        BBPSSW_BDS.start = stock_purification_start

    evidence = collect_intent_evidence(intent)
    events = Counter(record["event_type"].name for record in metrics.storage.get_all())
    states = adapter.get_timeline().quantum_manager.states
    fidelities = [pair.fidelity for pair in evidence.delivered_pairs]
    row = dict(
        topology=topology, hardware=hardware, route="->".join(route), min_fidelity=target, purification_mode=mode,
        duration_s=duration, coherence_time_s=coherence if coherence is not None else platform.coherence_time_s,
        seed=job["seed"], error=error, delivered_pairs=len(fidelities),
        mean_fidelity=sum(fidelities) / len(fidelities) if fidelities else None,
        discarded_pairs=evidence.discarded_pairs, swaps=events["ES_SUCCESS"],
        purification_successes=events["EP_SUCCESS"], purification_failures=events["EP_FAILURE"],
        dangling_states_at_end=sum(1 for state in states.values() if any(states.get(k) is not state for k in state.keys)),
        decohere_callers="; ".join(f"{name} x{count}" for name, count in sorted(decohere_callers.items())),
    )
    for kind in CLASSES:
        row[f"decohere_{kind}"] = decohere[kind]
        row[f"swap_input_{kind}"] = swap_inputs[kind]
        row[f"purification_input_{kind}"] = purification_inputs[kind]
    return row


def main() -> None:
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    jobs = [dict(case=case, seed=seed) for case in CASES for seed in range(seeds)]
    rows = []
    for i, (job, row) in enumerate(execute_jobs(jobs, workers=workers, job_runner=run_integrity_job), start=1):
        rows.append(row)
        print(f"[{i}/{len(jobs)}] {row['topology']}@{row['hardware']} {row['route']} {row['purification_mode']} "
              f"seed={row['seed']}: delivered={row['delivered_pairs']} error={row['error']}", flush=True)
    frame = pd.DataFrame(rows).sort_values(
        ["topology", "hardware", "route", "min_fidelity", "purification_mode", "coherence_time_s", "seed"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(OUT, index=False)

    def total(prefix: str) -> dict:
        return {kind: int(frame[f"{prefix}_{kind}"].sum()) for kind in CLASSES}

    print(f"\n{len(frame)} runs, {int(frame['error'].notna().sum())} aborted, "
          f"{int(frame['dangling_states_at_end'].sum())} dangling states at end of run")
    print("decoherence calls   :", total("decohere"))
    print("swap inputs         :", total("swap_input"))
    print("purification inputs :", total("purification_input"))
    callers = Counter()
    for text in frame["decohere_callers"].dropna():
        for part in filter(None, text.split("; ")):
            name, count = part.rsplit(" x", 1)
            callers[name] += int(count)
    for name, count in callers.most_common():
        print(f"   {count:6d}  {name}")


if __name__ == "__main__":
    main()
