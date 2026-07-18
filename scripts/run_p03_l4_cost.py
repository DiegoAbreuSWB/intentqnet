"""P03 (planner-family study, M8): cost of L4's K internal simulations.

**Disclosed, deliberate scope reduction** (see
docs/planner_study_findings_checkpoint2.md for why): the planner-study
brief asks for K in {5, 10, 20, 30} across multiple parameter
combinations. Each L4 planning call costs K+1 real SeQUeNCe simulations
(~5-9s each on this hardware), so K=30 alone costs ~4-5 minutes PER
TRIAL. Running the full requested grid was not achievable within this
session's wall-clock budget. This script runs K in {3, 5, 10} (a real,
disclosed reduction, not silently substituted) across 2 combinations
(favorable and resource-marginal, reusing P02's own combinations 1 and 3
for direct comparability) x 10 seeds - real signal on the cost/K
relationship, not the full sweep. Extending to K=20/30 and more
combinations is mechanical (edit K_VALUES/COMBINATIONS below) given more
wall-clock budget.

Writes only to results/planner_study/raw/P03_l4_cost/ - never touches
F0*/P01_*/P02_* data.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.demos.environment import collect_environment_info
from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.planner_study_records import append_trial_record, read_trial_ids, trials_csv_path
from ibqn.experiments.planner_study_runner import execute_trial_with_policy
from ibqn.experiments.records import TrialIdentity
from ibqn.experiments.sweeps import compute_parameter_hash
from ibqn.planning.planners import PlanningContext, SimulationInTheLoopPlanner, SimulationPlannerConfig
from ibqn.planning.routing import ShortestHopCountRouting

CAMPAIGN_NAME = "P03_l4_cost"
OUTPUT_DIR = str(PROJECT_ROOT / "results" / "planner_study")
SEEDS = list(range(10))  # reduced from P01/P02's 20 - see module docstring
K_VALUES = [3, 5, 10]  # reduced from the requested {5, 10, 20, 30} - see module docstring

COMBINATIONS = [
    dict(reserved_memory_slots=10, duration_s=0.1, attenuation_db_per_m=1e-5, min_delivered_pairs=10, min_fidelity=0.65, label="favorable"),
    dict(reserved_memory_slots=2, duration_s=0.01, attenuation_db_per_m=1e-5, min_delivered_pairs=10, min_fidelity=0.65, label="resource_marginal"),
]


def main() -> None:
    env = collect_environment_info()
    trials_path = trials_csv_path(OUTPUT_DIR, CAMPAIGN_NAME)
    known_trial_ids = read_trial_ids(trials_path)
    context_base_kwargs = dict(routing_strategy=ShortestHopCountRouting())

    completed = 0
    skipped = 0
    for combo in COMBINATIONS:
        parameter_hash = compute_parameter_hash({k: v for k, v in combo.items() if k != "label"})
        topology = three_node_spec(attenuation_db_per_m=combo["attenuation_db_per_m"], stop_time_s=0.2)
        for k in K_VALUES:
            strategy_name = f"L4_K{k}"
            policy = SimulationInTheLoopPlanner(
                config=SimulationPlannerConfig(simulations_per_candidate=k), admission_threshold=0.5,
            )
            context = PlanningContext(topology_spec=topology, **context_base_kwargs)
            for seed in SEEDS:
                identity = TrialIdentity(
                    campaign=CAMPAIGN_NAME, scenario=f"three_node_{combo['label']}", parameter_hash=parameter_hash,
                    strategy=strategy_name, seed=seed, intent_id="p03-intent",
                )
                if identity.trial_id in known_trial_ids:
                    skipped += 1
                    continue

                intent = simple_intent(
                    intent_id="p03-intent", source="a", destination="b", min_fidelity=combo["min_fidelity"],
                    requested_pairs=combo["reserved_memory_slots"], min_delivered_pairs=combo["min_delivered_pairs"],
                    start_time=0.01, duration=combo["duration_s"],
                )
                record = execute_trial_with_policy(
                    identity, intent, topology, policy, context,
                    project_commit=env.project_commit, sequence_commit=env.sequence_commit,
                )
                append_trial_record(trials_path, record)
                known_trial_ids.add(identity.trial_id)
                completed += 1
                print(f"[{completed}] {combo['label']} K={k} seed={seed} -> {record.final_status} "
                      f"(planning_time_s={record.planning_time_s:.2f})")

    print(f"DONE: completed={completed}, skipped={skipped}, output={trials_path}")


if __name__ == "__main__":
    main()
