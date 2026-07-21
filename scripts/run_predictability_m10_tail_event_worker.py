"""M10.8: runs exactly ONE tail-event-study trial, with heartbeat
instrumentation, and writes its result as a single JSON file - a
subprocess target, never imported. See M9/M10's other worker scripts for
the general "why a subprocess" rationale (SeQUeNCe's discrete-event loop
cannot be cooperatively interrupted). The heartbeat JSONL file is written
to a PERSISTENT path (not inside a temp directory that gets cleaned up),
specifically so it survives being read back by the parent process even
when this worker is killed by the wall-clock timeout mid-simulation.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from predictability_m10_common import TOPOLOGY_ENDPOINTS, build_intent, build_planner, build_topology  # noqa: E402

from ibqn.demos.environment import collect_environment_info  # noqa: E402
from ibqn.experiments.deterministic_context import DeterminismConfig  # noqa: E402
from ibqn.experiments.predictability_m10_records import PredictabilityM10TrialRecord  # noqa: E402
from ibqn.experiments.predictability_m10_tail_event_runner import execute_tail_event_trial  # noqa: E402
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
    parser.add_argument("--intent-id", default="m10-intent")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--heartbeat-path", required=True)
    parser.add_argument("--heartbeat-interval-s", type=float, default=2.0)
    parser.add_argument("--max-events", type=int, default=None)
    parser.add_argument("--admission-threshold", type=float, default=None)
    args = parser.parse_args()

    source, destination = TOPOLOGY_ENDPOINTS[args.topology_builder]
    topology = build_topology(args.topology_builder)
    policy = build_planner(args.planner_level, admission_threshold=args.admission_threshold)
    context = PlanningContext(routing_strategy=ShortestHopCountRouting(), topology_spec=topology)
    intent = build_intent(
        source=source, destination=destination, min_fidelity=args.min_fidelity,
        reserved_memory_slots=args.reserved_memory_slots, min_delivered_pairs=args.min_delivered_pairs,
        duration_s=args.duration_s, allow_purification=bool(args.allow_purification), intent_id=args.intent_id,
    )
    identity = TrialIdentity(
        campaign=args.campaign, scenario=args.scenario, parameter_hash=args.parameter_hash,
        strategy=args.planner_level, seed=args.seed, intent_id=args.intent_id,
    )
    env = collect_environment_info()
    record: PredictabilityM10TrialRecord = execute_tail_event_trial(
        identity, intent, topology, policy, context, env=env, determinism=DeterminismConfig(enabled=False),
        heartbeat_path=args.heartbeat_path, heartbeat_interval_s=args.heartbeat_interval_s,
        max_events=args.max_events,
    )
    Path(args.output_json).write_text(
        json.dumps({f: getattr(record, f) for f in PredictabilityM10TrialRecord.fieldnames()}), encoding="utf-8",
    )


if __name__ == "__main__":
    main()
