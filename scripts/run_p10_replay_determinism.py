"""P10 (M10.3): replay-determinism validation. Driven by
configs/campaigns/predictability_m10/P10_replay_determinism.yaml. For
each of 8 configurations, runs the SAME nominal trial 10 times with
determinism disabled (testing whether the simulation is ALREADY
deterministic via the per-node seeded generators the M10.1 audit found)
and 10 times with determinism enabled (testing M10.2's new mechanism) -
160 trials total. Every trial runs through the mandatory subprocess
wall-clock cap. Writes only to
results/predictability_m10/raw/P10_replay_determinism/.
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

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability_m10" / "P10_replay_determinism.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    campaign_name = config["name"]
    output_dir = str(PROJECT_ROOT / config["output_directory"])
    trials_path = trials_csv_path(output_dir, campaign_name)
    known_trial_ids = read_trial_ids(trials_path)
    seed = config["seed"]
    master_seed = config["master_seed"]

    completed = 0
    skipped = 0
    for cfg in config["configurations"]:
        for determinism_enabled in (False, True):
            mode_suffix = "det_on" if determinism_enabled else "det_off"
            parameter_hash = compute_parameter_hash({
                "min_fidelity": cfg["min_fidelity"], "duration_s": cfg["duration_s"],
                "reserved_memory_slots": cfg["reserved_memory_slots"],
                "allow_purification": cfg["allow_purification"], "mode": mode_suffix,
                "config_name": cfg["name"],
            })
            for replay_index in range(config["n_replays"]):
                trial_id = (
                    f"{campaign_name}:{cfg['scenario']}:{parameter_hash}:{cfg['planner_level']}:"
                    f"{seed}:m10-intent:{replay_index}"
                )
                if trial_id in known_trial_ids:
                    skipped += 1
                    continue

                row = run_trial_with_timeout(
                    campaign=campaign_name, scenario=cfg["scenario"], topology_builder=cfg["topology_builder"],
                    parameter_hash=parameter_hash, planner_level=cfg["planner_level"], seed=seed,
                    min_fidelity=cfg["min_fidelity"], reserved_memory_slots=cfg["reserved_memory_slots"],
                    min_delivered_pairs=cfg["min_delivered_pairs"], duration_s=cfg["duration_s"],
                    allow_purification=cfg["allow_purification"], timeout_s=config["timeout_s"],
                    replay_index=replay_index, determinism_enabled=determinism_enabled, master_seed=master_seed,
                    verify_replay=True, admission_threshold=cfg.get("admission_threshold"),
                )
                record = PredictabilityM10TrialRecord(**row)
                append_trial_record(trials_path, record)
                known_trial_ids.add(trial_id)
                completed += 1
                print(
                    f"[{completed}] {cfg['name']} mode={mode_suffix} replay={replay_index} -> "
                    f"{record.final_status} hash={record.trajectory_hash}"
                )

    print(f"DONE: completed={completed}, skipped={skipped}, output={trials_path}")


if __name__ == "__main__":
    main()
