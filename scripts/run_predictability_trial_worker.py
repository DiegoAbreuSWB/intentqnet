"""Runs exactly ONE predictability-study trial and writes its result as a
single JSON file - meant to be invoked as a subprocess with an external
wall-clock timeout (`subprocess.run(..., timeout=CAP)`), never imported.

Why a subprocess instead of an in-process call: SeQUeNCe's discrete-event
loop cannot be cooperatively interrupted (no natural checkpoint to test
"have I run too long" between events), and Windows has no `signal.alarm`.
A subprocess is the only way to enforce a hard, OS-level wall-clock cap -
the P02B campaign already demonstrated a real trial can run ~48723s
(~13.5h) if left uninterrupted (see docs/retry_storm_analysis.md), and
M9's whole point is to deliberately probe that same parameter region
further, so an uncapped trial here is not a theoretical risk.

If the parent's subprocess.run(...) times out, it kills this process
directly (no cleanup runs here) - the parent is responsible for recording
a TIMEOUT row with the enforced cap as a censored `simulation_wall_time_s`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from predictability_common import TOPOLOGY_ENDPOINTS, build_intent, build_planner, build_topology  # noqa: E402

from ibqn.demos.environment import collect_environment_info  # noqa: E402
from ibqn.experiments.predictability_records import PredictabilityTrialRecord  # noqa: E402
from ibqn.experiments.predictability_runner import execute_predictability_trial  # noqa: E402
from ibqn.experiments.records import TrialIdentity  # noqa: E402
from ibqn.planning.planners import PlanningContext  # noqa: E402
from ibqn.planning.routing import ShortestHopCountRouting  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--topology-builder", required=True)
    parser.add_argument("--parameter-hash", required=True)
    parser.add_argument("--planner-level", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--min-fidelity", type=float, required=True)
    parser.add_argument("--reserved-memory-slots", type=int, required=True)
    parser.add_argument("--min-delivered-pairs", type=int, required=True)
    parser.add_argument("--duration-s", type=float, required=True)
    parser.add_argument("--allow-purification", type=int, default=1)
    parser.add_argument("--intent-id", default="predictability-intent")
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()

    source, destination = TOPOLOGY_ENDPOINTS[args.topology_builder]
    topology = build_topology(args.topology_builder)
    policy = build_planner(args.planner_level)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting())
    intent = build_intent(
        source=source, destination=destination, min_fidelity=args.min_fidelity,
        reserved_memory_slots=args.reserved_memory_slots, min_delivered_pairs=args.min_delivered_pairs,
        duration_s=args.duration_s, allow_purification=bool(args.allow_purification),
        intent_id=args.intent_id,
    )
    identity = TrialIdentity(
        campaign=args.campaign, scenario=args.scenario, parameter_hash=args.parameter_hash,
        strategy=args.planner_level, seed=args.seed, intent_id=args.intent_id,
    )
    env = collect_environment_info()
    record: PredictabilityTrialRecord = execute_predictability_trial(
        identity, intent, topology, policy, context,
        project_commit=env.project_commit, sequence_commit=env.sequence_commit,
    )
    Path(args.output_json).write_text(
        json.dumps({f: getattr(record, f) for f in PredictabilityTrialRecord.fieldnames()}), encoding="utf-8",
    )


if __name__ == "__main__":
    main()
