"""Fase J10 final campaign F02 (routing) - two topologies via
run_programmatic_campaign (see docs/results_provenance.md, manifest
`blocks`)."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.experiments.programmatic_campaign import run_programmatic_campaign
from ibqn.demos.topologies import diamond_spec
from ibqn.demos.intents import diamond_intent, simple_intent
from ibqn.experiments.topology_catalog import small_mesh_spec

SEEDS = list(range(20))
OUTPUT_DIR = str(PROJECT_ROOT / "results")
STRATEGIES = ["shortest_hop_count", "least_loss", "highest_fidelity"]

# T2: diamond (heterogeneous, strategies genuinely diverge)
diamond_summary = run_programmatic_campaign(
    campaign_name="F02_routing", scenario_name="diamond_heterogeneous",
    base_topology=diamond_spec(stop_time_s=0.2), base_intents=[diamond_intent(requested_pairs=10, min_fidelity=0.6)],
    parameter_grid={"routing_strategy": STRATEGIES}, seeds=SEEDS, output_directory=OUTPUT_DIR,
)
print("diamond:", diamond_summary)

# T3: small mesh (a0 -> b3, multiple candidate paths)
mesh_intent = simple_intent(
    intent_id="f02-mesh", source="a0", destination="b3", min_fidelity=0.3, requested_pairs=10,
    min_delivered_pairs=10, start_time=0.01, duration=0.15,
)
mesh_summary = run_programmatic_campaign(
    campaign_name="F02_routing", scenario_name="small_mesh",
    base_topology=small_mesh_spec(stop_time_s=0.2), base_intents=[mesh_intent],
    parameter_grid={"routing_strategy": STRATEGIES}, seeds=SEEDS, output_directory=OUTPUT_DIR,
)
print("mesh:", mesh_summary)

print("DONE")
