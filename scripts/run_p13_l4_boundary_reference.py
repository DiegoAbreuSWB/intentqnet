"""P13 (M10.7): L4 (Reference Planner) evaluated at the boundary. Driven
by configs/campaigns/predictability_m10/P13_l4_boundary_reference.yaml.
Runs L4's planning step once per (configuration, K) - deterministic given
`_derive_internal_seeds`' hash-based derivation, never re-run across
operational seeds (see the config's own docstring for why). Also deploys
and runs ONE real trial per (configuration, K) at a fixed operational
seed, for admission-decision/cost/simulation-count reporting alongside
the predicted probability. Writes only to
results/predictability_m10/raw/P13_l4_boundary_reference/.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from predictability_m10_common import run_trial_with_timeout  # noqa: E402

from ibqn.experiments.predictability_m10_records import (  # noqa: E402
    PredictabilityM10TrialRecord,
    append_trial_record,
    read_trial_ids,
    trials_csv_path,
)
from ibqn.experiments.sweeps import compute_parameter_hash  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability_m10" / "P13_l4_boundary_reference.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    campaign_name = config["name"]
    output_dir = str(PROJECT_ROOT / config["output_directory"])
    trials_path = trials_csv_path(output_dir, campaign_name)
    known_trial_ids = read_trial_ids(trials_path)

    completed = 0
    skipped = 0
    for cfg in config["configurations"]:
        for k in config["k_values"]:
            parameter_hash = compute_parameter_hash({
                "min_fidelity": cfg["min_fidelity"], "duration_s": cfg["duration_s"],
                "reserved_memory_slots": config["reserved_memory_slots"], "config_name": cfg["name"], "k": k,
            })
            trial_id = (
                f"{campaign_name}:{cfg['scenario']}:{parameter_hash}:L4:{config['seed']}:m10-intent:0"
            )
            if trial_id in known_trial_ids:
                skipped += 1
                continue

            t0 = time.perf_counter()
            row = run_trial_with_timeout(
                campaign=campaign_name, scenario=cfg["scenario"], topology_builder=cfg["topology_builder"],
                parameter_hash=parameter_hash, planner_level="L4", seed=config["seed"],
                min_fidelity=cfg["min_fidelity"], reserved_memory_slots=config["reserved_memory_slots"],
                min_delivered_pairs=config["min_delivered_pairs"], duration_s=cfg["duration_s"],
                timeout_s=config["timeout_s"], admission_threshold=config["admission_threshold"],
                simulations_per_candidate=k,
            )
            record = PredictabilityM10TrialRecord(**row)
            append_trial_record(trials_path, record)
            known_trial_ids.add(trial_id)
            completed += 1
            wall = round(time.perf_counter() - t0, 1)
            print(
                f"[{completed}] {cfg['name']} K={k} -> feasible={record.feasible} "
                f"predicted_p={record.predicted_satisfaction_probability} "
                f"final={record.final_status} planning_time_s={record.planning_time_s} wrapper_wall={wall}"
            )

    print(f"\nDONE: completed={completed}, skipped={skipped}, output={trials_path}")


if __name__ == "__main__":
    main()
