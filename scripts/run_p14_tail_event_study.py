"""P14 (M10.8): tail-event diagnostic study. Driven by
configs/campaigns/predictability_m10/P14_tail_event_study.yaml.
Resume-safe. Writes only to
results/predictability_m10/raw/P14_tail_event_study/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from predictability_m10_common import run_tail_event_trial_with_timeout  # noqa: E402

from ibqn.experiments.predictability_m10_records import (  # noqa: E402
    PredictabilityM10TrialRecord,
    append_trial_record,
    read_trial_ids,
    trials_csv_path,
)
from ibqn.experiments.sweeps import compute_parameter_hash  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability_m10" / "P14_tail_event_study.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    campaign_name = config["name"]
    output_dir = str(PROJECT_ROOT / config["output_directory"])
    trials_path = trials_csv_path(output_dir, campaign_name)
    heartbeat_dir = Path(output_dir) / "raw" / campaign_name / "heartbeats"
    known_trial_ids = read_trial_ids(trials_path)

    completed = 0
    skipped = 0
    termination_counts: dict[str, int] = {}
    for cfg in config["configurations"]:
        parameter_hash = compute_parameter_hash({
            "min_fidelity": cfg["min_fidelity"], "duration_s": cfg["duration_s"],
            "reserved_memory_slots": config["reserved_memory_slots"], "config_name": cfg["name"],
        })
        for seed in range(config["seed_base"], config["seed_base"] + config["n_seeds"]):
            trial_id = (
                f"{campaign_name}:{cfg['scenario']}:{parameter_hash}:{config['planner_level']}:{seed}:m10-intent:0"
            )
            if trial_id in known_trial_ids:
                skipped += 1
                continue

            row = run_tail_event_trial_with_timeout(
                campaign=campaign_name, scenario=cfg["scenario"], topology_builder=cfg["topology_builder"],
                parameter_hash=parameter_hash, planner_level=config["planner_level"], seed=seed,
                min_fidelity=cfg["min_fidelity"], reserved_memory_slots=config["reserved_memory_slots"],
                min_delivered_pairs=config["min_delivered_pairs"], duration_s=cfg["duration_s"],
                timeout_s=config["timeout_s"], heartbeat_dir=heartbeat_dir,
                heartbeat_interval_s=config["heartbeat_interval_s"], max_events=config["max_events"],
            )
            record = PredictabilityM10TrialRecord(**row)
            append_trial_record(trials_path, record)
            known_trial_ids.add(trial_id)
            completed += 1
            reason = record.termination_reason or "UNKNOWN"
            termination_counts[reason] = termination_counts.get(reason, 0) + 1
            if completed % 10 == 0 or reason not in ("SIMULATION_COMPLETE",):
                print(f"[{completed}] {cfg['name']} seed={seed} -> {record.final_status} ({reason})")

    print(f"\nDONE: completed={completed}, skipped={skipped}, output={trials_path}")
    print(f"termination_reason counts: {termination_counts}")


if __name__ == "__main__":
    main()
