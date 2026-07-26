"""IBQN Validation-B3 (+B4): the minimum multi-intent campaign closing
data_sufficiency_assessment.md item G. Driven by
configs/campaigns/ibqn_validation_b/P17_concurrent_intents.yaml.

Also carries B4's overhead instrumentation (intent construction, planning,
orchestration/deployment, simulation, observation, assurance,
reconciliation-decision, reconciliation re-execution, persistence),
instrumented ONLY for this campaign - no historical campaign's numbers are
touched or retroactively estimated (see docs/paper_ibqn_validation/
overhead_measurement.md).

Never modifies any planner. Never touches P02b, F04, F05, F06, or any
other frozen result. Writes only to
results/ibqn_validation_b/P17_concurrent_intents/.

Run: python scripts/run_concurrent_intent_campaign.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.assurance.evaluator import evaluate_intent  # noqa: E402
from ibqn.assurance.reconciliation import reconcile  # noqa: E402
from ibqn.assurance.reconciliation_policy import decide_reconciliation_action  # noqa: E402
from ibqn.assurance.telemetry import collect_intent_evidence  # noqa: E402
from ibqn.assurance.violations import classify_violations  # noqa: E402
from ibqn.demos.environment import collect_environment_info  # noqa: E402
from ibqn.demos.intents import simple_intent  # noqa: E402
from ibqn.demos.topologies import star_spec  # noqa: E402
from ibqn.experiments.topology_catalog import small_mesh_spec as demos_small_mesh_spec  # noqa: E402
from ibqn.execution.sequence_executor import SequenceExecutor  # noqa: E402
from ibqn.intent.models import IntentStatus  # noqa: E402
from ibqn.intent.repository import IntentRepository  # noqa: E402
from ibqn.network.capabilities import NetworkCapabilities  # noqa: E402
from ibqn.network.sequence_adapter import SequenceAdapter  # noqa: E402
from ibqn.planning.planners import (  # noqa: E402
    ConservativeOneRoundPlanner,
    PlanningContext,
    ResourceAwareIterativePlanner,
    generate_candidate_paths,
)
from ibqn.planning.routing import ShortestHopCountRouting  # noqa: E402
from sequence.utils import metrics  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "ibqn_validation_b" / "P17_concurrent_intents.yaml"

TOPOLOGY_BUILDERS = {
    "small_mesh_spec": lambda kwargs: demos_small_mesh_spec(**kwargs),
    "star_spec": lambda kwargs: star_spec(**kwargs),
}
PLANNER_FACTORIES = {
    "L1": lambda: ConservativeOneRoundPlanner(),
    "L2-R": lambda: ResourceAwareIterativePlanner(),
}


def _classify_failure(final_status: str, rejection_reason: str | None, failed_reason: str | None) -> str:
    """A/B/C/D/E per architectural_validation_matrix.md's taxonomy -
    applied here at collection time since this is a new campaign, not a
    retrofit of historical data. FAILED is split by its lifecycle
    transition reason: a reservation genuinely rejected by SeQUeNCe's own
    NetworkManager (observed in C2, real resource contention) is
    Category C (execution-level, resource-driven), distinct from a
    mid-run exception (Category E, per B1's simulation_error_trace.md
    fix), which is itself distinct from any other/unexpected FAILED
    reason (kept as an explicit, inspectable D, never silently folded
    into C or E)."""
    if final_status == "REJECTED":
        return "B_or_A_pending_oracle"  # planner declined; whether it was a correct rejection is an oracle question, not decidable from this record alone
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


def _run_group(scenario_name, planner_level, seed, topology_spec, intent_specs, context, reconciliation_enabled,
                reconciliation_seed_offset, env):
    """Deploys every intent in `intent_specs` onto ONE shared
    SequenceExecutor/Timeline, runs once, evaluates each, optionally
    reconciles VIOLATED ones. Returns (intent_rows, group_row)."""
    group_id = f"{scenario_name}-{planner_level}-seed{seed}"
    policy = PLANNER_FACTORIES[planner_level]()
    capabilities = NetworkCapabilities(topology_spec)
    adapter = SequenceAdapter(topology_spec, seed=seed)
    repository = IntentRepository()
    executor = SequenceExecutor(adapter, repository)
    metrics.configure()
    metrics.reset_metrics()

    intents = {}
    plans = {}
    overhead = {iid: {} for iid in []}
    intent_rows = []

    t_val0 = time.perf_counter()
    for spec in intent_specs:
        intent_id = f"{group_id}-{spec['group_role']}"
        t0 = time.perf_counter()
        intent = simple_intent(
            intent_id=intent_id, source=spec["source"], destination=spec["destination"],
            min_fidelity=spec["min_fidelity"], requested_pairs=spec["requested_pairs"],
            start_time=0.01, duration=spec["duration_s"], allow_purification=spec.get("allow_purification", True),
        )
        intents[intent_id] = intent
        overhead[intent_id] = {"intent_validation_wall_time_s": time.perf_counter() - t0}
    intent_validation_total = time.perf_counter() - t_val0

    orchestration_total = 0.0
    for spec in intent_specs:
        intent_id = f"{group_id}-{spec['group_role']}"
        intent = intents[intent_id]

        t0 = time.perf_counter()
        candidate_paths = generate_candidate_paths(intent, capabilities, context)
        decision = policy.plan(intent, capabilities, candidate_paths, context)
        overhead[intent_id]["planning_wall_time_s"] = time.perf_counter() - t0
        plans[intent_id] = decision

        t0 = time.perf_counter()
        if decision.feasible:
            executor.deploy(intent, decision.selected_plan)
        else:
            repository.add(intent, sim_time=0.0)
            repository.transition(intent.id, IntentStatus.VALIDATED, "schema validated", sim_time=0.0)
            repository.transition(intent.id, IntentStatus.PLANNING, "invoking IntentPlanner", sim_time=0.0)
            repository.transition(
                intent.id, IntentStatus.REJECTED,
                decision.selected_plan.infeasibility_reason or "no feasible execution plan", sim_time=0.0,
            )
        overhead[intent_id]["orchestration_wall_time_s"] = time.perf_counter() - t0
        orchestration_total += overhead[intent_id]["orchestration_wall_time_s"]

    any_deployed = any(plans[f"{group_id}-{s['group_role']}"].feasible for s in intent_specs)
    t0 = time.perf_counter()
    if any_deployed:
        executor.run()
    simulation_wall_time_s = time.perf_counter() - t0

    for spec in intent_specs:
        intent_id = f"{group_id}-{spec['group_role']}"
        intent = intents[intent_id]
        decision = plans[intent_id]
        record = repository.get(intent_id)

        evaluation = None
        reconciliation_action = None
        reconciliation_recovered = None
        t_obs = t_assur = t_recon_decision = t_recon_exec = 0.0

        if record.lifecycle.status == IntentStatus.ACTIVE:
            t0 = time.perf_counter()
            evidence = collect_intent_evidence(intent)
            t_obs = time.perf_counter() - t0

            t0 = time.perf_counter()
            evaluation = evaluate_intent(intent, evidence)
            final_status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
            reason = "all success conditions met" if evaluation.satisfied else "; ".join(evaluation.violations)
            repository.transition(intent.id, final_status, reason, sim_time=adapter.get_timeline().now() / 1e12)
            t_assur = time.perf_counter() - t0
            record = repository.get(intent_id)

            if record.lifecycle.status == IntentStatus.VIOLATED and reconciliation_enabled:
                violations = classify_violations(evaluation)
                t0 = time.perf_counter()
                policy_decision = decide_reconciliation_action(violations)
                t_recon_decision = time.perf_counter() - t0
                reconciliation_action = policy_decision.action.value if hasattr(policy_decision.action, "value") else str(policy_decision.action)

                t0 = time.perf_counter()
                recon_result = reconcile(
                    intent, topology_spec, repository, evaluation,
                    seed=seed + reconciliation_seed_offset,
                )
                t_recon_exec = time.perf_counter() - t0
                reconciliation_recovered = recon_result.final_status == IntentStatus.SATISFIED
                record = repository.get(intent_id)

        final_record = repository.get(intent_id)
        rejection_reason = decision.rejection_reason if not decision.feasible else None
        failed_reason = (
            final_record.lifecycle.history[-1].reason
            if final_record.lifecycle.status == IntentStatus.FAILED and final_record.lifecycle.history
            else None
        )
        intent_rows.append({
            "group_id": group_id, "intent_id": intent_id, "group_role": spec["group_role"],
            "scenario": scenario_name, "planner_level": planner_level, "seed": seed,
            "source": spec["source"], "destination": spec["destination"],
            "min_fidelity": spec["min_fidelity"], "requested_pairs": spec["requested_pairs"],
            "duration_s": spec["duration_s"], "allow_purification": spec.get("allow_purification", True),
            "decision_feasible": decision.feasible, "route": " -> ".join(decision.selected_plan.route) if decision.feasible else None,
            "final_status": final_record.lifecycle.status.value,
            "satisfied": evaluation.satisfied if evaluation is not None else None,
            "delivered_pairs": evaluation.condition_results[0].observed if evaluation is not None and evaluation.condition_results else None,
            "reconciliation_action": reconciliation_action,
            "reconciliation_recovered": reconciliation_recovered,
            "failure_class": _classify_failure(final_record.lifecycle.status.value, rejection_reason, failed_reason),
            "rejection_reason": rejection_reason,
            "failed_reason": failed_reason,
            "intent_validation_wall_time_s": overhead[intent_id]["intent_validation_wall_time_s"],
            "planning_wall_time_s": overhead[intent_id]["planning_wall_time_s"],
            "orchestration_wall_time_s": overhead[intent_id]["orchestration_wall_time_s"],
            "simulation_wall_time_s_shared": simulation_wall_time_s,
            "observation_extraction_wall_time_s": t_obs,
            "assurance_wall_time_s": t_assur,
            "reconciliation_decision_wall_time_s": t_recon_decision,
            "reconciliation_execution_wall_time_s": t_recon_exec,
            "lifecycle_history_length": len(final_record.lifecycle.history),
            "project_git_commit": env.project_commit, "sequence_git_commit": env.sequence_commit,
        })

    group_row = {
        "group_id": group_id, "scenario": scenario_name, "planner_level": planner_level, "seed": seed,
        "intents_submitted": len(intent_specs),
        "admitted": sum(1 for r in intent_rows if r["decision_feasible"]),
        "rejected": sum(1 for r in intent_rows if not r["decision_feasible"]),
        "satisfied": sum(1 for r in intent_rows if r["final_status"] == "SATISFIED"),
        "violated": sum(1 for r in intent_rows if r["final_status"] == "VIOLATED"),
        "failed": sum(1 for r in intent_rows if r["final_status"] == "FAILED"),
        "reconciled_attempted": sum(1 for r in intent_rows if r["reconciliation_action"] is not None),
        "reconciled_recovered": sum(1 for r in intent_rows if r["reconciliation_recovered"] is True),
        "total_requested_pairs_reserved": sum(r["requested_pairs"] for r in intent_rows),
        "simulation_wall_time_s": simulation_wall_time_s,
        "orchestration_wall_time_s_total": orchestration_total,
        "group_wall_time_s": intent_validation_total + orchestration_total + simulation_wall_time_s + sum(
            r["observation_extraction_wall_time_s"] + r["assurance_wall_time_s"]
            + r["reconciliation_decision_wall_time_s"] + r["reconciliation_execution_wall_time_s"]
            for r in intent_rows
        ),
    }
    return intent_rows, group_row


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    output_dir = PROJECT_ROOT / config["output_directory"]
    output_dir.mkdir(parents=True, exist_ok=True)
    env = collect_environment_info()
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    reconciliation_enabled = config["reconciliation_enabled"]
    reconciliation_seed_offset = config["reconciliation_seed_offset"]

    all_intent_rows = []
    all_group_rows = []

    for scenario in config["scenarios"]:
        scenario_name = scenario["name"]
        builder_name = scenario["topology_builder"]
        topology_kwargs = scenario["topology_kwargs"]
        sequential = scenario.get("sequential", False)

        for planner_level in config["planners"]:
            for seed in config["seeds"]:
                if not sequential:
                    topology_spec = TOPOLOGY_BUILDERS[builder_name](topology_kwargs)
                    intent_rows, group_row = _run_group(
                        scenario_name, planner_level, seed, topology_spec, scenario["intents"], context,
                        reconciliation_enabled, reconciliation_seed_offset, env,
                    )
                else:
                    # C3: two independent, sequential episodes - each its
                    # own fresh topology/adapter/repository/executor, one
                    # intent each, run back to back. See
                    # docs/paper_ibqn_validation/concurrent_intent_validation.md
                    # for why this is NOT the same as a shared live timeline.
                    intent_rows = []
                    group_row_parts = []
                    for spec in scenario["intents"]:
                        topology_spec = TOPOLOGY_BUILDERS[builder_name](topology_kwargs)
                        rows, g = _run_group(
                            f"{scenario_name}-{spec['group_role']}", planner_level, seed, topology_spec, [spec],
                            context, reconciliation_enabled, reconciliation_seed_offset, env,
                        )
                        for r in rows:
                            r["group_id"] = f"{scenario_name}-{planner_level}-seed{seed}"
                        intent_rows.extend(rows)
                        group_row_parts.append(g)
                    group_row = {
                        "group_id": f"{scenario_name}-{planner_level}-seed{seed}", "scenario": scenario_name,
                        "planner_level": planner_level, "seed": seed,
                        "intents_submitted": sum(g["intents_submitted"] for g in group_row_parts),
                        "admitted": sum(g["admitted"] for g in group_row_parts),
                        "rejected": sum(g["rejected"] for g in group_row_parts),
                        "satisfied": sum(g["satisfied"] for g in group_row_parts),
                        "violated": sum(g["violated"] for g in group_row_parts),
                        "failed": sum(g["failed"] for g in group_row_parts),
                        "reconciled_attempted": sum(g["reconciled_attempted"] for g in group_row_parts),
                        "reconciled_recovered": sum(g["reconciled_recovered"] for g in group_row_parts),
                        "total_requested_pairs_reserved": sum(g["total_requested_pairs_reserved"] for g in group_row_parts),
                        "simulation_wall_time_s": sum(g["simulation_wall_time_s"] for g in group_row_parts),
                        "orchestration_wall_time_s_total": sum(g["orchestration_wall_time_s_total"] for g in group_row_parts),
                        "group_wall_time_s": sum(g["group_wall_time_s"] for g in group_row_parts),
                    }

                t_persist0 = time.perf_counter()
                all_intent_rows.extend(intent_rows)
                all_group_rows.append(group_row)
                group_row["persistence_wall_time_s"] = time.perf_counter() - t_persist0
                print(f"{scenario_name} {planner_level} seed={seed}: "
                      f"admitted={group_row['admitted']}/{group_row['intents_submitted']} "
                      f"satisfied={group_row['satisfied']} violated={group_row['violated']} "
                      f"reconciled_recovered={group_row['reconciled_recovered']}")

    intents_df = pd.DataFrame(all_intent_rows)
    groups_df = pd.DataFrame(all_group_rows)
    intents_df.to_csv(output_dir / "intents.csv", index=False)
    groups_df.to_csv(output_dir / "groups.csv", index=False)

    print(f"DONE: {len(all_intent_rows)} intent records, {len(all_group_rows)} group records, output={output_dir}")


if __name__ == "__main__":
    main()
