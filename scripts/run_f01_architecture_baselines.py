"""Fase J10 final campaign F01 (architecture/baselines) - ad-hoc script,
not run_programmatic_campaign/CampaignRunner (see
docs/results_provenance.md). Diamond topology, 6 conditions x 20 seeds.
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.demos.topologies import diamond_spec
from ibqn.demos.intents import diamond_intent
from ibqn.experiments.baselines import (
    run_native_sequence_baseline, run_static_provisioning_baseline, run_offline_oracle_baseline,
)
from ibqn.experiments.records import TrialIdentity
from ibqn.experiments.sweeps import TrialParameters
from ibqn.experiments.runner import execute_trial
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.execution.sequence_executor import SequenceExecutor
from ibqn.intent.repository import IntentRepository
from ibqn.intent.models import IntentStatus
from ibqn.planning.planner import IntentPlanner
from ibqn.planning.routing import ShortestHopCountRouting

SEEDS = list(range(20))
spec = diamond_spec(stop_time_s=0.2)
intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

rows = []


def add_row(condition, seed, *, accepted, satisfied, delivered_pairs, average_fidelity,
            planning_wall_time_s, simulation_wall_time_s, total_wall_time_s, episodes):
    rows.append({
        "condition": condition, "seed": seed, "accepted": accepted, "satisfied": satisfied,
        "delivered_pairs": delivered_pairs, "average_fidelity": average_fidelity,
        "planning_wall_time_s": planning_wall_time_s, "simulation_wall_time_s": simulation_wall_time_s,
        "total_wall_time_s": total_wall_time_s, "episodes": episodes,
    })


def run_ibqn_without_assurance(seed):
    """Planner + deploy + run, reporting only whether the reservation
    reached ACTIVE - no evaluate_intent call at all, isolating the value
    of assurance itself (does the reservation merely get accepted, vs
    does it actually meet requirements)."""
    t0 = time.perf_counter()
    capabilities = NetworkCapabilities(spec)
    planner = IntentPlanner(capabilities, routing_strategy=ShortestHopCountRouting())
    plan = planner.plan(intent)
    if not plan.feasible:
        return dict(accepted=False, satisfied=None, delivered_pairs=None, average_fidelity=None,
                    planning_wall_time_s=time.perf_counter() - t0, simulation_wall_time_s=0.0,
                    total_wall_time_s=time.perf_counter() - t0)
    planning_s = time.perf_counter() - t0

    repository = IntentRepository()
    adapter = SequenceAdapter(spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, plan)
    t1 = time.perf_counter()
    executor.run()
    sim_s = time.perf_counter() - t1

    accepted = repository.get(intent.id).lifecycle.status == IntentStatus.ACTIVE
    return dict(accepted=accepted, satisfied=None, delivered_pairs=None, average_fidelity=None,
                planning_wall_time_s=planning_s, simulation_wall_time_s=sim_s,
                total_wall_time_s=time.perf_counter() - t0)


for seed in SEEDS:
    # 1. Native SeQUeNCe
    native = run_native_sequence_baseline(spec, intent, seed=seed)
    add_row("native_sequence", seed, accepted=native.accepted, satisfied=native.satisfied,
             delivered_pairs=native.delivered_pairs, average_fidelity=native.average_fidelity,
             planning_wall_time_s=native.planning_wall_time_s, simulation_wall_time_s=native.simulation_wall_time_s,
             total_wall_time_s=native.total_wall_time_s, episodes=1)

    # 2. Static provisioning (fixed ShortestHopCountRouting choice)
    static = run_static_provisioning_baseline(spec, intent, seed=seed, routing_strategy=ShortestHopCountRouting())
    add_row("static_provisioning", seed, accepted=static.accepted, satisfied=static.satisfied,
            delivered_pairs=static.delivered_pairs, average_fidelity=static.average_fidelity,
            planning_wall_time_s=static.planning_wall_time_s, simulation_wall_time_s=static.simulation_wall_time_s,
            total_wall_time_s=static.total_wall_time_s, episodes=1)

    # 3. IBQN without assurance
    no_assurance = run_ibqn_without_assurance(seed)
    add_row("ibqn_without_assurance", seed, episodes=1, **no_assurance)

    # 4. IBQN with assurance (no reconciliation)
    identity_4 = TrialIdentity(campaign="F01_architecture_baselines", scenario="diamond", parameter_hash="noreconcile",
                                strategy="shortest_hop_count__automatic__conservative_min", seed=seed, intent_id=intent.id)
    params_4 = TrialParameters(topology_spec=spec, intent=intent, routing_strategy_name="shortest_hop_count",
                                purification_policy_name="automatic", reconciliation_enabled=False)
    record_4 = execute_trial(identity_4, params_4, project_commit=None, sequence_commit=None)
    add_row("ibqn_with_assurance", seed, accepted=record_4.accepted, satisfied=record_4.satisfied,
            delivered_pairs=record_4.delivered_pairs, average_fidelity=record_4.average_fidelity,
            planning_wall_time_s=record_4.planning_time_s, simulation_wall_time_s=record_4.simulation_wall_time_s,
            total_wall_time_s=(record_4.planning_time_s or 0) + (record_4.simulation_wall_time_s or 0), episodes=1)

    # 5. IBQN with reconciliation
    identity_5 = TrialIdentity(campaign="F01_architecture_baselines", scenario="diamond", parameter_hash="reconcile",
                                strategy="shortest_hop_count__automatic__conservative_min", seed=seed, intent_id=intent.id)
    params_5 = TrialParameters(topology_spec=spec, intent=intent, routing_strategy_name="shortest_hop_count",
                                purification_policy_name="automatic", reconciliation_enabled=True)
    record_5 = execute_trial(identity_5, params_5, project_commit=None, sequence_commit=None)
    add_row("ibqn_with_reconciliation", seed, accepted=record_5.accepted, satisfied=record_5.satisfied,
            delivered_pairs=record_5.delivered_pairs, average_fidelity=record_5.average_fidelity,
            planning_wall_time_s=record_5.planning_time_s, simulation_wall_time_s=record_5.simulation_wall_time_s,
            total_wall_time_s=(record_5.planning_time_s or 0) + (record_5.simulation_wall_time_s or 0),
            episodes=(2 if record_5.recovered is not None else 1))

    # 6. Offline oracle (small topology only - diamond has exactly 2 simple paths)
    oracle = run_offline_oracle_baseline(spec, intent, seed=seed)
    add_row("offline_oracle", seed, accepted=oracle.accepted, satisfied=oracle.satisfied,
            delivered_pairs=oracle.delivered_pairs, average_fidelity=oracle.average_fidelity,
            planning_wall_time_s=oracle.planning_wall_time_s, simulation_wall_time_s=oracle.simulation_wall_time_s,
            total_wall_time_s=oracle.total_wall_time_s, episodes=oracle.candidates_evaluated)

    print(f"seed {seed} done", file=sys.stderr)

import pandas as pd
df = pd.DataFrame(rows)
out_dir = PROJECT_ROOT / "results" / "raw" / "F01_architecture_baselines"
out_dir.mkdir(parents=True, exist_ok=True)
df.to_csv(os.path.join(out_dir, "trials.csv"), index=False)
print("wrote", len(df), "rows")
print("DONE")
