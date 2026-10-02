"""Processed tables for the calibrated ("realistic") campaign suite.

Reads the raw outputs of `scripts/realistic/run_suite.py` and the two
audits, and writes one processed CSV per result the manuscript reports,
plus a human-readable `SUMMARY.md`. No simulation is run and no raw file is
modified. Campaigns that have not been run yet are skipped with a note.

  python scripts/realistic/analyze_suite.py [--root results/realistic]

Statistics (docs/realistic_campaigns.md):
- proportions (satisfaction, recovery, false feasibility, false rejection):
  Wilson score interval, 95%;
- means (delivered pairs, fidelity): Student-t interval, 95%, over seeds;
- false-feasibility rate: VIOLATED / (SATISFIED + VIOLATED) among admitted
  intents that executed; false-rejection rate: oracle-satisfiable /
  oracle-tested among rejected intents. Different populations, never
  combined.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = PROJECT_ROOT / "results" / "realistic"
HARDWARE_ORDER = ["literature", "theoretical_ops"]
PLANNER_ORDER = ["L1", "L2", "L2-R", "L2-RB", "L3", "L3-R", "L3-RB", "L4"]
L3_FAMILY = ["L3", "L3-R", "L3-RB"]


# --------------------------------------------------------------------------
# statistics
# --------------------------------------------------------------------------

def wilson(successes: float, n: float, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval - the formula used throughout this project
    (scripts/paper_ibqn/generate_processed_data.py)."""
    if n == 0:
        return float("nan"), float("nan")
    p = successes / n
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, center - half), min(1.0, center + half)


def mean_ci(values, confidence: float = 0.95) -> tuple[float, float, float, int]:
    """(mean, low, high, n) with a Student-t interval; the interval collapses
    to the mean when fewer than two values exist or they are all equal."""
    data = pd.Series(values, dtype=float).dropna()
    n = len(data)
    if n == 0:
        return float("nan"), float("nan"), float("nan"), 0
    mean = float(data.mean())
    if n < 2 or data.std(ddof=1) == 0:
        return mean, mean, mean, n
    half = float(stats.t.ppf(1 - (1 - confidence) / 2, n - 1) * data.std(ddof=1) / np.sqrt(n))
    return mean, mean - half, mean + half, n


def proportion_columns(prefix: str, successes: int, n: int) -> dict:
    low, high = wilson(successes, n)
    return {
        f"{prefix}_count": int(successes), f"{prefix}_of": int(n),
        f"{prefix}_rate": successes / n if n else float("nan"), f"{prefix}_ci_low": low, f"{prefix}_ci_high": high,
    }


def mean_columns(prefix: str, values) -> dict:
    mean, low, high, n = mean_ci(values)
    return {f"{prefix}_mean": mean, f"{prefix}_ci_low": low, f"{prefix}_ci_high": high, f"{prefix}_n": n}


def split_scenario(frame: pd.DataFrame) -> pd.DataFrame:
    """`scenario` is `<topology>@<hardware>` in the programmatic campaigns."""
    frame = frame.copy()
    parts = frame["scenario"].str.split("@", n=1, expand=True)
    frame["topology"], frame["hardware"] = parts[0], parts[1]
    return frame


def status_counts(series: pd.Series) -> dict:
    counts = series.value_counts()
    return {f"n_{status.lower()}": int(counts.get(status, 0))
            for status in ("SATISFIED", "VIOLATED", "REJECTED", "FAILED", "SIMULATION_ERROR")}


def as_bool(series: pd.Series) -> pd.Series:
    return series.map(lambda v: str(v).strip().lower() in ("true", "1", "1.0") if pd.notna(v) else False)


# --------------------------------------------------------------------------
# per-campaign tables
# --------------------------------------------------------------------------

def routing(root: Path) -> dict[str, pd.DataFrame]:
    raw = split_scenario(pd.read_csv(root / "raw" / "R02_routing" / "trials.csv"))
    rows = []
    for (hardware, topology, strategy), g in raw.groupby(["hardware", "topology", "routing_strategy"]):
        rows.append(dict(
            hardware=hardware, topology=topology, routing_strategy=strategy, seeds=len(g),
            route=g["route"].mode().iat[0], distinct_routes=g["route"].nunique(), hop_count=int(g["hop_count"].mode().iat[0]),
            requested_fidelity=g["requested_fidelity"].iat[0], min_delivered_pairs=int(g["min_delivered_pairs"].iat[0]),
            **proportion_columns("satisfied", int(as_bool(g["satisfied"]).sum()), len(g)),
            **mean_columns("delivered_pairs", g["delivered_pairs"]),
            **mean_columns("average_fidelity", g["average_fidelity"]),
            estimated_fidelity=g["estimated_fidelity"].mean(),
        ))
    return {"r02_routing": pd.DataFrame(rows)}


def purification(root: Path) -> dict[str, pd.DataFrame]:
    raw = split_scenario(pd.read_csv(root / "raw" / "R03_purification" / "trials.csv"))
    keys = ["hardware", "topology", "requested_fidelity", "purification_policy"]
    rows = []
    for key, g in raw.groupby(keys):
        executed = g[g["final_status"].isin(["SATISFIED", "VIOLATED"])]
        rows.append(dict(
            zip(keys, key), seeds=len(g), **status_counts(g["final_status"]),
            purification_mode=executed["purification_mode"].mode().iat[0] if len(executed) else None,
            estimated_fidelity=g["estimated_fidelity"].mean(),
            **proportion_columns("satisfied", int((g["final_status"] == "SATISFIED").sum()), len(g)),
            **mean_columns("delivered_pairs", executed["delivered_pairs"]),
            **mean_columns("average_fidelity", executed["average_fidelity"]),
            purification_rounds_mean=executed["ep_attempts"].mean() if len(executed) else float("nan"),
            purification_successes_mean=executed["ep_success"].mean() if len(executed) else float("nan"),
            discarded_pairs_mean=executed["discarded_pairs"].mean() if "discarded_pairs" in executed and len(executed) else float("nan"),
        ))
    by_policy = pd.DataFrame(rows)

    # A rejection is "satisfiable by another policy" when, for the same topology, hardware, target and
    # seed, some other policy's execution was SATISFIED - an in-campaign oracle for the policy's estimate.
    case = ["hardware", "topology", "requested_fidelity", "seed"]
    satisfied_cases = set(map(tuple, raw.loc[raw["final_status"] == "SATISFIED", case].drop_duplicates().to_numpy()))
    rejected = raw[raw["final_status"] == "REJECTED"].copy()
    rejected["satisfiable_by_another_policy"] = [tuple(v) in satisfied_cases for v in rejected[case].to_numpy()]
    rows = []
    for key, g in rejected.groupby(["hardware", "topology", "purification_policy"]):
        rows.append(dict(
            zip(["hardware", "topology", "purification_policy"], key),
            **proportion_columns("rejections_satisfiable", int(g["satisfiable_by_another_policy"].sum()), len(g)),
            targets_falsely_rejected=", ".join(
                f"{v:g}" for v in sorted(g.loc[g["satisfiable_by_another_policy"], "requested_fidelity"].unique())),
        ))
    return {"r03_purification_by_policy": by_policy, "r03_purification_false_rejections": pd.DataFrame(rows)}


def resource_semantics(root: Path) -> dict[str, pd.DataFrame]:
    raw = split_scenario(pd.read_csv(root / "raw" / "R08_resource_semantics" / "trials.csv"))
    rows = []
    for key, g in raw.groupby(["hardware", "topology", "reserved_memory_slots", "duration_s"]):
        hardware, topology, slots, duration = key
        rows.append(dict(
            hardware=hardware, topology=topology, reserved_memory_slots=int(slots), duration_s=duration, seeds=len(g),
            slot_seconds=slots * duration, min_delivered_pairs=int(g["min_delivered_pairs"].iat[0]),
            **proportion_columns("satisfied", int(as_bool(g["satisfied"]).sum()), len(g)),
            **mean_columns("delivered_pairs", g["delivered_pairs"]),
            **mean_columns("delivery_ratio", g["delivery_ratio"]),
            **mean_columns("average_fidelity", g["average_fidelity"]),
        ))
    table = pd.DataFrame(rows)
    table["pairs_per_slot_second"] = table["delivered_pairs_mean"] / table["slot_seconds"]
    return {"r08_resource_semantics": table}


def planners(root: Path) -> dict[str, pd.DataFrame]:
    trials = pd.read_csv(root / "planner_study" / "R04_planner_evolution" / "trials.csv")
    l4_path = root / "planner_study" / "R04b_simulation_planner" / "trials.csv"
    oracle_path = root / "oracle" / "R05_oracle_by_planner" / "oracle_by_planner.csv"
    oracle = pd.read_csv(oracle_path) if oracle_path.exists() else None
    out: dict[str, pd.DataFrame] = {}

    def decision_quality(frame: pd.DataFrame, group: list[str], *, admitted_only_levels=()) -> pd.DataFrame:
        rows = []
        for key, g in frame.groupby(group):
            key = key if isinstance(key, tuple) else (key,)
            executed = g[g["final_status"].isin(["SATISFIED", "VIOLATED"])]
            row = dict(zip(group, key), trials=len(g), **status_counts(g["final_status"]),
                       **proportion_columns("admitted", int(as_bool(g["feasible"]).sum()), len(g)),
                       **proportion_columns("satisfied_of_all", int((g["final_status"] == "SATISFIED").sum()), len(g)),
                       **proportion_columns("false_feasibility", int((executed["final_status"] == "VIOLATED").sum()), len(executed)),
                       planning_time_s_median=g["planning_time_s"].median())
            if oracle is not None:
                join = dict(zip(group, key))
                o = oracle
                for column, value in join.items():
                    if column in o:
                        o = o[o[column] == value]
                tested = o[as_bool(o["oracle_tested"])]
                row.update(proportion_columns(
                    "false_rejection", int(as_bool(tested["oracle_satisfiable"]).sum()), len(tested)))
                row["rejected_not_oracle_tested"] = len(o) - len(tested)
            rows.append(row)
        table = pd.DataFrame(rows)
        if "planner_level" in table:
            table["planner_level"] = pd.Categorical(table["planner_level"], PLANNER_ORDER, ordered=True)
            table = table.sort_values([c for c in group if c in table]).reset_index(drop=True)
        return table

    out["r04_planner_decision_quality"] = decision_quality(trials, ["hardware", "planner_level"])
    out["r04_planner_decision_quality_by_topology"] = decision_quality(trials, ["hardware", "topology", "planner_level"])
    out["r04_planner_decision_quality_by_regime"] = decision_quality(trials, ["hardware", "regime", "planner_level"])
    if l4_path.exists():
        l4 = pd.read_csv(l4_path)
        out["r04b_simulation_planner"] = decision_quality(l4, ["hardware", "planner_level"])
        # the other levels on exactly the cases L4 was given (same topology, intent and seeds)
        case = ["topology", "hardware", "requested_fidelity", "reserved_memory_slots", "duration_s", "min_delivered_pairs",
                "regime", "seed"]
        matched = trials.merge(l4[case].drop_duplicates(), on=case)
        out["r04b_matched_grid"] = decision_quality(pd.concat([matched, l4]), ["hardware", "planner_level"])

    # --- how good are the estimates the decisions rest on? -----------------
    executed = trials[trials["final_status"].isin(["SATISFIED", "VIOLATED"])].copy()
    rows = []
    for key, g in executed.groupby(["hardware", "planner_level"]):
        with_prediction = g[g["predicted_delivered_pairs"].notna() & (g["predicted_delivered_pairs"] > 0)]
        plain = with_prediction[with_prediction["purification_rounds_estimate"] == 0]
        rows.append(dict(
            hardware=key[0], planner_level=key[1], executed=len(g),
            **mean_columns("fidelity_error", g["absolute_fidelity_error"]),
            fidelity_abs_error_mean=g["absolute_fidelity_error"].abs().mean(),
            with_delivery_prediction=len(with_prediction),
            delivered_over_predicted_all=(with_prediction["delivered_pairs"].sum() / with_prediction["predicted_delivered_pairs"].sum()
                                          if len(with_prediction) else float("nan")),
            no_purification_trials=len(plain),
            delivered_over_predicted_no_purification=(plain["delivered_pairs"].sum() / plain["predicted_delivered_pairs"].sum()
                                                      if len(plain) else float("nan")),
        ))
    out["r04_estimate_accuracy"] = pd.DataFrame(rows)

    # --- L3 family: is the predicted satisfaction probability calibrated? ---
    l3 = executed[executed["planner_level"].isin(L3_FAMILY) & executed["predicted_satisfaction_probability"].notna()].copy()
    l3["outcome"] = (l3["final_status"] == "SATISFIED").astype(float)
    rows, bins = [], []
    edges = [0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0000001]
    for key, g in l3.groupby(["hardware", "planner_level"]):
        p = g["predicted_satisfaction_probability"].clip(0, 1)
        rows.append(dict(
            hardware=key[0], planner_level=key[1], executed=len(g), brier_score=float(((p - g["outcome"]) ** 2).mean()),
            mean_predicted=float(p.mean()), observed_satisfied=float(g["outcome"].mean()),
            # the decision an admission threshold of 0.5 would have taken, scored on the same executions
            **proportion_columns("threshold_half_correct", int(((p >= 0.5) == (g["outcome"] == 1)).sum()), len(g)),
            **proportion_columns("threshold_half_false_feasibility",
                                 int(((p >= 0.5) & (g["outcome"] == 0)).sum()), int((p >= 0.5).sum())),
            **proportion_columns("threshold_half_false_rejection",
                                 int(((p < 0.5) & (g["outcome"] == 1)).sum()), int((p < 0.5).sum())),
        ))
        for low, high in zip(edges, edges[1:]):
            b = g[(p >= low) & (p < high)]
            if len(b):
                bins.append(dict(hardware=key[0], planner_level=key[1], bin_low=low, bin_high=min(high, 1.0), trials=len(b),
                                 mean_predicted=float(b["predicted_satisfaction_probability"].mean()),
                                 **proportion_columns("satisfied", int(b["outcome"].sum()), len(b))))
    out["r04_l3_calibration"] = pd.DataFrame(rows)
    out["r04_l3_reliability_bins"] = pd.DataFrame(bins)

    # --- one table for the manuscript: every model's admission decisions against ground truth ---
    # Deterministic models: what they admitted/rejected, false rejection from the offline oracle.
    # Probabilistic models were collected with admission disabled, so every intent ran: "admitted"
    # is predicted probability >= 0.5, and both error rates are scored on that same execution.
    rows = []
    for _, q in out["r04_planner_decision_quality"].iterrows():
        level = str(q["planner_level"])
        if level in L3_FAMILY:
            continue
        row = dict(hardware=q["hardware"], planner_level=level, intents=int(q["trials"]), admitted=int(q["admitted_count"]),
                   satisfied=int(q["n_satisfied"]), violated=int(q["n_violated"]), rejected=int(q["n_rejected"]),
                   not_evaluated=int(q["n_failed"] + q["n_simulation_error"]),
                   **{k: q[k] for k in q.index if k.startswith("false_feasibility_")})
        if oracle is not None:
            row.update({k: q[k] for k in q.index if k.startswith("false_rejection_")})
            row["false_rejection_basis"] = "offline oracle"
        rows.append(row)
    all_l3 = trials[trials["planner_level"].isin(L3_FAMILY)]
    for (hardware, level), g in l3.groupby(["hardware", "planner_level"]):
        p = g["predicted_satisfaction_probability"].clip(0, 1)
        admitted, satisfied = p >= 0.5, g["outcome"] == 1
        submitted = len(all_l3[(all_l3["hardware"] == hardware) & (all_l3["planner_level"] == level)])
        rows.append(dict(
            hardware=hardware, planner_level=level, intents=submitted, admitted=int(admitted.sum()),
            satisfied=int((admitted & satisfied).sum()), violated=int((admitted & ~satisfied).sum()),
            rejected=int((~admitted).sum()), not_evaluated=submitted - len(g),
            **proportion_columns("false_feasibility", int((admitted & ~satisfied).sum()), int(admitted.sum())),
            **proportion_columns("false_rejection", int((~admitted & satisfied).sum()), int((~admitted).sum())),
            false_rejection_basis="same execution",
        ))
    table = pd.DataFrame(rows)
    table["planner_level"] = pd.Categorical(table["planner_level"], PLANNER_ORDER, ordered=True)
    out["r04_planner_decision_table"] = table.sort_values(["hardware", "planner_level"]).reset_index(drop=True)

    if oracle is not None:
        rows = []
        for key, g in oracle.groupby(["hardware", "planner_level", "rejection_reason"], dropna=False):
            tested = g[as_bool(g["oracle_tested"])]
            rows.append(dict(hardware=key[0], planner_level=key[1], rejection_reason=str(key[2])[:160], rejected=len(g),
                             **proportion_columns("false_rejection", int(as_bool(tested["oracle_satisfiable"]).sum()), len(tested))))
        out["r05_false_rejection_by_reason"] = pd.DataFrame(rows)
    return out


def reconciliation(root: Path) -> dict[str, pd.DataFrame]:
    raw = pd.read_csv(root / "reconciliation" / "R06_reconciliation" / "trials.csv")
    raw["recovered_flag"] = as_bool(raw["recovered"])
    raw["attempted_flag"] = as_bool(raw["reconciliation_attempted"])
    rows = []
    for key, g in raw.groupby(["hardware", "case"]):
        attempted = g[g["attempted_flag"]]
        rows.append(dict(
            hardware=key[0], case=key[1], topology=g["topology"].iat[0], seeds=len(g),
            requested_fidelity=g["requested_fidelity"].iat[0], min_delivered_pairs=int(g["min_delivered_pairs"].iat[0]),
            initial_satisfied=int((g["initial_status"] == "SATISFIED").sum()),
            initial_violated=int((g["initial_status"] == "VIOLATED").sum()),
            initial_rejected=int((g["initial_status"] == "REJECTED").sum()),
            action=attempted["action"].mode().iat[0] if len(attempted) else (
                g["action"].dropna().mode().iat[0] if g["action"].notna().any() else None),
            **proportion_columns("recovered", int(attempted["recovered_flag"].sum()), len(attempted)),
            **mean_columns("episode1_delivered_pairs", g["episode1_delivered_pairs"]),
            **mean_columns("episode2_delivered_pairs", attempted["episode2_delivered_pairs"]),
            episode1_fidelity_mean=g["episode1_average_fidelity"].mean(),
            episode2_fidelity_mean=attempted["episode2_average_fidelity"].mean() if len(attempted) else float("nan"),
            episode1_route=g["episode1_route"].dropna().mode().iat[0] if g["episode1_route"].notna().any() else None,
            episode2_route=attempted["episode2_route"].dropna().mode().iat[0] if attempted["episode2_route"].notna().any() else None,
        ))
    by_case = pd.DataFrame(rows)
    rows = []
    attempted = raw[raw["attempted_flag"]]
    for key, g in attempted.groupby(["hardware", "action"]):
        rows.append(dict(hardware=key[0], action=key[1],
                         **proportion_columns("recovered", int(g["recovered_flag"].sum()), len(g))))
    for hardware, g in attempted.groupby("hardware"):
        rows.append(dict(hardware=hardware, action="ALL",
                         **proportion_columns("recovered", int(g["recovered_flag"].sum()), len(g))))
    return {"r06_reconciliation_by_case": by_case, "r06_reconciliation_by_action": pd.DataFrame(rows)}


def baselines(root: Path) -> dict[str, pd.DataFrame]:
    raw = pd.read_csv(root / "baselines" / "R01_architecture_baselines" / "trials.csv")
    order = ["native_sequence", "static_provisioning", "ibqn_without_assurance", "ibqn_with_assurance",
             "ibqn_with_reconciliation", "ibqn_resource_aware_planner", "offline_oracle"]
    rows = []
    for key, g in raw.groupby(["hardware", "condition"]):
        evaluated = g[g["satisfied"].notna()]
        rows.append(dict(
            hardware=key[0], condition=key[1], topology=g["topology"].iat[0], seeds=len(g),
            **proportion_columns("accepted", int(as_bool(g["accepted"]).sum()), len(g)),
            outcome_evaluated=len(evaluated),
            **proportion_columns("satisfied", int(as_bool(evaluated["satisfied"]).sum()), len(evaluated)),
            **mean_columns("delivered_pairs", g["delivered_pairs"]),
            **mean_columns("average_fidelity", g["average_fidelity"]),
            route=g["route"].dropna().mode().iat[0] if g["route"].notna().any() else None,
            episodes_mean=g["episodes"].mean(), total_wall_time_s_median=g["total_wall_time_s"].median(),
        ))
    table = pd.DataFrame(rows)
    table["condition"] = pd.Categorical(table["condition"], order, ordered=True)
    return {"r01_architecture_baselines": table.sort_values(["hardware", "condition"]).reset_index(drop=True)}


def overhead(root: Path) -> dict[str, pd.DataFrame]:
    raw = pd.read_csv(root / "overhead" / "R07_overhead" / "trials.csv")
    components = [c for c in raw.columns if c.endswith("_wall_time_s")]
    rows = []
    for key, g in raw.groupby(["hardware", "condition"]):
        row = dict(hardware=key[0], condition=key[1], topology=g["topology"].iat[0], seeds=len(g),
                   orchestration_overhead_ratio_median=g["orchestration_overhead_ratio"].median(),
                   orchestration_overhead_ratio_max=g["orchestration_overhead_ratio"].max(),
                   planning_overhead_ratio_median=g["planning_overhead_ratio"].median())
        row.update({f"{c}_median": g[c].median() for c in components if g[c].notna().any()})
        rows.append(row)
    return {"r07_overhead": pd.DataFrame(rows)}


def multi_intent(root: Path) -> dict[str, pd.DataFrame]:
    base = root / "multi_intent" / "R09_multi_intent"
    groups, intents = pd.read_csv(base / "groups.csv"), pd.read_csv(base / "intents.csv")
    by_scenario = groups.groupby(["hardware", "scenario", "planner_level"], as_index=False).agg(
        groups=("group_id", "count"), intents_submitted=("intents_submitted", "sum"), admitted=("admitted", "sum"),
        satisfied=("satisfied", "sum"), violated=("violated", "sum"), failed=("failed", "sum"),
    )
    rows = []
    for key, g in intents.groupby(["hardware", "scenario", "planner_level", "group_role"]):
        rows.append(dict(
            zip(["hardware", "scenario", "planner_level", "group_role"], key), intents=len(g), **status_counts(g["final_status"]),
            reservation_rejected=int(g["failure_class"].astype(str).str.contains("reservation_rejected").sum()),
            route=g["route"].dropna().mode().iat[0] if g["route"].notna().any() else None,
            **mean_columns("delivered_pairs", g["delivered_pairs"]), **mean_columns("average_fidelity", g["average_fidelity"]),
        ))
    return {"r09_multi_intent_by_scenario": by_scenario, "r09_multi_intent_by_role": pd.DataFrame(rows)}


def audits(root: Path) -> dict[str, pd.DataFrame]:
    out = {}
    summary = root / "audit" / "generation_model_audit_summary.csv"
    if summary.exists():
        out["r00_generation_model_audit"] = pd.read_csv(summary)
    integrity = root / "audit" / "state_integrity_audit.csv"
    if integrity.exists():
        raw = pd.read_csv(integrity)
        totals = {c: int(raw[c].sum()) for c in raw.columns
                  if c.startswith(("decohere_", "swap_input_", "purification_input_")) and c != "decohere_callers"}
        totals.update(runs=len(raw), aborted=int(raw["error"].notna().sum()),
                      dangling_states_at_end=int(raw["dangling_states_at_end"].sum()))
        out["r00_state_integrity_audit"] = pd.DataFrame([totals])
    return out


def assurance_consistency(root: Path) -> dict[str, pd.DataFrame]:
    """Does every executed intent's recorded outcome agree with its own
    evidence? An intent is SATISFIED exactly when it delivered at least its
    minimum number of pairs (only pairs at or above the requested fidelity
    are ever delivered) - recomputed here from the delivered-pair count and
    compared with the lifecycle status each campaign recorded."""
    sources = [
        ("R02_routing", root / "raw" / "R02_routing" / "trials.csv"),
        ("R03_purification", root / "raw" / "R03_purification" / "trials.csv"),
        ("R08_resource_semantics", root / "raw" / "R08_resource_semantics" / "trials.csv"),
        ("R04_planner_evolution", root / "planner_study" / "R04_planner_evolution" / "trials.csv"),
        ("R04b_simulation_planner", root / "planner_study" / "R04b_simulation_planner" / "trials.csv"),
    ]
    rows = []
    for campaign, path in sources:
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        executed = frame[frame["final_status"].isin(["SATISFIED", "VIOLATED"])]
        enough = executed["delivered_pairs"] >= executed["min_delivered_pairs"]
        if "recovered" in executed:  # a reconciled trial reports its second episode's status
            comparable = executed[executed["recovered"].isna()]
            enough = enough[comparable.index]
            executed = comparable
        below_target = executed["minimum_fidelity"].notna() & (executed["minimum_fidelity"] < executed["requested_fidelity"])
        rows.append(dict(
            campaign=campaign, trials=len(frame), executed=len(executed),
            rejected=int((frame["final_status"] == "REJECTED").sum()),
            other=int((~frame["final_status"].isin(["SATISFIED", "VIOLATED", "REJECTED"])).sum()),
            classification_mismatches=int(((executed["final_status"] == "SATISFIED") != enough).sum()),
            delivered_pairs_below_requested_fidelity=int(below_target.sum()),
            rejected_with_an_evaluation=int(frame.loc[frame["final_status"] == "REJECTED", "delivered_pairs"].notna().sum()),
        ))
    if not rows:
        raise FileNotFoundError(2, "no campaign with executed trials", "trials.csv")
    table = pd.DataFrame(rows)
    total = table.drop(columns="campaign").sum().to_dict()
    table = pd.concat([table, pd.DataFrame([dict(campaign="ALL", **total)])], ignore_index=True)
    return {"assurance_consistency": table}


CAMPAIGNS = [
    ("audits", audits), ("R02 routing", routing), ("R03 purification", purification),
    ("R08 resource semantics", resource_semantics), ("R04/R04b/R05 planners", planners),
    ("R06 reconciliation", reconciliation), ("R01 baselines", baselines), ("R07 overhead", overhead),
    ("R09 multi-intent", multi_intent), ("assurance consistency", assurance_consistency),
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    out_dir = args.root / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 60)
    report = ["# Calibrated campaign suite - processed results", "",
              f"Generated by `scripts/realistic/analyze_suite.py` from `{args.root.name}/`. Do not edit by hand.", ""]
    for label, build in CAMPAIGNS:
        try:
            tables = build(args.root)
        except FileNotFoundError as exc:
            print(f"[skip] {label}: {Path(exc.filename).name if exc.filename else exc} not found")
            continue
        for name, table in tables.items():
            table.to_csv(out_dir / f"{name}.csv", index=False)
            report += [f"## {name}", "", "```", table.round(4).to_string(index=False), "```", ""]
            print(f"\n== {name} ({len(table)} rows) ==")
            print(table.round(4).to_string(index=False))
    (out_dir / "SUMMARY.md").write_text("\n".join(report), encoding="utf-8")
    print(f"\nwrote {out_dir}")


if __name__ == "__main__":
    sys.exit(main())
