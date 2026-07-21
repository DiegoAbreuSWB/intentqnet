"""M10.7 analysis: compares L4's predicted_satisfaction_probability (per
configuration, per K) against P12's already-collected empirical P(satisfied)
for the identical (topology, fidelity, duration_s) pair - reusing P12's
data, never re-collecting it. Reports the ROUTE L4 actually selected
alongside the comparison, since a route mismatch (found for
diamond_transition - see docs/predictability_m10/
m10_7_l4_boundary_reference_summary.md) invalidates a same-plan comparison
for that configuration specifically.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
P13_RAW = PROJECT_ROOT / "results" / "predictability_m10" / "raw" / "P13_l4_boundary_reference" / "trials.csv"
P12_RAW = PROJECT_ROOT / "results" / "predictability_m10" / "raw" / "P12_boundary_variability" / "trials.csv"
PROCESSED_DIR = PROJECT_ROOT / "results" / "predictability_m10" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Route ShortestHopCountRouting selects for each linear-chain/heterogeneous
# topology - used to flag when L4 selected a DIFFERENT route than P12's
# ground truth (same-plan comparisons are only valid when routes match).
P12_ROUTE_BY_SCENARIO = {
    "three_node": "a -> r -> b",
    "four_node": "a -> r1 -> r2 -> b",
    "small_mesh": None,  # multi-hop, not pinned down here - not needed (small_mesh hit SIMULATION_ERROR in P13)
    "diamond_heterogeneous": "r1 -> bad -> r3",
}


def main() -> None:
    p13 = pd.read_csv(P13_RAW)
    p12 = pd.read_csv(P12_RAW)

    # empirical P(satisfied) per (scenario, requested_fidelity, duration_s) from P12
    p12_empirical = p12.groupby(["scenario", "requested_fidelity", "duration_s"]).apply(
        lambda g: (g["final_status"] == "SATISFIED").mean(), include_groups=False,
    ).rename("p12_empirical_p_satisfied").reset_index()

    merged = p13.merge(p12_empirical, on=["scenario", "requested_fidelity", "duration_s"], how="left")
    merged["p12_reference_route"] = merged["scenario"].map(P12_ROUTE_BY_SCENARIO)
    merged["same_route_as_p12"] = merged["route"] == merged["p12_reference_route"]
    merged["calibration_error"] = (merged["predicted_satisfaction_probability"] - merged["p12_empirical_p_satisfied"]).abs()

    cols = [
        "scenario", "requested_fidelity", "duration_s", "route", "same_route_as_p12",
        "predicted_satisfaction_probability", "p12_empirical_p_satisfied", "calibration_error",
        "final_status", "planning_time_s",
    ]
    print(merged[cols].to_string(index=False))
    merged[cols].to_csv(PROCESSED_DIR / "l4_boundary_reference_comparison.csv", index=False)

    valid = merged[merged["same_route_as_p12"] & merged["predicted_satisfaction_probability"].notna()]
    summary = {
        "n_total": len(merged),
        "n_valid_same_route_comparisons": len(valid),
        "n_route_mismatches": int((~merged["same_route_as_p12"] & merged["route"].notna() & merged["route"].ne("")).sum()),
        "mean_calibration_error_same_route_only": float(valid["calibration_error"].mean()) if len(valid) else None,
    }
    print(f"\n{json.dumps(summary, indent=2)}")
    (PROCESSED_DIR / "l4_boundary_reference_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {PROCESSED_DIR / 'l4_boundary_reference_comparison.csv'}")


if __name__ == "__main__":
    main()
