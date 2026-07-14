"""Fase J10 final campaign F06 (overhead at scale) - ad-hoc script, not
run_programmatic_campaign/CampaignRunner (see docs/results_provenance.md).
Diamond topology, 3 conditions x 20 seeds.
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd

from ibqn.demos.intents import diamond_intent
from ibqn.demos.topologies import diamond_spec
from ibqn.experiments.baselines import run_native_sequence_baseline, run_static_provisioning_baseline
from ibqn.experiments.overhead import run_instrumented_trial
from ibqn.planning.routing import ShortestHopCountRouting

SEEDS = list(range(20))
spec = diamond_spec(stop_time_s=0.2)
intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

rows = []
for seed in SEEDS:
    timing, evaluation = run_instrumented_trial(intent, spec, seed=seed, routing_strategy=ShortestHopCountRouting(), reconciliation_enabled=True)
    rows.append({
        "condition": "ibqn_instrumented", "seed": seed,
        "intent_parsing_wall_time_s": timing.intent_parsing_wall_time_s,
        "intent_validation_wall_time_s": timing.intent_validation_wall_time_s,
        "capability_extraction_wall_time_s": timing.capability_extraction_wall_time_s,
        "planning_wall_time_s": timing.planning_wall_time_s,
        "deployment_wall_time_s": timing.deployment_wall_time_s,
        "assurance_wall_time_s": timing.assurance_wall_time_s,
        "reconciliation_decision_wall_time_s": timing.reconciliation_decision_wall_time_s,
        "simulation_wall_time_s": timing.simulation_wall_time_s,
        "total_orchestration_wall_time_s": timing.total_orchestration_wall_time_s,
        "total_trial_wall_time_s": timing.total_trial_wall_time_s,
        "orchestration_overhead_ratio": timing.orchestration_overhead_ratio,
        "planning_overhead_ratio": timing.planning_overhead_ratio,
    })

    native = run_native_sequence_baseline(spec, intent, seed=seed)
    rows.append({
        "condition": "native_sequence", "seed": seed,
        "planning_wall_time_s": native.planning_wall_time_s,
        "simulation_wall_time_s": native.simulation_wall_time_s,
        "total_trial_wall_time_s": native.total_wall_time_s,
        "orchestration_overhead_ratio": (native.total_wall_time_s - native.simulation_wall_time_s) / native.total_wall_time_s if native.total_wall_time_s else None,
        "planning_overhead_ratio": native.planning_wall_time_s / native.total_wall_time_s if native.total_wall_time_s else None,
    })

    static = run_static_provisioning_baseline(spec, intent, seed=seed, routing_strategy=ShortestHopCountRouting())
    rows.append({
        "condition": "static_provisioning", "seed": seed,
        "planning_wall_time_s": static.planning_wall_time_s,
        "simulation_wall_time_s": static.simulation_wall_time_s,
        "total_trial_wall_time_s": static.total_wall_time_s,
        "orchestration_overhead_ratio": (static.total_wall_time_s - static.simulation_wall_time_s) / static.total_wall_time_s if static.total_wall_time_s else None,
        "planning_overhead_ratio": static.planning_wall_time_s / static.total_wall_time_s if static.total_wall_time_s else None,
    })

df = pd.DataFrame(rows)
out_dir = PROJECT_ROOT / "results" / "raw" / "F06_overhead"
out_dir.mkdir(parents=True, exist_ok=True)
df.to_csv(out_dir / "trials.csv", index=False)
print(df.groupby("condition")[["planning_wall_time_s", "simulation_wall_time_s", "total_trial_wall_time_s", "orchestration_overhead_ratio", "planning_overhead_ratio"]].mean())
print("wrote", len(df), "rows")
print("DONE")
