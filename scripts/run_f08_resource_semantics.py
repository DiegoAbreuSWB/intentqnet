"""Fase J10 final campaign F08 (resource semantics)."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.experiments.programmatic_campaign import run_programmatic_campaign
from ibqn.demos.topologies import three_node_spec
from ibqn.demos.intents import simple_intent
from ibqn.intent.models import SuccessCondition

SEEDS = list(range(20))
OUTPUT_DIR = str(PROJECT_ROOT / "results")

# min_delivered_pairs=30 as the fixed real success condition; reserved_memory_slots and
# duration_s are swept independently to show they are two genuinely separate levers
# (Fase J2) - not the same knob under two names.
intent = simple_intent(
    intent_id="f08-resource-semantics", source="a", destination="b", min_fidelity=0.6,
    requested_pairs=10, min_delivered_pairs=30, start_time=0.01, duration=0.03,
    success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=30)],
)

summary = run_programmatic_campaign(
    campaign_name="F08_resource_semantics", scenario_name="three_node",
    base_topology=three_node_spec(attenuation_db_per_m=0.01, stop_time_s=0.3, repeater_memories=40, end_memories=20),
    base_intents=[intent],
    parameter_grid={
        "reserved_memory_slots": [2, 10],
        "duration_s": [0.02, 0.05],
    },
    seeds=SEEDS, output_directory=OUTPUT_DIR,
)
print(summary)
print("DONE")
