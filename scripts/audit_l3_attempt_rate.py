"""L3 attempt-rate audit (planner-family study, M6c). Reproducible
diagnostic comparing L3's/L2-R's analytical attempt-rate model against
REAL observed data from the already-frozen F02/F03 campaigns - no new
simulations run, no F0*/P0* data modified.

Investigates the exact source of the 2.4-4.3x attempt-rate overestimate
first found in `docs/l3_probabilistic_model.md`, by testing candidate
correction factors (1x, 2x, 3x, 4x classical round trips) against real
`eg_attempts`/`duration_s` data, broken down by hop count and topology.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "results" / "raw"
OUT_DIR = PROJECT_ROOT / "results" / "planner_study" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CLASSICAL_DELAY_S = 1e-4
"""Fixed across F01-F08's scenario configs (configs/campaigns/scenarios/*.yaml,
demos.topologies/*_spec's default `classical_delay_s=1e-4`) - not a
persisted per-row column, so used here as a known, documented constant,
not invented."""

CANDIDATE_ROUND_TRIP_MULTIPLIERS = [1, 2, 3, 4, 5, 6, 7, 7.32, 8, 9, 10, 12, 15]
"""Barret-Kok's real protocol needs 3 coordination rounds (`ent_round`
1->2->3, sequence/entanglement_management/generation/barret_kok.py) -
each involving photon emission + BSM measurement + a classical message.
The ORIGINAL L3 model (docs/l3_probabilistic_model.md) assumed
multiplier=2 (one classical round trip per attempt); this audit searches
a wide range (not just plausible small multipliers) to find where the
ratio actually crosses 1.0, rather than assuming the true value must be
a small, protocol-motivated integer."""


def naive_attempt_rate(reserved_memory_slots: int, round_trip_multiplier: int) -> float:
    return reserved_memory_slots / (round_trip_multiplier * CLASSICAL_DELAY_S)


def load_campaign(name: str) -> pd.DataFrame:
    path = RAW_DIR / name / "trials.csv"
    df = pd.read_csv(path)
    df = df.dropna(subset=["eg_attempts", "duration_s", "reserved_memory_slots"])
    df["observed_attempt_rate"] = df["eg_attempts"] / df["duration_s"]
    return df


def main() -> None:
    frames = []
    for campaign in ["F02_routing", "F03_purification"]:
        df = load_campaign(campaign)
        df["campaign"] = campaign
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    print(f"loaded {len(combined)} trials with eg_attempts data (F02+F03)")

    # --- candidate multiplier fit ---
    fit_rows = []
    for multiplier in CANDIDATE_ROUND_TRIP_MULTIPLIERS:
        combined[f"predicted_rate_m{multiplier}"] = combined["reserved_memory_slots"].apply(
            lambda slots, m=multiplier: naive_attempt_rate(slots, m)
        )
        ratio = combined[f"predicted_rate_m{multiplier}"] / combined["observed_attempt_rate"]
        fit_rows.append({
            "round_trip_multiplier": multiplier,
            "mean_predicted_over_observed_ratio": float(ratio.mean()),
            "median_ratio": float(ratio.median()),
            "std_ratio": float(ratio.std()),
        })
    fit_df = pd.DataFrame(fit_rows)
    print("\n=== Candidate round-trip multiplier fit (ratio should be close to 1.0) ===")
    print(fit_df.to_string(index=False))
    best_multiplier = int(fit_df.loc[(fit_df["mean_predicted_over_observed_ratio"] - 1).abs().idxmin(), "round_trip_multiplier"])
    print(f"\nBest-fitting round_trip_multiplier: {best_multiplier}")

    # --- error by hop count ---
    by_hops = combined.groupby("hop_count").apply(
        lambda g: pd.Series({
            "n": len(g),
            "mean_observed_rate": g["observed_attempt_rate"].mean(),
            "mean_predicted_rate_m2_original": g["predicted_rate_m2"].mean(),
            "ratio_m2_original": g["predicted_rate_m2"].mean() / g["observed_attempt_rate"].mean(),
        }),
        include_groups=False,
    ).reset_index()
    print("\n=== Error by hop count (original multiplier=2 model) ===")
    print(by_hops.to_string(index=False))

    # --- error by topology (scenario) ---
    by_scenario = combined.groupby("scenario").apply(
        lambda g: pd.Series({
            "n": len(g),
            "mean_observed_rate": g["observed_attempt_rate"].mean(),
            "ratio_m2_original": g["predicted_rate_m2"].mean() / g["observed_attempt_rate"].mean(),
        }),
        include_groups=False,
    ).reset_index()
    print("\n=== Error by topology/scenario (original multiplier=2 model) ===")
    print(by_scenario.to_string(index=False))

    # --- attempts vs. successes never confused? (hypothesis 10) ---
    assert (combined["eg_success"] <= combined["eg_attempts"]).all(), (
        "eg_success exceeds eg_attempts somewhere - attempts/successes confusion found!"
    )
    print("\nConfirmed: eg_success <= eg_attempts in every row (no attempts/successes confusion).")

    # --- double-counting check (hypothesis 9): attempts per hop vs. total ---
    # if eg_attempts were double-counted per additional hop, we'd expect
    # observed_attempt_rate to scale with hop_count for the SAME topology
    # family at fixed reserved_memory_slots - check correlation
    single_slot_rate_by_hops = combined.groupby("hop_count")["observed_attempt_rate"].mean()
    print("\nObserved attempt rate by hop_count (checking for suspicious scaling):")
    print(single_slot_rate_by_hops.to_string())

    combined[["campaign", "scenario", "hop_count", "reserved_memory_slots", "duration_s", "eg_attempts",
              "eg_success", "observed_attempt_rate"] + [f"predicted_rate_m{m}" for m in CANDIDATE_ROUND_TRIP_MULTIPLIERS]].to_csv(
        OUT_DIR / "l3_attempt_rate_audit_raw.csv", index=False
    )
    fit_df.to_csv(OUT_DIR / "l3_attempt_rate_audit_fit.csv", index=False)
    by_hops.to_csv(OUT_DIR / "l3_attempt_rate_audit_by_hops.csv", index=False)
    by_scenario.to_csv(OUT_DIR / "l3_attempt_rate_audit_by_scenario.csv", index=False)

    summary = {
        "best_fitting_round_trip_multiplier": best_multiplier,
        "original_model_multiplier": 2,
        "original_model_mean_ratio": float(fit_df[fit_df.round_trip_multiplier == 2]["mean_predicted_over_observed_ratio"].iloc[0]),
        "n_trials_audited": len(combined),
    }
    (OUT_DIR / "l3_attempt_rate_audit_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote audit outputs to {OUT_DIR}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
