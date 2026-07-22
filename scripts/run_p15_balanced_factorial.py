"""P15 (M10.9): balanced factorial study. Driven by
configs/campaigns/predictability_m10/P15_balanced_factorial.yaml.
Resume-safe. Writes only to
results/predictability_m10/raw/P15_balanced_factorial/.
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

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability_m10" / "P15_balanced_factorial.yaml"


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    campaign_name = config["name"]
    output_dir = str(PROJECT_ROOT / config["output_directory"])
    trials_path = trials_csv_path(output_dir, campaign_name)
    known_trial_ids = read_trial_ids(trials_path)

    completed = 0
    skipped = 0
    n_cells = 0
    for topo_cfg in config["topologies"]:
        for fidelity_level, min_fidelity in topo_cfg["fidelity_levels"].items():
            for duration_s in config["duration_s_levels"]:
                for reserved_memory_slots in config["reserved_memory_slots_levels"]:
                    for planner_level in config["planners"]:
                        n_cells += 1
                        parameter_hash = compute_parameter_hash({
                            "min_fidelity": min_fidelity, "duration_s": duration_s,
                            "reserved_memory_slots": reserved_memory_slots, "topology": topo_cfg["name"],
                            "fidelity_level": fidelity_level,
                        })
                        for seed in config["seeds"]:
                            trial_id = (
                                f"{campaign_name}:{topo_cfg['scenario']}:{parameter_hash}:{planner_level}:"
                                f"{seed}:m10-intent:0"
                            )
                            if trial_id in known_trial_ids:
                                skipped += 1
                                continue

                            row = run_trial_with_timeout(
                                campaign=campaign_name, scenario=topo_cfg["scenario"],
                                topology_builder=topo_cfg["topology_builder"], parameter_hash=parameter_hash,
                                planner_level=planner_level, seed=seed, min_fidelity=min_fidelity,
                                reserved_memory_slots=reserved_memory_slots, min_delivered_pairs=10,
                                duration_s=duration_s, timeout_s=config["timeout_s"],
                            )
                            record = PredictabilityM10TrialRecord(**row)
                            append_trial_record(trials_path, record)
                            known_trial_ids.add(trial_id)
                            completed += 1
                            if completed % 20 == 0:
                                print(
                                    f"[{completed}] {topo_cfg['name']} fid={fidelity_level}({min_fidelity}) "
                                    f"dur={duration_s} mem={reserved_memory_slots} planner={planner_level} "
                                    f"seed={seed} -> {record.final_status}"
                                )

    print(f"\nDONE: cells={n_cells}, completed={completed}, skipped={skipped}, output={trials_path}")


if __name__ == "__main__":
    main()
