"""P02 (predictability-limits study, M9/section 1): intrinsic variability.
Driven by configs/campaigns/predictability/P02_variance.yaml. Runs the
superset of seeds (0..max(seed_counts)-1) per intent - the analysis
script slices the first 100/250/500 for the growing-seed-count
comparison, so only one pass of simulation is needed. Every trial runs
through the mandatory subprocess wall-clock cap. Writes only to
results/predictability/raw/P02_variance/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from predictability_common import run_trial_with_timeout  # noqa: E402

from ibqn.experiments.predictability_records import (  # noqa: E402
    PredictabilityTrialRecord,
    append_trial_record,
    read_trial_ids,
    trials_csv_path,
)
from ibqn.experiments.sweeps import compute_parameter_hash  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability" / "P02_variance.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    campaign_name = config["name"]
    output_dir = str(PROJECT_ROOT / config["output_directory"])
    trials_path = trials_csv_path(output_dir, campaign_name)
    known_trial_ids = read_trial_ids(trials_path)
    max_seeds = max(config["seed_counts"])

    completed = 0
    skipped = 0
    for intent_cfg in config["intents"]:
        parameter_hash = compute_parameter_hash({
            "min_fidelity": intent_cfg["min_fidelity"], "duration_s": config["duration_s"],
            "reserved_memory_slots": config["reserved_memory_slots"], "intent_name": intent_cfg["name"],
        })
        for seed in range(max_seeds):
            trial_id = (
                f"{campaign_name}:{config['scenario']}:{parameter_hash}:{config['planner_level']}:"
                f"{seed}:predictability-intent"
            )
            if trial_id in known_trial_ids:
                skipped += 1
                continue

            row = run_trial_with_timeout(
                campaign=campaign_name, scenario=config["scenario"], topology_builder=config["topology_builder"],
                parameter_hash=parameter_hash, planner_level=config["planner_level"], seed=seed,
                min_fidelity=intent_cfg["min_fidelity"], reserved_memory_slots=config["reserved_memory_slots"],
                min_delivered_pairs=config["min_delivered_pairs"], duration_s=config["duration_s"],
                timeout_s=config["timeout_s"],
            )
            record = PredictabilityTrialRecord(**row)
            append_trial_record(trials_path, record)
            known_trial_ids.add(trial_id)
            completed += 1
            if completed % 25 == 0:
                print(f"[{completed}] intent={intent_cfg['name']} seed={seed} -> {record.final_status}")

    print(f"DONE: completed={completed}, skipped={skipped}, output={trials_path}")


if __name__ == "__main__":
    main()
