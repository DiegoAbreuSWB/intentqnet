"""Job runners for the calibrated ("realistic") campaign suite
(`scripts/realistic/`, results under `results/realistic/`).

Every campaign in the suite runs under TWO hardware conditions
(docs/parameter_calibration.md):

- `literature`      -> platform `siv_2024`: every parameter demonstrated.
- `theoretical_ops` -> platform `siv_2024_theoretical_ops`: the same link
  fidelity, efficiency, memory and fiber, but ideal gates and measurements,
  so BBPSSW purification behaves as in the textbook.

Each runner is a top-level function taking and returning plain dicts, so it
can execute in a worker process (`experiments.parallel.execute_jobs`). The
reconciliation, baseline, overhead and multi-intent runners are ports of
the logic the original ad-hoc scripts (`scripts/run_f01_*`, `run_f05_*`,
`run_f06_*`, `run_concurrent_intent_campaign.py`) carried inline, with the
topology/intent construction replaced by the calibrated builders - the
measurement logic itself is unchanged.
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
from sequence.utils import metrics

from ..assurance.evaluator import evaluate_intent
from ..assurance.reconciliation import reconcile
from ..assurance.reconciliation_policy import apply_reconciliation_decision, decide_reconciliation_action
from ..assurance.telemetry import collect_intent_evidence
from ..assurance.violations import classify_violations
from ..demos.intents import simple_intent
from ..execution.sequence_executor import SequenceExecutor
from ..intent.models import EntanglementIntent, IntentStatus, SuccessCondition
from ..intent.repository import IntentRepository
from ..network.capabilities import NetworkCapabilities
from ..network.platforms import resolve_platform
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import NetworkTopologySpec
from ..planning.planner import IntentPlanner
from ..planning.planners import (
    BufferedResourceAwarePlanner,
    ConservativeOneRoundPlanner,
    IterativeAnalyticalPlanner,
    PlanningContext,
    ProbabilisticBufferedPlanner,
    ProbabilisticPlanner,
    ProbabilisticResourceAwarePlanner,
    ResourceAwareIterativePlanner,
    SimulationInTheLoopPlanner,
    SimulationPlannerConfig,
    generate_candidate_paths,
)
from ..planning.routing import ShortestHopCountRouting
from .baselines import run_native_sequence_baseline, run_offline_oracle_baseline, run_static_provisioning_baseline
from .manifests import replace_with_retry
from .overhead import run_instrumented_trial
from .parallel import execute_jobs
from .planner_study_runner import execute_trial_with_policy
from .realistic_topologies import realistic_chain, realistic_diamond, realistic_mesh, realistic_star
from .records import TrialIdentity
from .runner import execute_trial
from .sweeps import TrialParameters, compute_parameter_hash

HARDWARE: dict[str, str] = {
    "literature": "siv_2024",
    "theoretical_ops": "siv_2024_theoretical_ops",
}
"""Hardware condition -> platform profile name."""

WINDOW_START_S = 0.01
STOP_MARGIN_S = 0.02
RECONCILIATION_SEED_OFFSET = 1_000_000
ORACLE_SEED_OFFSET = 7_000_000
L3_FAMILY_COLLECTION_THRESHOLD = 0.0
"""The L3 family admits at threshold 0 during collection, exactly as P02b
did: every trial then carries BOTH the planner's predicted satisfaction
probability and the real outcome, and admission thresholds are applied post
hoc in analysis (never tuned on the test seeds)."""


# --------------------------------------------------------------------------
# builders
# --------------------------------------------------------------------------

def build_topology(name: str, hardware: str, *, duration_s: float, **kwargs: Any) -> NetworkTopologySpec:
    """`name`: `chain<N>` (N repeaters), `diamond`, `mesh` or `star`.
    `duration_s`: the longest reservation window the topology must outlive."""
    platform = resolve_platform(HARDWARE[hardware])
    stop_time_s = WINDOW_START_S + duration_s + STOP_MARGIN_S
    if name.startswith("chain"):
        return realistic_chain(int(name[len("chain"):]), platform=platform, stop_time_s=stop_time_s, **kwargs)
    builders: dict[str, Callable[..., NetworkTopologySpec]] = {
        "diamond": realistic_diamond, "mesh": realistic_mesh, "star": realistic_star,
    }
    try:
        builder = builders[name]
    except KeyError:
        raise ValueError(f"unknown topology {name!r} - supported: chain<N>, {sorted(builders)}") from None
    return builder(platform=platform, stop_time_s=stop_time_s, **kwargs)


def build_intent(
    intent_id: str, source: str, destination: str, combo: dict, *, check_fidelity: bool = True,
) -> EntanglementIntent:
    """An intent whose success conditions are exactly its declared service
    goals: `delivered_pairs >= min_delivered_pairs` and (unless
    `check_fidelity` is off) `average_fidelity >= min_fidelity`. (The legacy
    campaigns inherited `simple_intent`'s default, which compares delivered
    pairs against the reserved slot count instead.)"""
    conditions = [SuccessCondition(metric="delivered_pairs", operator=">=", expected=combo["min_delivered_pairs"])]
    if check_fidelity:
        conditions.append(SuccessCondition(metric="average_fidelity", operator=">=", expected=combo["min_fidelity"]))
    return simple_intent(
        intent_id=intent_id, source=source, destination=destination, min_fidelity=combo["min_fidelity"],
        requested_pairs=combo["reserved_memory_slots"], min_delivered_pairs=combo["min_delivered_pairs"],
        start_time=WINDOW_START_S, duration=combo["duration_s"],
        allow_purification=combo.get("allow_purification", True), success_conditions=conditions,
    )


def make_planner(level: str, *, l4_simulations: int = 3):
    factories: dict[str, Callable[[], Any]] = {
        "L1": ConservativeOneRoundPlanner,
        "L2": IterativeAnalyticalPlanner,
        "L2-R": ResourceAwareIterativePlanner,
        "L2-RB": BufferedResourceAwarePlanner,
        "L3": lambda: ProbabilisticPlanner(admission_threshold=L3_FAMILY_COLLECTION_THRESHOLD),
        "L3-R": lambda: ProbabilisticResourceAwarePlanner(admission_threshold=L3_FAMILY_COLLECTION_THRESHOLD),
        "L3-RB": lambda: ProbabilisticBufferedPlanner(admission_threshold=L3_FAMILY_COLLECTION_THRESHOLD),
        "L4": lambda: SimulationInTheLoopPlanner(
            config=SimulationPlannerConfig(simulations_per_candidate=l4_simulations), admission_threshold=0.5,
        ),
    }
    try:
        return factories[level]()
    except KeyError:
        raise ValueError(f"unknown planner level {level!r} - supported: {sorted(factories)}") from None


def _evidence_summary(intent: EntanglementIntent) -> tuple[int, float | None]:
    evidence = collect_intent_evidence(intent)
    delivered = len(evidence.delivered_pairs)
    average = sum(p.fidelity for p in evidence.delivered_pairs) / delivered if delivered else None
    return delivered, average


# --------------------------------------------------------------------------
# persistence / orchestration shared by the suite's scripts
# --------------------------------------------------------------------------

def run_jobs_to_csv(
    jobs: Iterable[dict], job_runner: Callable[[dict], Any], out_csv: str | Path, *,
    key: Callable[[dict], str], workers: int, describe: Callable[[dict, dict], str] | None = None,
    checkpoint_every: int = 40,
) -> pd.DataFrame:
    """Runs `jobs` (skipping any whose `key` is already in `out_csv`). A job
    returns one row (a dict) or several (a list of dicts); every row is
    tagged with its job's key under `job_key`. Rows are rewritten to
    `out_csv` every `checkpoint_every` completions and at the end, so an
    interrupted campaign resumes where it stopped. `describe(job, result)`
    receives exactly what the job returned."""
    out_csv = Path(out_csv)
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    done: set[str] = set()
    if out_csv.exists() and out_csv.stat().st_size > 0:
        existing = pd.read_csv(out_csv)
        rows = existing.to_dict("records")
        done = set(existing["job_key"].astype(str))
    pending = []
    for job in jobs:
        job = dict(job)
        job["job_key"] = key(job)
        if job["job_key"] not in done:
            pending.append(job)
    total = len(pending)
    print(f"{out_csv.name}: {total} job(s) to run, {len(done)} already done", flush=True)
    try:
        for i, (job, result) in enumerate(execute_jobs(pending, workers=workers, job_runner=job_runner), start=1):
            for row in (result if isinstance(result, list) else [result]):
                rows.append(dict(row, job_key=job["job_key"]))
            if describe is not None:
                print(f"[{i}/{total}] {describe(job, result)}", flush=True)
            if i % checkpoint_every == 0:
                _write_csv(rows, out_csv)
    finally:  # an interrupted or crashed campaign keeps every row it finished
        if rows:
            _write_csv(rows, out_csv)
    return pd.DataFrame(rows)


def _write_csv(rows: list[dict], out_csv: Path) -> None:
    """Rewrites `out_csv` through a temporary file, so a checkpoint is never
    half-written and a transient lock on the file (see
    `manifests.replace_with_retry`) does not abort the campaign."""
    tmp = out_csv.with_suffix(out_csv.suffix + ".tmp")
    pd.DataFrame(rows).to_csv(tmp, index=False)
    replace_with_retry(tmp, out_csv)


# --------------------------------------------------------------------------
# planner study
# --------------------------------------------------------------------------

def run_planner_case_job(job: dict) -> list[dict]:
    """Every planner level in `job["planner_levels"]` on ONE case (topology,
    hardware, intent, seed): one trial row per level. The levels share an
    execution cache, so levels that choose the same route and purification
    mode share a single simulation (`execute_trial_with_policy`). `job`
    keys: campaign, topology, hardware, planner_levels, seed, regime,
    combo, source, destination, project_commit, sequence_commit,
    [topology_kwargs], [l4_simulations]."""
    combo = job["combo"]
    spec = build_topology(job["topology"], job["hardware"], duration_s=combo["duration_s"], **job.get("topology_kwargs", {}))
    intent = build_intent(f"{job['campaign']}-intent", job["source"], job["destination"], combo)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting(), topology_spec=spec)
    execution_cache: dict = {}
    rows = []
    for level in job["planner_levels"]:
        policy = make_planner(level, l4_simulations=job.get("l4_simulations", 3))
        identity = TrialIdentity(
            campaign=job["campaign"], scenario=f"{job['topology']}@{job['hardware']}",
            parameter_hash=compute_parameter_hash(combo), strategy=level, seed=job["seed"], intent_id=intent.id,
        )
        record = execute_trial_with_policy(
            identity, intent, spec, policy, context, project_commit=job.get("project_commit"),
            sequence_commit=job.get("sequence_commit"), regime=job.get("regime"), execution_cache=execution_cache,
        )
        rows.append(dict(asdict(record), topology=job["topology"], hardware=job["hardware"]))
    return rows


def run_oracle_job(job: dict) -> dict:
    """Offline-oracle re-simulation of one planner-REJECTED trial: is the
    intent satisfiable on ANY simple path? Same topology/intent as the
    rejected trial, a disjoint seed. `job` keys: trial_id, planner_level,
    topology, hardware, seed, regime, combo, source, destination."""
    combo = job["combo"]
    spec = build_topology(job["topology"], job["hardware"], duration_s=combo["duration_s"], **job.get("topology_kwargs", {}))
    intent = build_intent(f"oracle-{job['planner_level']}-{job['seed']}", job["source"], job["destination"], combo)
    oracle_seed = job["seed"] + ORACLE_SEED_OFFSET
    base = dict(
        trial_id=job["trial_id"], planner_level=job["planner_level"], topology=job["topology"],
        hardware=job["hardware"], scenario=f"{job['topology']}@{job['hardware']}", seed=job["seed"],
        regime=job.get("regime"), oracle_seed=oracle_seed, requested_fidelity=combo["min_fidelity"],
        duration_s=combo["duration_s"], reserved_memory_slots=combo["reserved_memory_slots"],
        min_delivered_pairs=combo["min_delivered_pairs"], allow_purification=combo.get("allow_purification", True),
    )
    t0 = time.perf_counter()
    try:
        result = run_offline_oracle_baseline(spec, intent, seed=oracle_seed, max_candidates=job.get("max_candidates", 10))
    except ValueError as exc:  # more simple paths than the oracle enumerates
        return dict(base, oracle_tested=False, oracle_satisfiable=None, oracle_route=None, oracle_delivered_pairs=None,
                    oracle_average_fidelity=None, oracle_notes=f"oracle not computable: {exc}",
                    oracle_wall_time_s=round(time.perf_counter() - t0, 3))
    except Exception as exc:  # noqa: BLE001 - a candidate route the simulator itself refuses mid-run
        return dict(base, oracle_tested=False, oracle_satisfiable=None, oracle_route=None, oracle_delivered_pairs=None,
                    oracle_average_fidelity=None, oracle_notes=f"oracle simulation error: {type(exc).__name__}: {exc}",
                    oracle_wall_time_s=round(time.perf_counter() - t0, 3))
    return dict(
        base, oracle_tested=True, oracle_satisfiable=bool(result.satisfied),
        oracle_route=" -> ".join(result.route) if result.route else None,
        oracle_delivered_pairs=result.delivered_pairs, oracle_average_fidelity=result.average_fidelity,
        oracle_notes=result.notes, oracle_wall_time_s=round(time.perf_counter() - t0, 3),
    )


# --------------------------------------------------------------------------
# reconciliation (port of scripts/run_f05_reconciliation.py)
# --------------------------------------------------------------------------

def run_reconciliation_job(job: dict) -> dict:
    """Episode 1 with the default (shortest-hop) planner; if VIOLATED, the
    reconciliation policy picks one lever (route change / duration / slots)
    and episode 2 runs on a fresh timeline. `job` keys: case, topology,
    hardware, seed, combo, source, destination, [check_fidelity],
    [duration_multiplier], [slot_multiplier], [topology_kwargs]."""
    combo = job["combo"]
    duration_multiplier = job.get("duration_multiplier", 2.0)
    slot_multiplier = job.get("slot_multiplier", 2.0)
    spec = build_topology(
        job["topology"], job["hardware"], duration_s=combo["duration_s"] * max(duration_multiplier, 1.0),
        **job.get("topology_kwargs", {}),
    )
    intent = build_intent(
        f"recon-{job['case']}", job["source"], job["destination"], combo, check_fidelity=job.get("check_fidelity", False),
    )
    seed = job["seed"]
    row: dict[str, Any] = dict(
        case=job["case"], topology=job["topology"], hardware=job["hardware"], platform=spec.platform, seed=seed,
        requested_fidelity=combo["min_fidelity"], min_delivered_pairs=combo["min_delivered_pairs"],
        initial_status=None, action=None, reconciliation_attempted=False, recovered=None,
        additional_wall_time_s=None, episodes=1,
        episode1_route=None, episode1_delivered_pairs=None, episode1_average_fidelity=None,
        episode1_reserved_memory_slots=combo["reserved_memory_slots"], episode1_duration_s=combo["duration_s"],
        episode1_wall_time_s=None,
        episode2_route=None, episode2_delivered_pairs=None, episode2_average_fidelity=None,
        episode2_reserved_memory_slots=None, episode2_duration_s=None,
    )

    metrics.configure()
    capabilities = NetworkCapabilities(spec)
    plan = IntentPlanner(capabilities, routing_strategy=ShortestHopCountRouting()).plan(intent)
    if not plan.feasible:
        row["initial_status"] = "REJECTED"
        return row
    repository = IntentRepository()
    adapter = SequenceAdapter(spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, plan)
    t0 = time.perf_counter()
    executor.run()
    row["episode1_wall_time_s"] = round(time.perf_counter() - t0, 3)
    row["episode1_route"] = "->".join(plan.route)
    if repository.get(intent.id).lifecycle.status != IntentStatus.ACTIVE:
        row["initial_status"] = repository.get(intent.id).lifecycle.status.value
        return row

    evaluation = evaluate_intent(intent, collect_intent_evidence(intent))
    status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
    repository.transition(intent.id, status, "; ".join(evaluation.violations) or "satisfied", sim_time=0.0)
    row["episode1_delivered_pairs"], row["episode1_average_fidelity"] = _evidence_summary(intent)
    row["initial_status"] = status.value
    if status != IntentStatus.VIOLATED:
        return row

    decision = decide_reconciliation_action(
        classify_violations(evaluation), capabilities=capabilities, source=intent.endpoints.source,
        destination=intent.endpoints.destination, current_route=plan.route,
        current_reserved_memory_slots=intent.requirements.reserved_memory_slots,
        min_fidelity=intent.requirements.min_fidelity, allow_purification=intent.policy.allow_purification,
    )
    row["action"] = decision.action
    if decision.action == "no_action":
        return row

    adjusted = apply_reconciliation_decision(
        intent, decision, duration_multiplier=duration_multiplier, slot_multiplier=slot_multiplier,
    )
    t0 = time.perf_counter()
    result = reconcile(
        intent, spec, repository, evaluation, seed=seed + RECONCILIATION_SEED_OFFSET,
        routing_strategy=decision.recommended_routing_strategy or ShortestHopCountRouting(),
        intent_override=adjusted if adjusted != intent else None,
    )
    working = adjusted if adjusted != intent else intent
    delivered, fidelity = _evidence_summary(working)
    row.update(
        reconciliation_attempted=True, recovered=result.final_status == IntentStatus.SATISFIED,
        additional_wall_time_s=round(time.perf_counter() - t0, 3), episodes=2,
        episode2_route="->".join(result.new_plan.route) if result.new_plan and result.new_plan.route else None,
        episode2_delivered_pairs=delivered, episode2_average_fidelity=fidelity,
        episode2_reserved_memory_slots=working.requirements.reserved_memory_slots,
        episode2_duration_s=working.requirements.duration_s,
        final_status=result.final_status.value,
    )
    return row


# --------------------------------------------------------------------------
# architecture baselines (port of scripts/run_f01_architecture_baselines.py)
# --------------------------------------------------------------------------

BASELINE_CONDITIONS: tuple[str, ...] = (
    "native_sequence", "static_provisioning", "ibqn_without_assurance",
    "ibqn_with_assurance", "ibqn_with_reconciliation", "ibqn_resource_aware_planner", "offline_oracle",
)
RESOURCE_AWARE_BASELINE_PLANNER = "L2-RB"


def run_baseline_job(job: dict) -> dict:
    """One (condition, seed) cell of the architecture-baseline comparison.
    `job` keys: condition, topology, hardware, seed, combo, source,
    destination, [topology_kwargs]."""
    combo = job["combo"]
    spec = build_topology(job["topology"], job["hardware"], duration_s=combo["duration_s"] * 2, **job.get("topology_kwargs", {}))
    intent = build_intent("baseline-intent", job["source"], job["destination"], combo, check_fidelity=False)
    condition, seed = job["condition"], job["seed"]
    base = dict(condition=condition, topology=job["topology"], hardware=job["hardware"], platform=spec.platform, seed=seed)

    def row(**values) -> dict:
        out = dict(base, accepted=None, satisfied=None, delivered_pairs=None, average_fidelity=None, route=None,
                   planning_wall_time_s=None, simulation_wall_time_s=None, total_wall_time_s=None, episodes=1)
        out.update(values)
        return out

    if condition in ("native_sequence", "static_provisioning", "offline_oracle"):
        if condition == "native_sequence":
            result = run_native_sequence_baseline(spec, intent, seed=seed)
        elif condition == "static_provisioning":
            result = run_static_provisioning_baseline(spec, intent, seed=seed, routing_strategy=ShortestHopCountRouting())
        else:
            result = run_offline_oracle_baseline(spec, intent, seed=seed)
        return row(
            accepted=result.accepted, satisfied=result.satisfied, delivered_pairs=result.delivered_pairs,
            average_fidelity=result.average_fidelity, route=" -> ".join(result.route) if result.route else None,
            planning_wall_time_s=result.planning_wall_time_s, simulation_wall_time_s=result.simulation_wall_time_s,
            total_wall_time_s=result.total_wall_time_s,
            episodes=result.candidates_evaluated if condition == "offline_oracle" else 1,
        )

    if condition == "ibqn_without_assurance":
        # planner + deploy + run, reporting only whether the reservation was
        # accepted - no assurance at all (what "admitted" alone tells you)
        metrics.configure()
        t0 = time.perf_counter()
        plan = IntentPlanner(NetworkCapabilities(spec), routing_strategy=ShortestHopCountRouting()).plan(intent)
        planning_s = time.perf_counter() - t0
        if not plan.feasible:
            return row(accepted=False, planning_wall_time_s=planning_s, simulation_wall_time_s=0.0, total_wall_time_s=planning_s)
        repository = IntentRepository()
        adapter = SequenceAdapter(spec, seed=seed)
        executor = SequenceExecutor(adapter, repository)
        executor.deploy(intent, plan)
        t1 = time.perf_counter()
        executor.run()
        simulation_s = time.perf_counter() - t1
        return row(
            accepted=repository.get(intent.id).lifecycle.status == IntentStatus.ACTIVE, route=" -> ".join(plan.route),
            planning_wall_time_s=planning_s, simulation_wall_time_s=simulation_s,
            total_wall_time_s=time.perf_counter() - t0,
        )

    if condition == "ibqn_resource_aware_planner":
        # IBQN with assurance, the default one-round planner replaced by the resource-aware one: the
        # route is chosen for what it can deliver in the window, before anything is deployed
        identity = TrialIdentity(
            campaign="R01_architecture_baselines", scenario=f"{job['topology']}@{job['hardware']}",
            parameter_hash="resource_aware", strategy=RESOURCE_AWARE_BASELINE_PLANNER, seed=seed, intent_id=intent.id,
        )
        record = execute_trial_with_policy(
            identity, intent, spec, make_planner(RESOURCE_AWARE_BASELINE_PLANNER),
            PlanningContext(routing_strategy=ShortestHopCountRouting(), topology_spec=spec),
            project_commit=job.get("project_commit"), sequence_commit=job.get("sequence_commit"),
        )
        return row(
            accepted=record.feasible, satisfied=record.satisfied, delivered_pairs=record.delivered_pairs,
            average_fidelity=record.average_fidelity, route=record.route if record.feasible else None,
            planning_wall_time_s=record.planning_time_s, simulation_wall_time_s=record.simulation_wall_time_s,
            total_wall_time_s=(record.planning_time_s or 0) + (record.simulation_wall_time_s or 0),
        )

    reconciliation = condition == "ibqn_with_reconciliation"
    identity = TrialIdentity(
        campaign="R01_architecture_baselines", scenario=f"{job['topology']}@{job['hardware']}",
        parameter_hash="reconcile" if reconciliation else "noreconcile",
        strategy="shortest_hop_count__automatic__conservative_min", seed=seed, intent_id=intent.id,
    )
    params = TrialParameters(
        topology_spec=spec, intent=intent, routing_strategy_name="shortest_hop_count",
        purification_policy_name="automatic", reconciliation_enabled=reconciliation,
    )
    record = execute_trial(identity, params, project_commit=job.get("project_commit"), sequence_commit=job.get("sequence_commit"))
    return row(
        accepted=record.accepted, satisfied=record.satisfied, delivered_pairs=record.delivered_pairs,
        average_fidelity=record.average_fidelity, route=record.route,
        planning_wall_time_s=record.planning_time_s, simulation_wall_time_s=record.simulation_wall_time_s,
        total_wall_time_s=(record.planning_time_s or 0) + (record.simulation_wall_time_s or 0),
        episodes=2 if record.recovered is not None else 1,
    )


# --------------------------------------------------------------------------
# orchestration overhead (port of scripts/run_f06_overhead.py)
# --------------------------------------------------------------------------

OVERHEAD_CONDITIONS: tuple[str, ...] = ("ibqn_instrumented", "native_sequence", "static_provisioning")


def run_overhead_job(job: dict) -> dict:
    """`job` keys: condition, topology, hardware, seed, combo, source,
    destination, [topology_kwargs]."""
    combo = job["combo"]
    spec = build_topology(job["topology"], job["hardware"], duration_s=combo["duration_s"], **job.get("topology_kwargs", {}))
    intent = build_intent("overhead-intent", job["source"], job["destination"], combo, check_fidelity=False)
    condition, seed = job["condition"], job["seed"]
    base = dict(condition=condition, topology=job["topology"], hardware=job["hardware"], platform=spec.platform, seed=seed)
    if condition == "ibqn_instrumented":
        timing, _ = run_instrumented_trial(
            intent, spec, seed=seed, routing_strategy=ShortestHopCountRouting(), reconciliation_enabled=True,
        )
        return dict(
            base,
            intent_parsing_wall_time_s=timing.intent_parsing_wall_time_s,
            intent_validation_wall_time_s=timing.intent_validation_wall_time_s,
            capability_extraction_wall_time_s=timing.capability_extraction_wall_time_s,
            planning_wall_time_s=timing.planning_wall_time_s,
            deployment_wall_time_s=timing.deployment_wall_time_s,
            assurance_wall_time_s=timing.assurance_wall_time_s,
            reconciliation_decision_wall_time_s=timing.reconciliation_decision_wall_time_s,
            simulation_wall_time_s=timing.simulation_wall_time_s,
            total_orchestration_wall_time_s=timing.total_orchestration_wall_time_s,
            total_trial_wall_time_s=timing.total_trial_wall_time_s,
            orchestration_overhead_ratio=timing.orchestration_overhead_ratio,
            planning_overhead_ratio=timing.planning_overhead_ratio,
        )
    if condition == "native_sequence":
        result = run_native_sequence_baseline(spec, intent, seed=seed)
    else:
        result = run_static_provisioning_baseline(spec, intent, seed=seed, routing_strategy=ShortestHopCountRouting())
    total = result.total_wall_time_s
    return dict(
        base, planning_wall_time_s=result.planning_wall_time_s, simulation_wall_time_s=result.simulation_wall_time_s,
        total_trial_wall_time_s=total,
        orchestration_overhead_ratio=(total - result.simulation_wall_time_s) / total if total else None,
        planning_overhead_ratio=result.planning_wall_time_s / total if total else None,
    )


# --------------------------------------------------------------------------
# multi-intent (port of scripts/run_concurrent_intent_campaign.py)
# --------------------------------------------------------------------------

def _classify_failure(final_status: str, failed_reason: str | None) -> str:
    if final_status == "REJECTED":
        return "B_or_A_pending_oracle"
    if final_status == "SATISFIED":
        return "none"
    if final_status == "VIOLATED":
        return "B_false_feasibility"
    if final_status == "FAILED":
        reason = failed_reason or ""
        if "reservation rejected by NetworkManager" in reason:
            return "C_resource_contention_reservation_rejected"
        if reason.startswith("simulation raised"):
            return "E_infrastructure_simulator_failure"
        return "D_unclassified_architectural_failure"
    return "unclassified"


def _run_intent_group(job: dict, intent_specs: list[dict], group_id: str) -> tuple[list[dict], dict]:
    """Deploys every intent in `intent_specs` onto ONE shared
    `SequenceExecutor`/`Timeline`, runs once, evaluates each."""
    duration = max(spec["duration_s"] for spec in intent_specs)
    topology = build_topology(job["topology"], job["hardware"], duration_s=duration, **job.get("topology_kwargs", {}))
    capabilities = NetworkCapabilities(topology)
    adapter = SequenceAdapter(topology, seed=job["seed"])
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    metrics.configure()
    metrics.reset_metrics()
    context = PlanningContext(routing_strategy=ShortestHopCountRouting(), topology_spec=topology)

    intents: dict[str, EntanglementIntent] = {}
    decisions: dict[str, Any] = {}
    timings: dict[str, dict[str, float]] = {}
    orchestration_total = 0.0
    for spec in intent_specs:
        intent_id = f"{group_id}-{spec['group_role']}"
        combo = dict(
            min_fidelity=spec["min_fidelity"], reserved_memory_slots=spec["reserved_memory_slots"],
            min_delivered_pairs=spec["min_delivered_pairs"], duration_s=spec["duration_s"],
            allow_purification=spec.get("allow_purification", True),
        )
        intent = build_intent(intent_id, spec["source"], spec["destination"], combo)
        intents[intent_id] = intent
        policy = make_planner(job["planner_level"])
        t0 = time.perf_counter()
        decision = policy.plan(intent, capabilities, generate_candidate_paths(intent, capabilities, context), context)
        planning_s = time.perf_counter() - t0
        decisions[intent_id] = decision
        t0 = time.perf_counter()
        if decision.feasible:
            executor.deploy(intent, decision.selected_plan)
        else:
            repository.add(intent, sim_time=0.0)
            repository.transition(intent.id, IntentStatus.VALIDATED, "schema validated", sim_time=0.0)
            repository.transition(intent.id, IntentStatus.PLANNING, "invoking planner", sim_time=0.0)
            repository.transition(
                intent.id, IntentStatus.REJECTED,
                decision.selected_plan.infeasibility_reason or "no feasible execution plan", sim_time=0.0,
            )
        orchestration_s = time.perf_counter() - t0
        timings[intent_id] = dict(planning=planning_s, orchestration=orchestration_s)
        orchestration_total += planning_s + orchestration_s

    t0 = time.perf_counter()
    if any(decision.feasible for decision in decisions.values()):
        executor.run()
    simulation_s = time.perf_counter() - t0

    intent_rows = []
    for spec in intent_specs:
        intent_id = f"{group_id}-{spec['group_role']}"
        intent, decision = intents[intent_id], decisions[intent_id]
        record = repository.get(intent_id)
        delivered = fidelity = satisfied = None
        if record.lifecycle.status == IntentStatus.ACTIVE:
            evaluation = evaluate_intent(intent, collect_intent_evidence(intent))
            status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
            repository.transition(
                intent.id, status, "; ".join(evaluation.violations) or "all success conditions met",
                sim_time=adapter.get_timeline().now() / 1e12,
            )
            satisfied = evaluation.satisfied
            delivered, fidelity = _evidence_summary(intent)
            record = repository.get(intent_id)
        failed_reason = (
            record.lifecycle.history[-1].reason
            if record.lifecycle.status == IntentStatus.FAILED and record.lifecycle.history else None
        )
        final_status = record.lifecycle.status.value
        intent_rows.append(dict(
            group_id=group_id, intent_id=intent_id, group_role=spec["group_role"], scenario=job["scenario"],
            topology=job["topology"], hardware=job["hardware"], platform=topology.platform,
            planner_level=job["planner_level"], seed=job["seed"],
            source=spec["source"], destination=spec["destination"], min_fidelity=spec["min_fidelity"],
            reserved_memory_slots=spec["reserved_memory_slots"], min_delivered_pairs=spec["min_delivered_pairs"],
            duration_s=spec["duration_s"], decision_feasible=decision.feasible,
            route=" -> ".join(decision.selected_plan.route) if decision.feasible else None,
            final_status=final_status, satisfied=satisfied, delivered_pairs=delivered, average_fidelity=fidelity,
            failure_class=_classify_failure(final_status, failed_reason),
            rejection_reason=decision.rejection_reason if not decision.feasible else None, failed_reason=failed_reason,
            planning_wall_time_s=timings[intent_id]["planning"],
            orchestration_wall_time_s=timings[intent_id]["orchestration"],
            simulation_wall_time_s_shared=simulation_s, lifecycle_history_length=len(record.lifecycle.history),
        ))
    group_row = dict(
        group_id=group_id, scenario=job["scenario"], topology=job["topology"], hardware=job["hardware"],
        planner_level=job["planner_level"], seed=job["seed"], intents_submitted=len(intent_specs),
        admitted=sum(1 for r in intent_rows if r["decision_feasible"]),
        rejected=sum(1 for r in intent_rows if not r["decision_feasible"]),
        satisfied=sum(1 for r in intent_rows if r["final_status"] == "SATISFIED"),
        violated=sum(1 for r in intent_rows if r["final_status"] == "VIOLATED"),
        failed=sum(1 for r in intent_rows if r["final_status"] == "FAILED"),
        simulation_wall_time_s=simulation_s, orchestration_wall_time_s_total=orchestration_total,
    )
    return intent_rows, group_row


def run_multi_intent_job(job: dict) -> dict:
    """One multi-intent group. `job` keys: scenario, topology, hardware,
    planner_level, seed, intents (list of per-intent dicts), sequential
    (bool: run each intent as its own episode instead of sharing a
    timeline), [topology_kwargs]. Returns the group's row with its
    per-intent rows JSON-encoded under `intent_rows_json` (one flat row per
    job, so the campaign checkpoints and resumes like the others)."""
    group_id = f"{job['scenario']}-{job['hardware']}-{job['planner_level']}-seed{job['seed']}"
    if not job.get("sequential", False):
        intent_rows, group_row = _run_intent_group(job, job["intents"], group_id)
        return dict(group_row, intent_rows_json=json.dumps(intent_rows))

    intent_rows: list[dict] = []
    parts: list[dict] = []
    for spec in job["intents"]:
        rows, part = _run_intent_group(job, [spec], group_id)
        intent_rows.extend(rows)
        parts.append(part)
    group_row = dict(parts[0])
    for field in ("intents_submitted", "admitted", "rejected", "satisfied", "violated", "failed",
                  "simulation_wall_time_s", "orchestration_wall_time_s_total"):
        group_row[field] = sum(part[field] for part in parts)
    return dict(group_row, intent_rows_json=json.dumps(intent_rows))
