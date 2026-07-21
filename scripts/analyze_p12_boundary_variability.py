"""M10.6 analysis (sections 9-10): per-configuration predictability
measures and the Bayes-optimal configuration-conditional empirical lower
bound. Reads only results/predictability_m10/raw/
P12_boundary_variability/trials.csv - never touches any other campaign's
data.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "results" / "predictability_m10" / "raw" / "P12_boundary_variability" / "trials.csv"
PROCESSED_DIR = PROJECT_ROOT / "results" / "predictability_m10" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability_m10" / "P12_boundary_variability.yaml"


def wilson_ci(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def classify_region(p_hat: float, ci_lo: float, ci_hi: float) -> str:
    if ci_lo >= 0.95:
        return "ROBUST_SUCCESS"
    if ci_hi <= 0.05:
        return "ROBUST_FAILURE"
    if p_hat >= 0.75:
        return "LIKELY_SUCCESS"
    if p_hat >= 0.25:
        return "TRANSITION"
    return "LIKELY_FAILURE"


def binary_entropy(p: float) -> float:
    """H(Y|X=configuration) in bits - 0 when p in {0,1} (perfectly
    predictable within this configuration), 1 at p=0.5 (maximal binary
    uncertainty). Called `empirical within-configuration outcome
    uncertainty under the evaluated SeQUeNCe model` throughout this
    project's docs (never "irreducible uncertainty" unqualified - section
    9's explicit wording requirement)."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return float(-p * np.log2(p) - (1 - p) * np.log2(1 - p))


def load_config_names() -> dict[str, tuple[str, str]]:
    """Maps `parameter_hash` back to `(config_name, expected_region)` -
    the raw trials.csv only carries the hash, not the human-readable name."""
    from ibqn.experiments.sweeps import compute_parameter_hash

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    mapping = {}
    for cfg in config["configurations"]:
        ph = compute_parameter_hash({
            "min_fidelity": cfg["min_fidelity"], "duration_s": cfg["duration_s"],
            "reserved_memory_slots": config["reserved_memory_slots"], "config_name": cfg["name"],
        })
        mapping[ph] = (cfg["name"], cfg["expected_region"])
    return mapping


def main() -> None:
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "src"))

    if not RAW_PATH.exists():
        raise FileNotFoundError(f"{RAW_PATH} not found - run scripts/run_p12_boundary_variability.py first")
    df = pd.read_csv(RAW_PATH)
    print(f"loaded {len(df)} trials")

    name_map = load_config_names()
    df["config_name"] = df["parameter_hash"].map(lambda h: name_map.get(h, (h, "?"))[0])
    df["expected_region"] = df["parameter_hash"].map(lambda h: name_map.get(h, (h, "?"))[1])

    rows = []
    for (config_name, expected_region), group in df.groupby(["config_name", "expected_region"]):
        n = len(group)
        satisfied = (group["final_status"] == "SATISFIED")
        n_satisfied = int(satisfied.sum())
        p_hat = n_satisfied / n if n else 0.0
        ci_lo, ci_hi = wilson_ci(n_satisfied, n)
        region = classify_region(p_hat, ci_lo, ci_hi)

        delivered = group["delivered_pairs"].dropna()
        fidelity = group["average_fidelity"].dropna()
        wall = group["simulation_wall_time_s"].dropna()
        n_timeout = int(group["timed_out"].sum())

        rows.append({
            "config_name": config_name, "expected_region": expected_region, "observed_region": region,
            "region_match": region == expected_region,
            "scenario": group["scenario"].iloc[0], "n": n, "n_satisfied": n_satisfied,
            "p_satisfied": p_hat, "ci_lo": ci_lo, "ci_hi": ci_hi,
            "binary_entropy_bits": binary_entropy(p_hat),
            "bayes_empirical_lower_bound": min(p_hat, 1 - p_hat),
            "mean_delivered_pairs": float(delivered.mean()) if len(delivered) else None,
            "std_delivered_pairs": float(delivered.std()) if len(delivered) > 1 else None,
            "cv_delivered_pairs": float(delivered.std() / delivered.mean()) if len(delivered) > 1 and delivered.mean() else None,
            "mean_fidelity": float(fidelity.mean()) if len(fidelity) else None,
            "std_fidelity": float(fidelity.std()) if len(fidelity) > 1 else None,
            "p_timeout": n_timeout / n if n else 0.0,
            "wall_p50": float(wall.quantile(0.5)) if len(wall) else None,
            "wall_p90": float(wall.quantile(0.9)) if len(wall) else None,
            "wall_p95": float(wall.quantile(0.95)) if len(wall) else None,
            "wall_p99": float(wall.quantile(0.99)) if len(wall) else None,
            "wall_max": float(wall.max()) if len(wall) else None,
        })

    report = pd.DataFrame(rows).sort_values(["scenario", "config_name"])
    report.to_csv(PROCESSED_DIR / "boundary_variability_report.csv", index=False)
    print("\n=== Per-configuration predictability measures ===")
    print(report[["config_name", "scenario", "expected_region", "observed_region", "n", "p_satisfied", "ci_lo", "ci_hi", "binary_entropy_bits", "p_timeout"]].to_string(index=False))

    # Bayes-optimal empirical lower bound - two aggregations (section 10)
    equal_weighted = float(report["bayes_empirical_lower_bound"].mean())
    trial_weighted = float((report["bayes_empirical_lower_bound"] * report["n"]).sum() / report["n"].sum())
    print(f"\nBayes-style empirical configuration-conditional lower bound:")
    print(f"  equal-weighted-by-configuration: {equal_weighted:.4f}")
    print(f"  weighted-by-trial-count: {trial_weighted:.4f}")

    region_coverage = report["observed_region"].value_counts().to_dict()
    print(f"\nRegion coverage (observed, at collected seed counts): {region_coverage}")

    summary = {
        "n_configurations": len(report), "n_trials_total": len(df),
        "bayes_lower_bound_equal_weighted": equal_weighted, "bayes_lower_bound_trial_weighted": trial_weighted,
        "region_coverage": {k: int(v) for k, v in region_coverage.items()},
        "n_region_mismatches": int((~report["region_match"]).sum()),
    }
    (PROCESSED_DIR / "boundary_variability_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote {PROCESSED_DIR / 'boundary_variability_report.csv'}")


if __name__ == "__main__":
    main()
