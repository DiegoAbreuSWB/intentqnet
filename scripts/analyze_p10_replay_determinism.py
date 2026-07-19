"""M10.3 analysis: classifies each (configuration, determinism-mode)
group of 10 replays as BITWISE_IDENTICAL, LOGICALLY_IDENTICAL, or
NONDETERMINISTIC. Reads only results/predictability_m10/raw/
P10_replay_determinism/trials.csv (produced by
scripts/run_p10_replay_determinism.py) - never touches P01-P02B/P03/M9
data.

Classification (wall-clock time is NEVER used as evidence - see
docs/predictability_m10/randomness_audit.md section 5):
- BITWISE_IDENTICAL: every replay has the exact same final_status,
  delivered_pairs, and UNROUNDED average_fidelity/timeline_end_time_s
  (float equality, not just trajectory_hash agreement).
- LOGICALLY_IDENTICAL: every replay has the same trajectory_hash (a
  wall-clock-free fingerprint tolerating only last-bit float noise), but
  raw float equality is not exact - OR every replay reached the same
  final_status with no trajectory to hash (REJECTED/TIMEOUT/
  SIMULATION_ERROR consistently).
- NONDETERMINISTIC: replays disagree on final_status or trajectory_hash.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "results" / "predictability_m10" / "raw" / "P10_replay_determinism" / "trials.csv"
PROCESSED_DIR = PROJECT_ROOT / "results" / "predictability_m10" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def classify_group(group: pd.DataFrame) -> dict:
    n = len(group)
    statuses = group["final_status"].unique().tolist()
    hashes = group["trajectory_hash"].dropna().unique().tolist()

    if len(statuses) > 1:
        classification = "NONDETERMINISTIC"
        reason = f"final_status disagreement across replays: {statuses}"
    elif group["trajectory_hash"].isna().all():
        # no trajectory to hash (e.g. every replay REJECTED/TIMEOUT) -
        # consistent categorical outcome across all replays is still
        # informative, weaker evidence than a trajectory hash match
        classification = "LOGICALLY_IDENTICAL"
        reason = f"all {n} replays reached '{statuses[0]}' with no trajectory to hash (consistent categorical outcome)"
    elif len(hashes) == 1:
        # check strict bitwise equality on the raw (unrounded) fields too
        exact_fields = ["delivered_pairs", "average_fidelity", "timeline_end_time_s"]
        bitwise = all(group[f].nunique(dropna=False) == 1 for f in exact_fields)
        classification = "BITWISE_IDENTICAL" if bitwise else "LOGICALLY_IDENTICAL"
        reason = (
            "all replays share one trajectory_hash and identical raw field values" if bitwise else
            "all replays share one trajectory_hash, but raw float values differ at higher precision than the hash's 9-decimal rounding"
        )
    else:
        classification = "NONDETERMINISTIC"
        reason = f"{len(hashes)} distinct trajectory_hash values across {n} replays: {hashes}"

    return {
        "classification": classification, "reason": reason, "n_replays": n,
        "distinct_final_statuses": statuses, "distinct_trajectory_hashes": len(hashes),
    }


def main() -> None:
    if not RAW_PATH.exists():
        raise FileNotFoundError(f"{RAW_PATH} not found - run scripts/run_p10_replay_determinism.py first")
    df = pd.read_csv(RAW_PATH)
    print(f"loaded {len(df)} trials")

    rows = []
    for (scenario, parameter_hash, planner_level, determinism_enabled), group in df.groupby(
        ["scenario", "parameter_hash", "planner_level", "determinism_enabled"]
    ):
        result = classify_group(group)
        rows.append({
            "scenario": scenario, "parameter_hash": parameter_hash, "planner_level": planner_level,
            "determinism_enabled": determinism_enabled, **result,
        })

    report = pd.DataFrame(rows)
    report.to_csv(PROCESSED_DIR / "replay_determinism_report.csv", index=False)
    print("\n=== Replay determinism report ===")
    print(report[["scenario", "planner_level", "determinism_enabled", "classification", "n_replays", "reason"]].to_string(index=False))

    n_nondeterministic = int((report["classification"] == "NONDETERMINISTIC").sum())
    overall_verdict = "BLOCKED_BY_NONDETERMINISM" if n_nondeterministic > 0 else "REPRODUCIBLE"
    print(f"\nOverall verdict: {overall_verdict} ({n_nondeterministic} nondeterministic group(s) out of {len(report)})")

    summary = {
        "overall_verdict": overall_verdict, "n_groups": len(report),
        "n_nondeterministic": n_nondeterministic,
        "n_bitwise_identical": int((report["classification"] == "BITWISE_IDENTICAL").sum()),
        "n_logically_identical": int((report["classification"] == "LOGICALLY_IDENTICAL").sum()),
    }
    (PROCESSED_DIR / "replay_determinism_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {PROCESSED_DIR / 'replay_determinism_report.csv'}")


if __name__ == "__main__":
    main()
