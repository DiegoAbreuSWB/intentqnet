"""IBQN Validation-B2: runs the existing offline-oracle baseline
(experiments.baselines.run_offline_oracle_baseline, unmodified) against
every REJECTED row of the frozen P02b_resource_aware_planners campaign,
partitioned by planner_name - closing the gap identified in
docs/paper_ibqn_validation/data_sufficiency_assessment.md item B (F04's
existing oracle result is partitioned by routing_strategy/
purification_policy, not by the L1-L6 planner axis).

Reuses, byte-for-byte, the same topology builders/endpoints/intent
construction as scripts/run_p02b_resource_aware_planners.py, looked up by
each rejected row's parameter_hash - never guesses or approximates the
original intent.

Never writes to results/planner_study/raw/P02b_resource_aware_planners/ -
P02b's frozen trials.csv is opened read-only.

Driven by configs/campaigns/ibqn_validation_b/P16_oracle_by_planner.yaml.
Run: python scripts/run_oracle_by_planner.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.demos.environment import collect_environment_info  # noqa: E402
from ibqn.demos.intents import simple_intent  # noqa: E402
from ibqn.demos.topologies import diamond_spec, three_node_spec  # noqa: E402
from ibqn.experiments.baselines import run_offline_oracle_baseline  # noqa: E402
from ibqn.experiments.sweeps import compute_parameter_hash  # noqa: E402
from ibqn.experiments.topology_catalog import linear_chain_spec, small_mesh_spec  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "ibqn_validation_b" / "P16_oracle_by_planner.yaml"

# Identical to scripts/run_p02b_resource_aware_planners.py's TOPOLOGY_BUILDERS.
TOPOLOGY_BUILDERS = {
    "three_node_spec": lambda: three_node_spec(stop_time_s=0.2),
    "linear_chain_2_spec": lambda: linear_chain_spec(2, stop_time_s=0.2),
    "diamond_spec": lambda: diamond_spec(stop_time_s=0.2),
    "small_mesh_spec": lambda: small_mesh_spec(stop_time_s=0.2),
}


def _load_p02b_topology_index(p02b_config_path: Path) -> dict:
    """Builds {scenario_name: {"builder": str, "endpoints": dict,
    "parameter_hash": {hash: combo}}} from the original P02b YAML, so
    every rejected row can be matched back to its exact original
    topology builder, endpoints, and combo dict (including
    `allow_purification`, which trials.csv does not carry as a column)."""
    config = yaml.safe_load(p02b_config_path.read_text(encoding="utf-8"))["campaign"]
    index = {}
    for topo_entry in config["topologies"]:
        combo_by_hash = {compute_parameter_hash(combo): combo for combo in topo_entry["combinations"]}
        index[topo_entry["name"]] = {
            "builder": topo_entry["builder"],
            "endpoints": topo_entry["intent_endpoints"],
            "combo_by_hash": combo_by_hash,
        }
    return index


def main() -> None:
    p16_config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    p02b_trials_path = PROJECT_ROOT / p16_config["source_trials_csv"]
    p02b_config_path = PROJECT_ROOT / p16_config["source_config"]
    planners_included = p16_config["planners_included"]
    seed_offset = p16_config["oracle_seed_offset"]
    max_candidates = p16_config["oracle_max_candidates"]
    output_dir = PROJECT_ROOT / p16_config["output_directory"]
    output_dir.mkdir(parents=True, exist_ok=True)

    topology_index = _load_p02b_topology_index(p02b_config_path)

    p02b = pd.read_csv(p02b_trials_path)
    rejected = p02b[(p02b["final_status"] == "REJECTED") & (p02b["planner_name"].isin(
        {"conservative_one_round": "L1", "iterative_analytical": "L2", "iterative_resource_aware": "L2-R"}.keys()
    ))].copy()

    planner_level_by_name = {
        "conservative_one_round": "L1", "iterative_analytical": "L2", "iterative_resource_aware": "L2-R",
    }

    env = collect_environment_info()
    rows = []
    n = len(rejected)
    for i, (_, row) in enumerate(rejected.iterrows(), start=1):
        scenario = row["scenario"]
        topo = topology_index[scenario]
        combo = topo["combo_by_hash"].get(row["parameter_hash"])
        if combo is None:
            rows.append({
                "trial_id": row["trial_id"], "planner_level": planner_level_by_name[row["planner_name"]],
                "planner_name": row["planner_name"], "scenario": scenario, "seed": row["seed"],
                "oracle_seed": None, "oracle_tested": False, "oracle_satisfiable": None,
                "oracle_route": None, "oracle_notes": "parameter_hash not found in P02b source config",
                "oracle_wall_time_s": 0.0,
            })
            continue

        topology_spec = TOPOLOGY_BUILDERS[topo["builder"]]()
        endpoints = topo["endpoints"]
        intent = simple_intent(
            intent_id=f"p16-oracle-{row['trial_id']}", source=endpoints["source"], destination=endpoints["destination"],
            min_fidelity=combo["min_fidelity"], requested_pairs=combo["reserved_memory_slots"],
            min_delivered_pairs=combo["min_delivered_pairs"], start_time=0.01,
            duration=combo["duration_s"], allow_purification=combo["allow_purification"],
        )
        oracle_seed = int(row["seed"]) + seed_offset

        t0 = time.perf_counter()
        try:
            result = run_offline_oracle_baseline(topology_spec, intent, seed=oracle_seed, max_candidates=max_candidates)
            rows.append({
                "trial_id": row["trial_id"], "planner_level": planner_level_by_name[row["planner_name"]],
                "planner_name": row["planner_name"], "scenario": scenario, "seed": row["seed"],
                "oracle_seed": oracle_seed, "oracle_tested": True, "oracle_satisfiable": bool(result.satisfied),
                "oracle_route": " -> ".join(result.route) if result.route else None,
                "oracle_notes": result.notes, "oracle_wall_time_s": round(time.perf_counter() - t0, 6),
                "requested_fidelity": combo["min_fidelity"], "duration_s": combo["duration_s"],
                "reserved_memory_slots": combo["reserved_memory_slots"], "min_delivered_pairs": combo["min_delivered_pairs"],
                "allow_purification": combo["allow_purification"], "regime": combo["regime"],
            })
        except ValueError as exc:
            rows.append({
                "trial_id": row["trial_id"], "planner_level": planner_level_by_name[row["planner_name"]],
                "planner_name": row["planner_name"], "scenario": scenario, "seed": row["seed"],
                "oracle_seed": oracle_seed, "oracle_tested": False, "oracle_satisfiable": None,
                "oracle_route": None, "oracle_notes": f"oracle not computable: {exc}",
                "oracle_wall_time_s": round(time.perf_counter() - t0, 6),
            })
        except Exception as exc:  # noqa: BLE001
            # A candidate route the oracle enumerates can itself hit the
            # same class of SeQUeNCe-internal protocol assertion documented
            # in docs/false_rejection_root_cause.md and confirmed live
            # during this script's own smoke test (BBPSSWProtocol's
            # kept_memo.fidelity check) - one candidate's simulator-level
            # failure must not crash the whole oracle-by-planner batch, and
            # must be recorded honestly as untested, not silently skipped.
            rows.append({
                "trial_id": row["trial_id"], "planner_level": planner_level_by_name[row["planner_name"]],
                "planner_name": row["planner_name"], "scenario": scenario, "seed": row["seed"],
                "oracle_seed": oracle_seed, "oracle_tested": False, "oracle_satisfiable": None,
                "oracle_route": None,
                "oracle_notes": f"oracle raised {type(exc).__name__} during candidate-route simulation: {exc}",
                "oracle_wall_time_s": round(time.perf_counter() - t0, 6),
            })
        print(f"[{i}/{n}] {scenario} {planner_level_by_name[row['planner_name']]} seed={row['seed']} "
              f"-> oracle_satisfiable={rows[-1]['oracle_satisfiable']}")

    out = pd.DataFrame(rows)
    out_path = output_dir / "oracle_results.csv"
    out.to_csv(out_path, index=False)

    (output_dir / "manifest.json").write_text(json.dumps({
        "source_trials_csv": str(p16_config["source_trials_csv"]),
        "source_config": str(p16_config["source_config"]),
        "planners_included": planners_included,
        "oracle_seed_offset": seed_offset,
        "n_rejected_rows_considered": int(n),
        "project_git_commit": env.project_commit,
        "sequence_git_commit": env.sequence_commit,
    }, indent=2), encoding="utf-8")

    print(f"DONE: {n} rejected rows processed, output={out_path}")


if __name__ == "__main__":
    main()
