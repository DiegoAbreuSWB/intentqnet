"""P04 (predictability-limits study, M9/section 5): retry-storm pilot.
Driven by configs/campaigns/predictability/P04_retry_storm.yaml. Every
trial runs through a hard subprocess wall-clock cap
(predictability_common.run_trial_with_timeout) - see that config's
description for why. Writes only to
results/predictability/raw/P04_retry_storm/ - never touches any
P01/P02/P02B/P03 planner-study data.
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

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability" / "P04_retry_storm.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    campaign_name = config["name"]
    output_dir = str(PROJECT_ROOT / config["output_directory"])
    trials_path = trials_csv_path(output_dir, campaign_name)
    known_trial_ids = read_trial_ids(trials_path)

    completed = 0
    skipped = 0
    timeouts = 0
    for min_fidelity in config["min_fidelity_sweep"]:
        parameter_hash = compute_parameter_hash({
            "min_fidelity": min_fidelity, "duration_s": config["duration_s"],
            "reserved_memory_slots": config["reserved_memory_slots"],
        })
        for seed in config["seeds"]:
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
                min_fidelity=min_fidelity, reserved_memory_slots=config["reserved_memory_slots"],
                min_delivered_pairs=config["min_delivered_pairs"], duration_s=config["duration_s"],
                timeout_s=config["timeout_s"],
            )
            record = PredictabilityTrialRecord(**row)
            append_trial_record(trials_path, record)
            known_trial_ids.add(trial_id)
            completed += 1
            if record.timed_out:
                timeouts += 1
            print(
                f"[{completed}] fid={min_fidelity} seed={seed} -> {record.final_status} "
                f"wall={record.simulation_wall_time_s}"
            )

    print(f"DONE: completed={completed}, skipped={skipped}, timeouts={timeouts}, output={trials_path}")


if __name__ == "__main__":
    main()
