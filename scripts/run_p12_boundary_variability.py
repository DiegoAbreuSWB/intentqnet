"""P12 (M10.6): boundary variability campaign. Driven by
configs/campaigns/predictability_m10/P12_boundary_variability.yaml.
Resume-safe (skips seeds already recorded for a given configuration, so
a bug fix or interruption never re-executes completed trials). Writes
only to results/predictability_m10/raw/P12_boundary_variability/.
"""
from __future__ import annotations

import sys
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

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability_m10" / "P12_boundary_variability.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    campaign_name = config["name"]
    output_dir = str(PROJECT_ROOT / config["output_directory"])
    trials_path = trials_csv_path(output_dir, campaign_name)
    known_trial_ids = read_trial_ids(trials_path)

    completed = 0
    skipped = 0
    for cfg in config["configurations"]:
        n_seeds = (
            config["n_seeds_transition"] if cfg["expected_region"] == "TRANSITION"
            else config["n_seeds_robust_likely"]
        )
        parameter_hash = compute_parameter_hash({
            "min_fidelity": cfg["min_fidelity"], "duration_s": cfg["duration_s"],
            "reserved_memory_slots": config["reserved_memory_slots"], "config_name": cfg["name"],
        })
        n_satisfied = 0
        n_run = 0
        for seed in range(config["seed_base"], config["seed_base"] + n_seeds):
            trial_id = (
                f"{campaign_name}:{cfg['scenario']}:{parameter_hash}:{config['planner_level']}:"
                f"{seed}:m10-intent:0"
            )
            if trial_id in known_trial_ids:
                skipped += 1
                n_run += 1
                continue

            row = run_trial_with_timeout(
                campaign=campaign_name, scenario=cfg["scenario"], topology_builder=cfg["topology_builder"],
                parameter_hash=parameter_hash, planner_level=config["planner_level"], seed=seed,
                min_fidelity=cfg["min_fidelity"], reserved_memory_slots=config["reserved_memory_slots"],
                min_delivered_pairs=config["min_delivered_pairs"], duration_s=cfg["duration_s"],
                timeout_s=config["timeout_s"],
            )
            record = PredictabilityM10TrialRecord(**row)
            append_trial_record(trials_path, record)
            known_trial_ids.add(trial_id)
            completed += 1
            n_run += 1
            if record.final_status == "SATISFIED":
                n_satisfied += 1
            if completed % 20 == 0:
                print(f"[{completed}] {cfg['name']} seed={seed} -> {record.final_status}")

        print(f"{cfg['name']} ({cfg['expected_region']}): {n_satisfied}/{n_run} satisfied so far")

    print(f"\nDONE: completed={completed}, skipped={skipped}, output={trials_path}")


if __name__ == "__main__":
    main()
