"""M10.10 (section 15): corrected, controlled variance decomposition.

M9's original claim ("seed explains only 0.02% of variance") came from a
ONE-WAY eta-squared on P02B's data - explicitly flagged in that analysis
as exploratory, since P02B's `reserved_memory_slots`/`duration_s` were
perfectly collinear (paired into a single "regime" factor) and eta-
squared values from separate one-way analyses do not sum to 100% or
correctly attribute shared variance between correlated factors.

P15's design (M10.9) fixes this: 2 topologies x 3 fidelity levels x 2
duration_s levels x 2 reserved_memory_slots levels x 2 planners, fully
crossed and BALANCED (same 5 seeds - 400-404 - in every cell). This lets
every main effect and interaction be computed via the standard balanced-
design sum-of-squares partition, which is exact (not approximate) for a
balanced design: SS(any subset of factors) = sum over that subset's
level-combinations of n_combo * (mean_in_combo - grand_mean)^2, and pure
interaction SS = SS(joint cells) - SS(each factor alone) - since the
design is balanced, main-effect and interaction sums of squares computed
this way are orthogonal (do not double-count shared variance), unlike
M9's separate one-way eta-squared values.

Primary response: `satisfied` (0/1) - a linear-probability-model ANOVA,
standard practice when a full mixed logistic model isn't available (no
statsmodels dependency in this project - documented, not silently
substituted). Uses all 240 trials (REJECTED counts as satisfied=0).
Secondary response: `delivered_pairs`, restricted to the 70 SATISFIED
trials only (small-sample caveat disclosed, not hidden).
"""
from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = PROJECT_ROOT / "results" / "predictability_m10" / "raw" / "P15_balanced_factorial" / "trials.csv"
PROCESSED_DIR = PROJECT_ROOT / "results" / "predictability_m10" / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

MAIN_FACTORS = ["scenario", "fidelity_level", "duration_s", "reserved_memory_slots", "planner_level"]
REPORTED_INTERACTIONS = [
    ("scenario", "fidelity_level"), ("duration_s", "reserved_memory_slots"),
    ("fidelity_level", "duration_s"), ("scenario", "duration_s"),
]
CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability_m10" / "P15_balanced_factorial.yaml"


def ss_for_factor_combo(df: pd.DataFrame, factors: list[str], response: str, grand_mean: float) -> float:
    """SS explained by the cell means of `factors` (includes all lower-
    order effects nested within this combination) - the balanced-design
    formula: sum over each level-combination of n * (mean - grand_mean)^2."""
    grouped = df.groupby(factors)[response].agg(["mean", "size"])
    return float((grouped["size"] * (grouped["mean"] - grand_mean) ** 2).sum())


def is_balanced(df: pd.DataFrame, factors: list[str]) -> bool:
    """The orthogonal sum-of-squares partition below (SS(A,B joint) -
    SS(A) - SS(B) = pure interaction, non-negative) is only valid for a
    BALANCED design (equal n in every cell). Filtering to a subsample
    (e.g. SATISFIED-only trials) breaks this - cells with different
    admission rates end up with different counts. Checked explicitly
    rather than assumed."""
    counts = df.groupby(factors).size()
    return counts.nunique() == 1


def variance_decomposition(df: pd.DataFrame, response: str) -> dict:
    grand_mean = df[response].mean()
    n_total = len(df)
    ss_total = float(((df[response] - grand_mean) ** 2).sum())
    balanced = is_balanced(df, MAIN_FACTORS)

    main_effect_ss = {f: ss_for_factor_combo(df, [f], response, grand_mean) for f in MAIN_FACTORS}

    interaction_ss = {}
    for a, b in REPORTED_INTERACTIONS:
        ss_ab_joint = ss_for_factor_combo(df, [a, b], response, grand_mean)
        interaction_ss[f"{a}:{b}"] = ss_ab_joint - main_effect_ss[a] - main_effect_ss[b]

    ss_explained = sum(main_effect_ss.values()) + sum(interaction_ss.values())
    ss_residual = ss_total - ss_explained  # includes seed/replicate variation + unmodeled higher-order interactions

    rows = []
    for name, ss in {**main_effect_ss, **interaction_ss}.items():
        rows.append({"term": name, "sum_of_squares": ss, "proportion_of_total_variance": ss / ss_total if ss_total else None})
    rows.append({
        "term": "residual (seed + unmodeled higher-order interactions)",
        "sum_of_squares": ss_residual, "proportion_of_total_variance": ss_residual / ss_total if ss_total else None,
    })

    if not balanced:
        for row in rows:
            if ":" in row["term"] and row["sum_of_squares"] < 0:
                row["caveat"] = (
                    "UNRELIABLE: this subsample is not balanced (unequal cell counts after filtering) - the "
                    "orthogonal SS partition assumed here does not hold; a negative value is the diagnostic "
                    "symptom of that violation, not a real negative variance component. Main effects above "
                    "remain approximately valid; this interaction term should be disregarded."
                )

    return {
        "response": response, "n": n_total, "grand_mean": grand_mean, "ss_total": ss_total,
        "balanced_design": balanced, "terms": rows,
    }


def seed_only_contribution(df: pd.DataFrame, response: str) -> float:
    """Isolates JUST the seed main effect (marginalizing over every other
    factor) - the direct, controlled analog of M9's original one-way
    eta-squared claim, computed on THIS balanced design instead."""
    grand_mean = df[response].mean()
    ss_total = float(((df[response] - grand_mean) ** 2).sum())
    ss_seed = ss_for_factor_combo(df, ["seed"], response, grand_mean)
    return ss_seed / ss_total if ss_total else float("nan")


def build_fidelity_level_map() -> dict[tuple[str, float], str]:
    """`requested_fidelity` is a topology-specific raw value (three_node:
    0.65/0.72/0.78; four_node: 0.53/0.58/0.63) - NESTED within `scenario`,
    not crossed with it. The actually-crossed factor is the abstract
    `fidelity_level` label (low/medium/high) - using the raw value
    directly as an ANOVA factor alongside `scenario` double-counts
    variance and produces a nonsensical negative interaction SS (found
    and fixed while building this analysis - see module docstring)."""
    import yaml

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    mapping = {}
    for topo_cfg in config["topologies"]:
        for level, value in topo_cfg["fidelity_levels"].items():
            mapping[(topo_cfg["scenario"], value)] = level
    return mapping


def main() -> None:
    if not RAW_PATH.exists():
        raise FileNotFoundError(f"{RAW_PATH} not found - run scripts/run_p15_balanced_factorial.py first")
    df = pd.read_csv(RAW_PATH)
    df["satisfied_numeric"] = (df["final_status"] == "SATISFIED").astype(float)

    fidelity_map = build_fidelity_level_map()
    df["fidelity_level"] = df.apply(lambda r: fidelity_map[(r["scenario"], r["requested_fidelity"])], axis=1)
    print(f"loaded {len(df)} trials")

    print("\n=== PRIMARY: variance decomposition of `satisfied` (0/1), n=240 ===")
    primary = variance_decomposition(df, "satisfied_numeric")
    primary_df = pd.DataFrame(primary["terms"]).sort_values("proportion_of_total_variance", ascending=False)
    print(primary_df.to_string(index=False))
    seed_prop_primary = seed_only_contribution(df, "satisfied_numeric")
    print(f"\nSeed-only contribution (marginalized over all other factors): {seed_prop_primary:.5f} ({seed_prop_primary*100:.3f}%)")

    satisfied_only = df[df["final_status"] == "SATISFIED"].copy()
    print(f"\n=== SECONDARY: variance decomposition of `delivered_pairs`, n={len(satisfied_only)} (SATISFIED trials only) ===")
    if len(satisfied_only) >= 10:
        secondary = variance_decomposition(satisfied_only, "delivered_pairs")
        secondary_df = pd.DataFrame(secondary["terms"]).sort_values("proportion_of_total_variance", ascending=False)
        print(secondary_df.to_string(index=False))
        seed_prop_secondary = seed_only_contribution(satisfied_only, "delivered_pairs")
        print(f"\nSeed-only contribution: {seed_prop_secondary:.5f} ({seed_prop_secondary*100:.3f}%)")
    else:
        secondary_df = pd.DataFrame()
        seed_prop_secondary = None
        print("Too few SATISFIED trials for a meaningful secondary decomposition - skipped, disclosed not hidden.")

    primary_df.to_csv(PROCESSED_DIR / "p15_variance_decomposition_satisfied.csv", index=False)
    if not secondary_df.empty:
        secondary_df.to_csv(PROCESSED_DIR / "p15_variance_decomposition_delivered_pairs.csv", index=False)

    summary = {
        "n_total": len(df), "n_satisfied": len(satisfied_only),
        "seed_contribution_satisfied_response": seed_prop_primary,
        "seed_contribution_delivered_pairs_response": seed_prop_secondary,
        "m9_original_claim": "seed explains only 0.02% of delivered_pairs variance (one-way eta-squared, P02B data)",
    }
    (PROCESSED_DIR / "p15_variance_decomposition_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote outputs to {PROCESSED_DIR}")


if __name__ == "__main__":
    main()
