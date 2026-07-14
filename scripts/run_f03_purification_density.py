import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.experiments.programmatic_campaign import run_programmatic_campaign
from ibqn.demos.topologies import three_node_spec
from ibqn.demos.intents import simple_intent

SEEDS = list(range(20))
OUTPUT_DIR = str(PROJECT_ROOT / "results")
# Fase K2 supplementary campaign (user-approved): the original F03 sweep
# (0.65/0.70/0.72/0.75) leaves a 0.03-wide gap with no data point between
# 0.72 (still satisfiable) and 0.75 (always REJECTED) for the "automatic"
# policy - denser thresholds inside exactly that gap, same topology,
# seeds, and policies as the original run, so it's a clean paired
# extension, not a new campaign design.
DENSER_FIDELITY_LEVELS = [0.73, 0.735, 0.74, 0.745]
POLICIES = ["disabled", "automatic"]

one_repeater_intent = simple_intent(
    intent_id="f03-1rep", source="a", destination="b", min_fidelity=0.65, requested_pairs=10,
    min_delivered_pairs=10, start_time=0.01, duration=0.1,
)
summary = run_programmatic_campaign(
    campaign_name="F03_purification", scenario_name="three_node_1_repeater",
    base_topology=three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2), base_intents=[one_repeater_intent],
    parameter_grid={"min_fidelity": DENSER_FIDELITY_LEVELS, "purification_policy": POLICIES},
    seeds=SEEDS, output_directory=OUTPUT_DIR,
)
print("density supplement:", summary)
print("DONE")
