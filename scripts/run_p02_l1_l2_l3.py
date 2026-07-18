"""P02 (planner-family study, M6): L1 vs. L2 vs. L3 admission accuracy and
calibration. Six hand-picked (attenuation, duration, slots, min_delivered_
pairs, min_fidelity) combinations spanning favorable / resource-marginal /
severe conditions (not a full factorial grid - deliberately designed to
avoid a single outcome class dominating, mirroring the P04 dataset-balance
guidance in spirit), x 20 seeds x 3 planner levels, on the three-node
chain (same topology physics as F03/P01 - see docs/planner_study_baseline.md).

L3 runs with admission_threshold=0.0 (deploys the best candidate whenever
ANY route is feasible with non-zero probability) so every trial's REAL
predicted_satisfaction_probability is recorded regardless of what a
stricter threshold would have decided - `scripts/analyze_p02.py` applies
candidate thresholds (0.50/0.75/0.90/0.95) post-hoc during analysis,
avoiding four separate simulation passes for what is really a decision-
rule choice applied to one recorded probability (see
docs/planner_comparison_methodology.md).

Never touches results/raw/F0* or results/planner_study/raw/P01_* - writes
only to results/planner_study/raw/P02_l1_l2_l3/.
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
from ibqn.planning.planners import (
    ConservativeOneRoundPlanner,
    IterativeAnalyticalPlanner,
    PlanningContext,
    ProbabilisticPlanner,
)
from ibqn.planning.routing import ShortestHopCountRouting

CAMPAIGN_NAME = "P02_l1_l2_l3"
OUTPUT_DIR = str(PROJECT_ROOT / "results" / "planner_study")
SEEDS = list(range(20))  # 0-9 validation, 10-19 test (docs/planner_comparison_methodology.md)

COMBINATIONS = [
    dict(reserved_memory_slots=10, duration_s=0.1, attenuation_db_per_m=1e-5, min_delivered_pairs=10, min_fidelity=0.65),
    dict(reserved_memory_slots=10, duration_s=0.1, attenuation_db_per_m=1e-5, min_delivered_pairs=10, min_fidelity=0.73),
    dict(reserved_memory_slots=2, duration_s=0.01, attenuation_db_per_m=1e-5, min_delivered_pairs=10, min_fidelity=0.65),
    dict(reserved_memory_slots=2, duration_s=0.01, attenuation_db_per_m=1e-5, min_delivered_pairs=10, min_fidelity=0.73),
    dict(reserved_memory_slots=2, duration_s=0.01, attenuation_db_per_m=1e-3, min_delivered_pairs=50, min_fidelity=0.65),
    dict(reserved_memory_slots=2, duration_s=0.01, attenuation_db_per_m=1e-3, min_delivered_pairs=50, min_fidelity=0.73),
]

PLANNERS = [
    ("L1", ConservativeOneRoundPlanner()),
    ("L2", IterativeAnalyticalPlanner()),
    ("L3", ProbabilisticPlanner(admission_threshold=0.0)),
]


def main() -> None:
    env = collect_environment_info()
    trials_path = trials_csv_path(OUTPUT_DIR, CAMPAIGN_NAME)
    known_trial_ids = read_trial_ids(trials_path)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())

    completed = 0
    skipped = 0
    for combo in COMBINATIONS:
        parameter_hash = compute_parameter_hash(combo)
        topology = three_node_spec(attenuation_db_per_m=combo["attenuation_db_per_m"], stop_time_s=0.2)
        for planner_name, policy in PLANNERS:
            for seed in SEEDS:
                identity = TrialIdentity(
                    campaign=CAMPAIGN_NAME, scenario="three_node", parameter_hash=parameter_hash,
                    strategy=planner_name, seed=seed, intent_id="p02-intent",
                )
                if identity.trial_id in known_trial_ids:
                    skipped += 1
                    continue

                intent = simple_intent(
                    intent_id="p02-intent", source="a", destination="b", min_fidelity=combo["min_fidelity"],
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
                print(f"[{completed}] {planner_name} seed={seed} fid={combo['min_fidelity']} "
                      f"slots={combo['reserved_memory_slots']} -> {record.final_status}")

    print(f"DONE: completed={completed}, skipped={skipped}, output={trials_path}")


if __name__ == "__main__":
    main()
