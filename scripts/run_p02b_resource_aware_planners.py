"""P02B (planner-family study, M6e/checkpoint 2B): L1 vs. L2 vs. L2-R vs.
L3-original vs. L3-R, paired across four topologies. Driven entirely by
configs/campaigns/planner_study/P02b_resource_aware_planners.yaml (the
declarative source of truth for topologies/combinations/seeds/planners -
this script only maps builder/endpoint names to real Python callables and
executes).

Never touches results/raw/F0*, results/planner_study/raw/P01_*,
results/planner_study/raw/P02_l1_l2_l3/, or
results/planner_study/raw/P03_l4_cost/ - writes only to
results/planner_study/raw/P02b_resource_aware_planners/.

L4 is intentionally NOT included (see the YAML's description) - P03's
already-collected results are reused in checkpoint 2B's analysis instead
of re-simulating.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.demos.environment import collect_environment_info
from ibqn.demos.intents import simple_intent
from ibqn.demos.topologies import diamond_spec, three_node_spec
from ibqn.experiments.planner_study_records import append_trial_record, read_trial_ids, trials_csv_path
from ibqn.experiments.planner_study_runner import execute_trial_with_policy
from ibqn.experiments.records import TrialIdentity
from ibqn.experiments.sweeps import compute_parameter_hash
from ibqn.experiments.topology_catalog import linear_chain_spec, small_mesh_spec
from ibqn.planning.planners import (
    ConservativeOneRoundPlanner,
    IterativeAnalyticalPlanner,
    PlanningContext,
    ProbabilisticPlanner,
    ProbabilisticResourceAwarePlanner,
    ResourceAwareIterativePlanner,
)
from ibqn.planning.routing import ShortestHopCountRouting

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "planner_study" / "P02b_resource_aware_planners.yaml"

TOPOLOGY_BUILDERS = {
    "three_node_spec": lambda: three_node_spec(stop_time_s=0.2),
    "linear_chain_2_spec": lambda: linear_chain_spec(2, stop_time_s=0.2),
    "diamond_spec": lambda: diamond_spec(stop_time_s=0.2),
    "small_mesh_spec": lambda: small_mesh_spec(stop_time_s=0.2),
}

PLANNER_FACTORIES = {
    "L1": lambda: ConservativeOneRoundPlanner(),
    "L2": lambda: IterativeAnalyticalPlanner(),
    "L2-R": lambda: ResourceAwareIterativePlanner(),
    "L3": lambda: ProbabilisticPlanner(admission_threshold=0.0),
    "L3-R": lambda: ProbabilisticResourceAwarePlanner(admission_threshold=0.0),
}


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    campaign_name = config["name"]
    seeds = config["seeds"]
    planner_levels = config["planners"]

    env = collect_environment_info()
    output_dir = str(PROJECT_ROOT / config["output_directory"])
    trials_path = trials_csv_path(output_dir, campaign_name)
    known_trial_ids = read_trial_ids(trials_path)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())

    completed = 0
    skipped = 0
    for topo_entry in config["topologies"]:
        topo_name = topo_entry["name"]
        topology = TOPOLOGY_BUILDERS[topo_entry["builder"]]()
        endpoints = topo_entry["intent_endpoints"]

        for combo in topo_entry["combinations"]:
            parameter_hash = compute_parameter_hash(combo)
            for planner_level in planner_levels:
                policy = PLANNER_FACTORIES[planner_level]()
                for seed in seeds:
                    identity = TrialIdentity(
                        campaign=campaign_name, scenario=topo_name, parameter_hash=parameter_hash,
                        strategy=planner_level, seed=seed, intent_id="p02b-intent",
                    )
                    if identity.trial_id in known_trial_ids:
                        skipped += 1
                        continue

                    intent = simple_intent(
                        intent_id="p02b-intent", source=endpoints["source"], destination=endpoints["destination"],
                        min_fidelity=combo["min_fidelity"], requested_pairs=combo["reserved_memory_slots"],
                        min_delivered_pairs=combo["min_delivered_pairs"], start_time=0.01,
                        duration=combo["duration_s"], allow_purification=combo["allow_purification"],
                    )
                    record = execute_trial_with_policy(
                        identity, intent, topology, policy, context,
                        project_commit=env.project_commit, sequence_commit=env.sequence_commit,
                    )
                    append_trial_record(trials_path, record)
                    known_trial_ids.add(identity.trial_id)
                    completed += 1
                    print(
                        f"[{completed}] {topo_name} {planner_level} seed={seed} "
                        f"fid={combo['min_fidelity']} regime={combo['regime']} -> {record.final_status}"
                    )

    print(f"DONE: completed={completed}, skipped={skipped}, output={trials_path}")


if __name__ == "__main__":
    main()
