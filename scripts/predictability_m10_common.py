"""Shared helpers for M10 scripts - topology/planner resolution by name,
subprocess-with-timeout trial execution (with optional PYTHONHASHSEED
pinning when determinism is enabled). Never imported by, or imports
from, P01-P02B/P03's frozen scripts or M9's own predictability_common.py
(a separate, parallel module - M9's scripts are untouched).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKER_SCRIPT = Path(__file__).resolve().parent / "run_predictability_m10_trial_worker.py"


def build_topology(builder_name: str, *, distance_m: float | None = None):
    from ibqn.demos.topologies import diamond_spec, three_node_spec
    from ibqn.experiments.topology_catalog import linear_chain_spec, small_mesh_spec

    if builder_name == "three_node_spec":
        return three_node_spec(stop_time_s=0.2, **({"distance_m": distance_m} if distance_m else {}))
    if builder_name == "linear_chain_2_spec":
        return linear_chain_spec(2, stop_time_s=0.2, **({"distance_m": distance_m} if distance_m else {}))
    if builder_name == "diamond_spec":
        return diamond_spec(stop_time_s=0.2)
    if builder_name == "small_mesh_spec":
        return small_mesh_spec(stop_time_s=0.2, **({"distance_m": distance_m} if distance_m else {}))
    raise ValueError(f"unknown topology builder '{builder_name}'")


TOPOLOGY_ENDPOINTS = {
    "three_node_spec": ("a", "b"),
    "linear_chain_2_spec": ("a", "b"),
    "diamond_spec": ("r1", "r3"),
    "small_mesh_spec": ("a0", "b3"),
}


def build_planner(level: str, *, admission_threshold: float | None = None):
    from ibqn.planning.planners import (
        ProbabilisticPlanner,
        ProbabilisticResourceAwarePlanner,
        resolve_planner_policy,
    )

    if admission_threshold is not None and level == "L3":
        return ProbabilisticPlanner(admission_threshold=admission_threshold)
    if admission_threshold is not None and level == "L3-R":
        return ProbabilisticResourceAwarePlanner(admission_threshold=admission_threshold)
    return resolve_planner_policy(level)


def build_intent(*, source: str, destination: str, min_fidelity: float, reserved_memory_slots: int,
                  min_delivered_pairs: int, duration_s: float, allow_purification: bool = True,
                  intent_id: str = "m10-intent"):
    from ibqn.demos.intents import simple_intent

    return simple_intent(
        intent_id=intent_id, source=source, destination=destination, min_fidelity=min_fidelity,
        requested_pairs=reserved_memory_slots, min_delivered_pairs=min_delivered_pairs,
        start_time=0.01, duration=duration_s, allow_purification=allow_purification,
    )


_M10_FIELDNAMES = [
    "campaign", "trial_id", "scenario", "parameter_hash", "seed", "intent_id", "planner_level", "planner_name",
    "replay_index", "reserved_memory_slots", "min_delivered_pairs", "requested_fidelity", "duration_s",
    "attenuation_db_per_m", "distance_m", "allow_purification", "route", "hop_count", "feasible", "rejection_reason",
    "predicted_satisfaction_probability", "predicted_delivered_pairs", "predicted_average_fidelity",
    "purification_rounds_estimate", "planning_time_s", "final_status", "satisfied", "delivered_pairs",
    "average_fidelity", "observed_fidelity", "absolute_fidelity_error", "simulation_wall_time_s", "timed_out",
    "timeout_s", "eg_attempts", "eg_success", "ep_attempts", "ep_success", "es_attempts", "es_success",
    "timeline_end_time_s", "trajectory_hash", "determinism_enabled", "master_seed", "execution_seed_used",
    "namespace_seeds_json", "python_random_reseeded", "python_hash_seed_env_value", "project_git_commit",
    "sequence_git_commit", "python_version", "numpy_version", "dependency_versions_json", "platform_system",
    "platform_release", "hostname", "timestamp",
]


def run_trial_with_timeout(
    *, campaign: str, scenario: str, topology_builder: str, parameter_hash: str, planner_level: str,
    seed: int, min_fidelity: float, reserved_memory_slots: int, min_delivered_pairs: int, duration_s: float,
    allow_purification: bool = True, intent_id: str = "m10-intent", timeout_s: float,
    distance_m: float | None = None, replay_index: int = 0,
    determinism_enabled: bool = False, master_seed: int = 0, verify_replay: bool = False,
    admission_threshold: float | None = None,
):
    """Runs one trial in a subprocess with a hard wall-clock cap - same
    rationale as M9's `predictability_common.run_trial_with_timeout`
    (SeQUeNCe's discrete-event loop cannot be cooperatively interrupted).
    When `determinism_enabled`, pins `PYTHONHASHSEED` in the CHILD
    process's environment (the only point at which it can be fixed - see
    `deterministic_context`'s module docstring)."""
    import os

    from ibqn.experiments.deterministic_context import DeterminismConfig, build_subprocess_environment

    with tempfile.TemporaryDirectory() as tmp_dir:
        output_json = Path(tmp_dir) / f"{uuid.uuid4().hex}.json"
        args = [
            sys.executable, str(WORKER_SCRIPT),
            "--campaign", campaign, "--scenario", scenario, "--topology-builder", topology_builder,
            "--parameter-hash", parameter_hash, "--planner-level", planner_level, "--seed", str(seed),
            "--min-fidelity", str(min_fidelity), "--reserved-memory-slots", str(reserved_memory_slots),
            "--min-delivered-pairs", str(min_delivered_pairs), "--duration-s", str(duration_s),
            "--allow-purification", "1" if allow_purification else "0",
            "--intent-id", intent_id, "--output-json", str(output_json),
            "--replay-index", str(replay_index),
            "--determinism-enabled", "1" if determinism_enabled else "0",
            "--master-seed", str(master_seed), "--verify-replay", "1" if verify_replay else "0",
        ]
        if distance_m is not None:
            args += ["--distance-m", str(distance_m)]
        if admission_threshold is not None:
            args += ["--admission-threshold", str(admission_threshold)]

        config = DeterminismConfig(enabled=determinism_enabled, master_seed=master_seed, verify_replay=verify_replay)
        env = build_subprocess_environment(config, base_env=dict(os.environ))

        trial_id = f"{campaign}:{scenario}:{parameter_hash}:{planner_level}:{seed}:{intent_id}:{replay_index}"
        try:
            subprocess.run(args, timeout=timeout_s, capture_output=True, text=True, env=env)
        except subprocess.TimeoutExpired:
            return {
                **{k: None for k in _M10_FIELDNAMES},
                "campaign": campaign, "trial_id": trial_id, "scenario": scenario, "parameter_hash": parameter_hash,
                "seed": seed, "intent_id": intent_id, "planner_level": planner_level, "planner_name": planner_level,
                "replay_index": replay_index, "reserved_memory_slots": reserved_memory_slots,
                "min_delivered_pairs": min_delivered_pairs, "requested_fidelity": min_fidelity,
                "duration_s": duration_s, "distance_m": distance_m, "allow_purification": allow_purification,
                "feasible": True, "final_status": "TIMEOUT", "simulation_wall_time_s": timeout_s,
                "timed_out": True, "timeout_s": timeout_s,
                "python_version": sys.version.split()[0], "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        if not output_json.exists():
            return {
                **{k: None for k in _M10_FIELDNAMES},
                "campaign": campaign, "trial_id": trial_id, "scenario": scenario, "parameter_hash": parameter_hash,
                "seed": seed, "intent_id": intent_id, "planner_level": planner_level, "planner_name": planner_level,
                "replay_index": replay_index, "reserved_memory_slots": reserved_memory_slots,
                "min_delivered_pairs": min_delivered_pairs, "requested_fidelity": min_fidelity,
                "duration_s": duration_s, "distance_m": distance_m, "allow_purification": allow_purification,
                "feasible": False, "final_status": "WORKER_ERROR", "timed_out": False, "timeout_s": timeout_s,
                "python_version": sys.version.split()[0], "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        return json.loads(output_json.read_text(encoding="utf-8"))
