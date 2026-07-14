"""Fase J10 final campaign F03 (purification) - original 4 fidelity
thresholds. See scripts/run_f03_purification_density.py for the Fase K2
supplementary densification of three_node_1_repeater (docs/
results_provenance.md, docs/false_rejection_root_cause.md)."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.experiments.programmatic_campaign import run_programmatic_campaign
from ibqn.demos.topologies import three_node_spec
from ibqn.demos.intents import simple_intent
from ibqn.experiments.topology_catalog import linear_chain_spec

SEEDS = list(range(20))
OUTPUT_DIR = str(PROJECT_ROOT / "results")
FIDELITY_LEVELS = [0.65, 0.70, 0.72, 0.75]
POLICIES = ["disabled", "automatic"]

# 1 repeater (matches C02's established calibration)
one_repeater_intent = simple_intent(
    intent_id="f03-1rep", source="a", destination="b", min_fidelity=0.65, requested_pairs=10,
    min_delivered_pairs=10, start_time=0.01, duration=0.1,
)
summary_1 = run_programmatic_campaign(
    campaign_name="F03_purification", scenario_name="three_node_1_repeater",
    base_topology=three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2), base_intents=[one_repeater_intent],
    parameter_grid={"min_fidelity": FIDELITY_LEVELS, "purification_policy": POLICIES},
    seeds=SEEDS, output_directory=OUTPUT_DIR,
)
print("1 repeater:", summary_1)

# 2 repeaters (checks whether the purification ceiling holds with more swaps)
two_repeater_intent = simple_intent(
    intent_id="f03-2rep", source="a", destination="b", min_fidelity=0.65, requested_pairs=10,
    min_delivered_pairs=10, start_time=0.01, duration=0.1,
)
summary_2 = run_programmatic_campaign(
    campaign_name="F03_purification", scenario_name="linear_chain_2_repeaters",
    base_topology=linear_chain_spec(2, attenuation_db_per_m=1e-5, stop_time_s=0.2), base_intents=[two_repeater_intent],
    parameter_grid={"min_fidelity": FIDELITY_LEVELS, "purification_policy": POLICIES},
    seeds=SEEDS, output_directory=OUTPUT_DIR,
)
print("2 repeaters:", summary_2)

print("DONE")
