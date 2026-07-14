"""Fase J10 final campaign F07 (fidelity estimators)."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.experiments.programmatic_campaign import run_programmatic_campaign
from ibqn.demos.topologies import diamond_spec
from ibqn.demos.intents import diamond_intent

SEEDS = list(range(20))
OUTPUT_DIR = str(PROJECT_ROOT / "results")

summary = run_programmatic_campaign(
    campaign_name="F07_estimators", scenario_name="diamond_heterogeneous",
    base_topology=diamond_spec(stop_time_s=0.2), base_intents=[diamond_intent(requested_pairs=10, min_fidelity=0.6)],
    parameter_grid={
        "routing_strategy": ["shortest_hop_count", "least_loss", "highest_fidelity"],
        "fidelity_estimator": ["conservative_min", "sequence_consistent"],
    },
    seeds=SEEDS, output_directory=OUTPUT_DIR,
)
print(summary)
print("DONE")
