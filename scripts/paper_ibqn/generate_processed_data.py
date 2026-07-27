"""P-IBQN2a: generates every processed CSV the IBQN manuscript's tables
draw from, mechanically re-derived from raw/processed campaign files,
Validation-A/B outputs, and final_evidence_matrix.md's claim IDs - never
hand-transcribed. No new simulations. No planner or frozen data touched
(every source file below is opened read-only).

Ambiguous/inapplicable cells use one of three explicit markers, never a
blank cell:
  NA_NOT_APPLICABLE  - the metric does not apply to this row by design
  NA_NOT_MEASURED    - the metric could apply but was not instrumented
  NA_NOT_COMPARABLE  - a real number exists but is not comparable to the
                       other rows in the same table (denominator/design
                       mismatch) and must not be combined with them

Run: python scripts/paper_ibqn/generate_processed_data.py
Writes: results/paper_ibqn/processed/*.csv
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "results" / "paper_ibqn" / "processed"

NA_NOT_APPLICABLE = "NA_NOT_APPLICABLE"
NA_NOT_MEASURED = "NA_NOT_MEASURED"
NA_NOT_COMPARABLE = "NA_NOT_COMPARABLE"


def wilson_ci(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Same formula reused throughout this project (search_transition_region.py,
    L4's _wilson_ci) - not re-derived differently here."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return max(0.0, center - half), min(1.0, center + half)


# ---------------------------------------------------------------------------
# 1. intent_schema.csv - structural, code-inspection-derived (not a
#    campaign result), sourced to exact fields in src/ibqn/intent/models.py
# ---------------------------------------------------------------------------
def build_intent_schema() -> pd.DataFrame:
    rows = [
        dict(field="id", meaning="Unique intent identifier", used_by_validation="yes",
             used_by_planning="yes (identity)", used_by_assurance="yes (keyed lookup)"),
        dict(field="service", meaning='Literal "entanglement_distribution"', used_by_validation="yes (schema constraint)",
             used_by_planning="no", used_by_assurance="no"),
        dict(field="endpoints.source", meaning="Source router id", used_by_validation="yes",
             used_by_planning="yes (routing)", used_by_assurance="no (indirect, via telemetry tagging)"),
        dict(field="endpoints.destination", meaning="Destination router id", used_by_validation="yes",
             used_by_planning="yes (routing)", used_by_assurance="no (indirect, via telemetry tagging)"),
        dict(field="requirements.min_fidelity", meaning="Minimum acceptable average fidelity", used_by_validation="yes",
             used_by_planning="yes (feasibility estimate)", used_by_assurance="yes (via validation.success_conditions)"),
        dict(field="requirements.min_throughput", meaning="Minimum entangled pairs/second", used_by_validation="yes",
             used_by_planning="no (no throughput estimate in any current planner)", used_by_assurance="conditional (only if declared in success_conditions)"),
        dict(field="requirements.max_latency", meaning="Per-pair latency budget", used_by_validation="yes",
             used_by_planning="no", used_by_assurance="conditional (only if declared in success_conditions)"),
        dict(field="requirements.min_delivered_pairs", meaning="Minimum delivered pairs", used_by_validation="yes",
             used_by_planning="yes (resource sizing)", used_by_assurance="yes (via validation.success_conditions)"),
        dict(field="requirements.reserved_memory_slots", meaning="Memory slots reserved for this intent", used_by_validation="yes",
             used_by_planning="yes (feasibility/resource checks)", used_by_assurance="no (planning-time only)"),
        dict(field="requirements.start_time_s", meaning="Reservation window start (sim time)", used_by_validation="yes",
             used_by_planning="yes (reservation window)", used_by_assurance="conditional (completion_time metric)"),
        dict(field="requirements.duration_s", meaning="Reservation window length", used_by_validation="yes",
             used_by_planning="yes (reservation window)", used_by_assurance="conditional (completion_time metric)"),
        dict(field="policy.priority", meaning='Literal "low"/"normal"/"high", default "normal"', used_by_validation="yes (schema)",
             used_by_planning="no (declared but unread - see docs/multi_intent_scope.md)", used_by_assurance="no"),
        dict(field="policy.allow_rerouting", meaning="Whether rerouting is permitted", used_by_validation="yes (schema)",
             used_by_planning="no (no read site found in planning/execution/assurance)", used_by_assurance="no"),
        dict(field="policy.allow_purification", meaning="Whether purification is permitted", used_by_validation="yes (schema)",
             used_by_planning="yes (passed to PurificationStrategy.decide)", used_by_assurance="no"),
        dict(field="policy.allow_multiple_paths", meaning="Whether multiple concurrent paths are permitted", used_by_validation="yes (schema)",
             used_by_planning="no (no read site found in planning/execution/assurance)", used_by_assurance="no"),
        dict(field="validation.metrics", meaning="Declared list of metric names", used_by_validation="yes (schema)",
             used_by_planning="no", used_by_assurance="no (display-only, demos.tables - assurance reads success_conditions instead)"),
        dict(field="validation.success_conditions", meaning="List of (metric, operator, expected) conditions", used_by_validation="yes",
             used_by_planning="no", used_by_assurance="yes (the ONLY source assurance evaluates against - see assurance_validation.md)"),
    ]
    return pd.DataFrame(rows).assign(
        source_file="src/ibqn/intent/models.py", claim_id=NA_NOT_APPLICABLE,
        campaign=NA_NOT_APPLICABLE,
        note="Structural claim from direct code inspection, not a campaign result - fields not read anywhere by planning/assurance are marked 'no', never assumed.",
    )


# ---------------------------------------------------------------------------
# 2. lifecycle_states.csv
# ---------------------------------------------------------------------------
def build_lifecycle_states() -> pd.DataFrame:
    rows = [
        dict(state="RECEIVED", meaning="Intent registered in the repository", allowed_successors="VALIDATED, REJECTED, CANCELLED", terminal="no"),
        dict(state="VALIDATED", meaning="Schema validated", allowed_successors="PLANNING, CANCELLED", terminal="no"),
        dict(state="PLANNING", meaning="Planner invoked", allowed_successors="PLANNED, REJECTED, CANCELLED", terminal="no"),
        dict(state="PLANNED", meaning="A plan (feasible or not) was produced", allowed_successors="DEPLOYING, CANCELLED", terminal="no"),
        dict(state="DEPLOYING", meaning="Reservation submitted to NetworkManager", allowed_successors="ACTIVE, FAILED, CANCELLED", terminal="no"),
        dict(state="ACTIVE", meaning="Reservation approved; simulation executing", allowed_successors="SATISFIED, VIOLATED, FAILED [added, see note], CANCELLED", terminal="no"),
        dict(state="REJECTED", meaning="Planner found no feasible plan", allowed_successors="(none)", terminal="yes"),
        dict(state="SATISFIED", meaning="Assurance confirmed all declared success conditions met", allowed_successors="COMPLETED, VIOLATED, CANCELLED", terminal="no"),
        dict(state="VIOLATED", meaning="Assurance found at least one unmet success condition", allowed_successors="RECONCILING, FAILED, CANCELLED", terminal="no"),
        dict(state="RECONCILING", meaning="A new episode is being (re)planned/(re)executed", allowed_successors="PLANNING, FAILED, CANCELLED", terminal="no"),
        dict(state="FAILED", meaning="Reservation rejected by NetworkManager, or a mid-simulation exception (see note)", allowed_successors="(none)", terminal="yes"),
        dict(state="COMPLETED", meaning="Terminal confirmation of a SATISFIED intent", allowed_successors="(none)", terminal="yes"),
        dict(state="CANCELLED", meaning="Intent cancelled (reachable from any non-terminal state)", allowed_successors="(none)", terminal="yes"),
    ]
    df = pd.DataFrame(rows).assign(
        source_file="src/ibqn/intent/models.py; src/ibqn/intent/lifecycle.py", claim_id="C1, C2",
        campaign=NA_NOT_APPLICABLE,
        note=NA_NOT_APPLICABLE,
    )
    df.loc[df["state"] == "ACTIVE", "note"] = (
        "ACTIVE->FAILED is a validation-discovered robustness correction (IBQN Validation-B1), "
        "NOT part of the original lifecycle design - added after finding a mid-simulation exception "
        "after ACTIVE had no terminal edge to reach. See docs/paper_ibqn_validation/simulation_error_trace.md."
    )
    df.loc[df["state"] == "FAILED", "note"] = (
        "Reached via DEPLOYING->FAILED (reservation rejected by NetworkManager, original design) or the "
        "validation-added ACTIVE->FAILED edge (mid-simulation exception). SIMULATION_ERROR is a harness-level "
        "trial-record label, NEVER an IntentStatus value - it is not one of these 13 states."
    )
    df["evidence"] = df["state"].map({
        "RECEIVED": "IntentLifecycle.__init__", "VALIDATED": "sequence_executor.py:submit/deploy",
        "PLANNING": "sequence_executor.py:submit/deploy; reconciliation.py", "PLANNED": "sequence_executor.py:_deploy_plan",
        "DEPLOYING": "sequence_executor.py:_deploy_plan", "ACTIVE": "IntentRequestApp.get_reservation_result",
        "REJECTED": "sequence_executor.py:_deploy_plan (plan.feasible=False)", "SATISFIED": "runner.py; reconciliation.py (evaluate_intent)",
        "VIOLATED": "runner.py; reconciliation.py (evaluate_intent)", "RECONCILING": "reconciliation.py:reconcile",
        "FAILED": "IntentRequestApp.get_reservation_result(False); SequenceExecutor.run() exception handler",
        "COMPLETED": "lifecycle.py:_BASE_ALLOWED_TRANSITIONS", "CANCELLED": "lifecycle.py (added to every non-terminal state)",
    })
    return df


# ---------------------------------------------------------------------------
# 3. planner_capabilities.csv
# ---------------------------------------------------------------------------
def build_planner_capabilities() -> pd.DataFrame:
    rows = [
        dict(planner="L1", purification_model="One analytical round (PurifyUntilTarget, shared with the generic IntentPlanner - NOT the same code path as F04's campaign, see note)",
             resource_awareness="no", probability_model=NA_NOT_APPLICABLE, candidate_routes="1 (ShortestHopCountRouting)",
             internal_simulation="no", matched_grid="yes (P02b)"),
        dict(planner="L2", purification_model="Iterative (multi-round estimate)", resource_awareness="no",
             probability_model=NA_NOT_APPLICABLE, candidate_routes="1 (ShortestHopCountRouting)", internal_simulation="no", matched_grid="yes (P02b)"),
        dict(planner="L2-R", purification_model="Iterative (multi-round estimate)", resource_awareness="yes (peak memory occupancy + conservative generation-rate/attempt-rate estimate)",
             probability_model=NA_NOT_APPLICABLE, candidate_routes="1 (ShortestHopCountRouting)", internal_simulation="no", matched_grid="yes (P02b)"),
        dict(planner="L3", purification_model="Iterative", resource_awareness="no", probability_model="yes (predicted satisfaction probability)",
             candidate_routes="1 (ShortestHopCountRouting)", internal_simulation="no", matched_grid="yes (P02b)"),
        dict(planner="L3-R", purification_model="Iterative", resource_awareness="yes (same as L2-R)", probability_model="yes",
             candidate_routes="1 (ShortestHopCountRouting)", internal_simulation="no", matched_grid="yes (P02b)"),
        dict(planner="L4", purification_model="Empirical (from internal simulation outcomes)", resource_awareness="indirect (via simulated outcomes)",
             probability_model="yes (predicted + internally simulated)", candidate_routes="multiple (K internal simulations per candidate)",
             internal_simulation="yes", matched_grid=f"NO - {NA_NOT_COMPARABLE} (P03/P13, different scenario set than P02b)"),
    ]
    df = pd.DataFrame(rows).assign(
        source_file="src/ibqn/planning/planners/{l1_conservative,l2_iterative,l2_resource_aware,l3_probabilistic,l3_resource_aware,l4_simulation}.py",
        claim_id="C4, C13", campaign="P02b (L1-L3-R); P03+P13 (L4)",
        note=NA_NOT_APPLICABLE,
    )
    df.loc[df["planner"] == "L1", "note"] = (
        "L1 is NOT the same code path as F04's oracle_purification_boundary experiment: F04 used the generic "
        "planning.planner.IntentPlanner wrapper (purification_policy='automatic'), not ConservativeOneRoundPlanner. "
        "Both reuse the same planning.purification.PurifyUntilTarget class internally, so the underlying mechanism "
        "is shared, but the code path and campaign are distinct - see oracle_result_reconciliation.md."
    )
    df.loc[df["planner"] == "L4", "note"] = (
        "L4 is not on the same matched seed/intent grid as L1-L3-R (data_sufficiency_assessment.md item C). "
        "L4 is a candidate-evaluation planner, never an oracle: it evaluates a bounded number (K) of candidates "
        "via internal simulation before committing to one, it does not see the real outcome in hindsight the way "
        "the offline oracle baseline does."
    )
    return df


# ---------------------------------------------------------------------------
# 4. planner_error_results.csv (false feasibility) - CORRECTED denominator:
#    admitted AND operationally executed (reached assurance), excluding
#    SIMULATION_ERROR/TIMEOUT trials that never reached an assurance
#    evaluation. This differs from architectural_validation_matrix.md's
#    original Table 2 (Validation-A), which used admitted as the sole
#    denominator - flagged explicitly as a found inconsistency, corrected
#    here per the manuscript's own denominator rule (false feasibility is
#    only decidable once assurance actually ran).
# ---------------------------------------------------------------------------
def build_planner_error_results() -> pd.DataFrame:
    df = pd.read_csv(PROJECT_ROOT / "results/planner_study/raw/P02b_resource_aware_planners/trials.csv")
    name_by_level = {
        "L1": "conservative_one_round", "L2": "iterative_analytical", "L2-R": "iterative_resource_aware",
        "L3": "probabilistic", "L3-R": "probabilistic_resource_aware",
    }
    rows = []
    for level, name in name_by_level.items():
        grp = df[df["planner_name"] == name]
        n = len(grp)
        rejected = int((grp["final_status"] == "REJECTED").sum())
        admitted = n - rejected
        satisfied = int((grp["final_status"] == "SATISFIED").sum())
        violated = int((grp["final_status"] == "VIOLATED").sum())
        op_executed = satisfied + violated
        rate = violated / op_executed if op_executed else float("nan")
        rows.append(dict(
            planner=level, metric_name="false_feasibility_rate", numerator=violated, denominator=op_executed,
            rate=round(rate, 4), ci_low=NA_NOT_MEASURED, ci_high=NA_NOT_MEASURED,
            campaign="P02b_resource_aware_planners", source_file="results/planner_study/raw/P02b_resource_aware_planners/trials.csv",
            claim_id="C6",
            note=f"Denominator = admitted AND operationally executed (reached assurance) = satisfied+violated, "
                 f"excluding {admitted - op_executed} SIMULATION_ERROR trial(s) that never reached assurance. "
                 f"admitted={admitted} for reference only, NOT the denominator used here.",
        ))
    frames = []
    for path in ["results/planner_study/raw/P03_l4_cost/trials.csv", "results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv"]:
        frames.append(pd.read_csv(PROJECT_ROOT / path))
    l4 = pd.concat(frames, ignore_index=True)
    n = len(l4)
    rejected = int((l4["final_status"] == "REJECTED").sum())
    admitted = n - rejected
    satisfied = int((l4["final_status"] == "SATISFIED").sum())
    violated = int((l4["final_status"] == "VIOLATED").sum())
    op_executed = satisfied + violated
    rate = violated / op_executed if op_executed else float("nan")
    rows.append(dict(
        planner="L4", metric_name="false_feasibility_rate", numerator=violated, denominator=op_executed,
        rate=round(rate, 4), ci_low=NA_NOT_MEASURED, ci_high=NA_NOT_MEASURED,
        campaign=f"P03_l4_cost + P13_l4_boundary_reference ({NA_NOT_COMPARABLE} to P02b's matched grid)",
        source_file="results/planner_study/raw/P03_l4_cost/trials.csv; results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv",
        claim_id="C6, C13",
        note=f"admitted={admitted}, {admitted - op_executed} trial(s) excluded (SIMULATION_ERROR/TIMEOUT). "
             f"Small n, not matched to L1-L3-R's seeds/scenarios.",
    ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. oracle_purification_boundary.csv (F04) - kept structurally and
#    numerically separate from oracle_by_planner.csv; never merged.
# ---------------------------------------------------------------------------
def build_oracle_purification_boundary() -> pd.DataFrame:
    metrics = json.loads((PROJECT_ROOT / "results/processed/F04_planner_vs_operation/gap_metrics.json").read_text(encoding="utf-8"))
    matrix = pd.read_csv(PROJECT_ROOT / "results/processed/F04_planner_vs_operation/matrix.csv")
    rejected_confirmed = int(matrix.loc[matrix["category"] == "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE", "count"].iloc[0])
    rejected_never_tested = int(matrix.loc[matrix["category"] == "INFEASIBLE_AND_REJECTED", "count"].iloc[0])
    row = dict(
        experiment="F04_purification_boundary", planner_path="generic planning.planner.IntentPlanner (purification_policy=automatic) - NOT any L1-L6 IntentPlannerPolicy",
        rejected=rejected_confirmed, oracle_tested=rejected_confirmed, oracle_satisfiable=rejected_confirmed,
        rate=round(metrics["false_rejection_rate"], 4),
        mechanism="One-round purification estimate ceiling (planning.purification.PurifyUntilTarget); fidelity thresholds densified 0.0097-0.03 above the analytically-known ceiling (0.720252, three_node_1_repeater)",
        fidelity_margin_design="Deliberately targeted at the one-round ceiling boundary (Fase K2 densification) - not a general-purpose parameter sweep",
        campaign="F02_routing + F03_purification, three_node_1_repeater scenario only", source_file="results/processed/F04_planner_vs_operation/{matrix.csv,gap_metrics.json}",
        claim_id="C8",
        note=(f"{rejected_never_tested} additional REJECTED trials in this campaign's other scenarios "
              f"(linear_chain_2_repeaters) were never oracle-tested - not included in this row's denominator. "
              f"NOT COMPARABLE to oracle_by_planner.csv - see docs/paper_ibqn_validation/"
              f"oracle_result_reconciliation.md. Do not use this table to rank planners: the planner_path here "
              f"is not any of L1-L6."),
    )
    return pd.DataFrame([row])


# ---------------------------------------------------------------------------
# 6. oracle_by_planner.csv (B2) - kept separate from #5.
# ---------------------------------------------------------------------------
def build_oracle_by_planner() -> pd.DataFrame:
    df = pd.read_csv(PROJECT_ROOT / "results/ibqn_validation_b/P16_oracle_by_planner/oracle_results.csv")
    rows = []
    for level in ["L1", "L2", "L2-R"]:
        grp = df[df["planner_level"] == level]
        tested = grp[grp["oracle_tested"]]
        n_tested = len(tested)
        n_sat = int(tested["oracle_satisfiable"].sum())
        rate = n_sat / n_tested if n_tested else float("nan")
        lo, hi = wilson_ci(n_sat, n_tested)
        rows.append(dict(
            planner=level, rejected=len(grp), oracle_tested=n_tested, oracle_satisfiable=n_sat,
            false_rejection_rate=round(rate, 4), ci_low=round(lo, 4), ci_high=round(hi, 4),
            campaign="P02b_resource_aware_planners (rejected rows) + P16_oracle_by_planner (oracle re-simulation)",
            source_file="results/ibqn_validation_b/P16_oracle_by_planner/oracle_results.csv", claim_id="C7",
            note=(f"{len(grp) - n_tested} rejected row(s) not oracle-tested (oracle itself hit a simulator "
                  f"assertion on some candidate routes - see simulation_error_trace.md). "
                  f"{NA_NOT_COMPARABLE} to oracle_purification_boundary.csv (different campaign, different "
                  f"planner_path, different parameter design)."),
        ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 7. assurance_results.csv
# ---------------------------------------------------------------------------
def build_assurance_results() -> pd.DataFrame:
    df = pd.read_csv(PROJECT_ROOT / "results/planner_study/raw/P02b_resource_aware_planners/trials.csv")
    name_by_level = {
        "L1": "conservative_one_round", "L2": "iterative_analytical", "L2-R": "iterative_resource_aware",
        "L3": "probabilistic", "L3-R": "probabilistic_resource_aware",
    }
    rows = []
    for level, name in name_by_level.items():
        grp = df[df["planner_name"] == name]
        rejected = int((grp["final_status"] == "REJECTED").sum())
        executed = len(grp) - rejected
        evaluations = int((grp["final_status"].isin(["SATISFIED", "VIOLATED"])).sum())
        missing = executed - evaluations
        mismatch1 = int(((grp["final_status"] == "SATISFIED") & (grp["satisfied"] != True)).sum())  # noqa: E712
        mismatch2 = int(((grp["satisfied"] == True) & (grp["final_status"] != "SATISFIED")).sum())  # noqa: E712
        rejected_with_eval = int(grp.loc[grp["final_status"] == "REJECTED", "satisfied"].notna().sum())
        mismatches = mismatch1 + mismatch2 + rejected_with_eval
        rows.append(dict(
            planner_or_campaign=level, executed_intents=executed, assurance_evaluations=evaluations,
            mismatches=mismatches, missing_evaluations=missing,
            status="PASS" if mismatches == 0 else "FAIL",
            campaign="P02b_resource_aware_planners", source_file="results/planner_study/raw/P02b_resource_aware_planners/trials.csv",
            claim_id="C3",
            note=f"{missing} missing evaluation(s) = SIMULATION_ERROR trials (executed/admitted, but the run raised "
                 f"before assurance could evaluate them) - a harness-level exception outcome, not an assurance defect. "
                 f"Rejected intents ({rejected}) are correctly excluded from 'executed_intents' and never counted as missing.",
        ))
    frames = []
    for path in ["results/planner_study/raw/P03_l4_cost/trials.csv", "results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv"]:
        frames.append(pd.read_csv(PROJECT_ROOT / path))
    l4 = pd.concat(frames, ignore_index=True)
    rejected = int((l4["final_status"] == "REJECTED").sum())
    executed = len(l4) - rejected
    evaluations = int((l4["final_status"].isin(["SATISFIED", "VIOLATED"])).sum())
    missing = executed - evaluations
    mismatch1 = int(((l4["final_status"] == "SATISFIED") & (l4["satisfied"] != True)).sum())  # noqa: E712
    mismatch2 = int(((l4["satisfied"] == True) & (l4["final_status"] != "SATISFIED")).sum())  # noqa: E712
    rejected_with_eval = int(l4.loc[l4["final_status"] == "REJECTED", "satisfied"].notna().sum())
    mismatches = mismatch1 + mismatch2 + rejected_with_eval
    rows.append(dict(
        planner_or_campaign="L4", executed_intents=executed, assurance_evaluations=evaluations,
        mismatches=mismatches, missing_evaluations=missing, status="PASS" if mismatches == 0 else "FAIL",
        campaign="P03_l4_cost + P13_l4_boundary_reference", source_file="results/planner_study/raw/P03_l4_cost/trials.csv; results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv",
        claim_id="C3",
        note=f"{missing} missing evaluation(s) = SIMULATION_ERROR + TIMEOUT trials (harness-level, not an assurance defect).",
    ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 8. reconciliation_results.csv
# ---------------------------------------------------------------------------
def build_reconciliation_results() -> pd.DataFrame:
    df = pd.read_csv(PROJECT_ROOT / "results/raw/F05_reconciliation/trials.csv")
    rows = []
    total_triggered = total_recovered = total_episode2 = 0
    for action in ["route_change", "slot_increase", "duration_increase"]:
        grp = df[df["action"] == action]
        triggered = len(grp)
        episode2 = int(grp["episode2_route"].notna().sum())
        recovered = int((grp["recovered"] == True).sum())  # noqa: E712
        failed_recovery = triggered - recovered
        rate = recovered / triggered if triggered else float("nan")
        rows.append(dict(
            action=action, triggered=triggered, episode2_executed=episode2, recovered=recovered,
            failed_recovery=failed_recovery, recovery_rate=round(rate, 4),
            campaign="F05_reconciliation", source_file="results/raw/F05_reconciliation/trials.csv", claim_id="C9",
            note="Recovery means the second execution episode was evaluated as SATISFIED (episodes==2 for all rows; episode2 genuinely re-executed even for failed-recovery rows).",
        ))
        total_triggered += triggered
        total_recovered += recovered
        total_episode2 += episode2
    rows.append(dict(
        action="TOTAL", triggered=total_triggered, episode2_executed=total_episode2, recovered=total_recovered,
        failed_recovery=total_triggered - total_recovered, recovery_rate=round(total_recovered / total_triggered, 4),
        campaign="F05_reconciliation", source_file="results/raw/F05_reconciliation/trials.csv", claim_id="C9",
        note="Single-intent campaign only - multi-intent reconciliation behavior under contention not campaign-tested (0 VIOLATED outcomes in P17).",
    ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 9. multi_intent_results.csv (P17)
# ---------------------------------------------------------------------------
def build_multi_intent_results() -> pd.DataFrame:
    intents = pd.read_csv(PROJECT_ROOT / "results/ibqn_validation_b/P17_concurrent_intents/intents.csv")
    intents["scenario_group"] = intents["scenario"].str.replace(r"-[AB]$", "", regex=True)
    rows = []
    for (scenario, planner), grp in intents.groupby(["scenario_group", "planner_level"]):
        n_groups = grp["group_id"].nunique()
        admitted = int(grp["decision_feasible"].sum())
        satisfied = int((grp["final_status"] == "SATISFIED").sum())
        resv_rejected = int((grp["failure_class"] == "C_resource_contention_reservation_rejected").sum())
        violated = int((grp["final_status"] == "VIOLATED").sum())
        failed = int((grp["final_status"] == "FAILED").sum())
        rows.append(dict(
            scenario=scenario, groups=n_groups, intents=len(grp), planner=planner, admitted=admitted,
            satisfied=satisfied, reservation_rejected=resv_rejected, violated=violated, failed=failed,
            campaign="P17_concurrent_intents", source_file="results/ibqn_validation_b/P17_concurrent_intents/intents.csv",
            claim_id="C10, C11",
            note="'admitted' = planner decision (feasible); 'reservation_rejected' = NetworkManager rejected the "
                 "already-admitted reservation (a DIFFERENT, execution-time outcome, never a planner rejection). "
                 "'failed' = total FAILED intents (equals reservation_rejected in this campaign; no other FAILED "
                 "mechanism occurred in P17).",
        ))
    return pd.DataFrame(rows).sort_values(["scenario", "planner"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# 10. overhead_results.csv
# ---------------------------------------------------------------------------
def build_overhead_results() -> pd.DataFrame:
    intents = pd.read_csv(PROJECT_ROOT / "results/ibqn_validation_b/P17_concurrent_intents/intents.csv")
    components = {
        "planner": ("planning_wall_time_s", "planner"),
        "intent_validation": ("intent_validation_wall_time_s", "lifecycle"),
        "orchestration": ("orchestration_wall_time_s", "lifecycle (includes route application - not separately isolated)"),
        "simulation": ("simulation_wall_time_s_shared", "simulation"),
        "observation": ("observation_extraction_wall_time_s", "lifecycle"),
        "assurance": ("assurance_wall_time_s", "lifecycle"),
    }
    total = (
        intents["planning_wall_time_s"] + intents["intent_validation_wall_time_s"]
        + intents["orchestration_wall_time_s"] + intents["simulation_wall_time_s_shared"]
        + intents["observation_extraction_wall_time_s"] + intents["assurance_wall_time_s"]
    )
    rows = []
    for name, (col, scope) in components.items():
        med, p90 = intents[col].median(), intents[col].quantile(0.9)
        pct = (intents[col] / total).median() * 100
        rows.append(dict(
            component=name, median_s=round(med, 6), p90_s=round(p90, 6), pct_of_total=round(pct, 4), scope=scope,
            campaign="P17_concurrent_intents", source_file="results/ibqn_validation_b/P17_concurrent_intents/intents.csv",
            claim_id="C12", note="Wall-clock, machine-dependent, P17-specific instrumentation - not a general architectural constant.",
        ))
    rows.append(dict(
        component="reconciliation (decision + execution)", median_s=NA_NOT_MEASURED, p90_s=NA_NOT_MEASURED, pct_of_total=NA_NOT_MEASURED,
        scope="reconciliation", campaign="P17_concurrent_intents", source_file="results/ibqn_validation_b/P17_concurrent_intents/intents.csv",
        claim_id="C12", note="0 VIOLATED outcomes occurred in P17, so reconciliation was never invoked - not a real zero, genuinely not measured in this campaign.",
    ))
    rows.append(dict(
        component="persistence (true, isolated)", median_s=NA_NOT_MEASURED, p90_s=NA_NOT_MEASURED, pct_of_total=NA_NOT_MEASURED,
        scope="persistence", campaign="P17_concurrent_intents", source_file=NA_NOT_APPLICABLE,
        claim_id="C12", note="An instrumentation defect (timer placed before topology construction, not before the row-append step) made this run's persistence timer measure almost the whole group instead - disclosed in overhead_measurement.md, not re-run; true persistence cost not isolated in this or any other campaign (same gap as F06).",
    ))
    rows.append(dict(
        component="route_application (isolated)", median_s=NA_NOT_MEASURED, p90_s=NA_NOT_MEASURED, pct_of_total=NA_NOT_MEASURED,
        scope="merged into orchestration", campaign="P17_concurrent_intents", source_file=NA_NOT_APPLICABLE,
        claim_id="C12", note="Not separately isolated from orchestration in P17 or F06 - a genuine, twice-disclosed measurement gap, not estimated.",
    ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 11. failure_taxonomy.csv - descriptive, not a campaign result
# ---------------------------------------------------------------------------
def build_failure_taxonomy() -> pd.DataFrame:
    rows = [
        dict(failure_class="correct rejection", definition="Planner rejects; offline oracle confirms genuinely unsatisfiable",
             example="L1/L2 rejections at fidelity well beyond the one-round purification ceiling", detected_by="offline oracle",
             final_state="REJECTED"),
        dict(failure_class="false rejection", definition="Planner rejects; offline oracle confirms it was actually satisfiable",
             example="L2-R rejections with rejection_reason=DELIVERY_TARGET_EXCEEDS_WINDOW that the oracle satisfied", detected_by="offline oracle ONLY (never assurance - a rejected intent is never executed)",
             final_state="REJECTED"),
        dict(failure_class="correct feasibility", definition="Planner admits; assurance confirms SATISFIED",
             example="L2-R's 50/50 admitted intents in P02b", detected_by="assurance", final_state="SATISFIED"),
        dict(failure_class="false feasibility", definition="Planner admits; assurance finds VIOLATED",
             example="L1's 54/90 admitted-but-violated trials", detected_by="assurance (after execution)", final_state="VIOLATED"),
        dict(failure_class="stochastic operational failure", definition="A reasonable plan; a stochastic realization still fails",
             example="M10's confirmed graded transition region at four_node (frozen predictability evidence)", detected_by="assurance / repeated-trial statistics",
             final_state="VIOLATED"),
        dict(failure_class="architectural failure", definition="The architecture fails to execute/observe/classify/reconcile per its declared lifecycle",
             example="The pre-fix SIMULATION_ERROR gap (intent stuck at ACTIVE) - now closed, see Validation-B1", detected_by="lifecycle/repository state inspection",
             final_state="Should always be a terminal IntentStatus (FAILED after the fix); never a stuck non-terminal state"),
        dict(failure_class="simulator/infrastructure failure", definition="SeQUeNCe itself raises (e.g. a protocol assertion) or a harness-level timeout occurs",
             example="BBPSSWProtocol's kept_memo.fidelity assertion; P14's rare TIMEOUT cases", detected_by="harness exception handler / heartbeat monitor",
             final_state="FAILED (post-fix); harness-level SIMULATION_ERROR/TIMEOUT label in trial records"),
    ]
    df = pd.DataFrame(rows).assign(
        source_file="docs/paper_ibqn_validation/architectural_validation_matrix.md; simulation_error_trace.md",
        claim_id="C2, C6, C7, C8", campaign=NA_NOT_APPLICABLE,
    )
    return df


# ---------------------------------------------------------------------------
# 12. limitations.csv
# ---------------------------------------------------------------------------
def build_limitations() -> pd.DataFrame:
    rows = [
        dict(limitation="SeQUeNCe-only evaluation, no physical hardware execution", claim_id="C1-C14 (scope of every result)"),
        dict(limitation="Small, hand-specified topologies (three_node, four_node, diamond, small_mesh, star)", claim_id="C5-C13"),
        dict(limitation="L4 not on the same matched seed/intent grid as L1-L3-R", claim_id="C5, C6, C13"),
        dict(limitation="Offline oracle only run against selected rejected intents (P02b + F02/F03's three_node_1_repeater), not exhaustively", claim_id="C7, C8"),
        dict(limitation="No multi-intent reconciliation campaign (P17 produced 0 VIOLATED outcomes)", claim_id="C9, C10"),
        dict(limitation="No planner currently has cross-intent, planning-time residual-resource awareness", claim_id="C10, C11"),
        dict(limitation="route_application and true persistence overhead not isolated from orchestration (both P17 and frozen F06)", claim_id="C12"),
        dict(limitation="Simulation wall time is machine-dependent, not a portable cost metric", claim_id="C12"),
        dict(limitation="One lifecycle bug (SIMULATION_ERROR/ACTIVE stuck state) was found and corrected during validation, not present from initial design", claim_id="C2"),
        dict(limitation="Predictability results (M9/M10) are supporting evidence for planner robustness, not universal or physical limits", claim_id="C14"),
    ]
    return pd.DataFrame(rows).assign(source_file="docs/paper_ibqn_validation/data_sufficiency_assessment.md", campaign=NA_NOT_APPLICABLE)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    builders = {
        "intent_schema": build_intent_schema,
        "lifecycle_states": build_lifecycle_states,
        "planner_capabilities": build_planner_capabilities,
        "planner_error_results": build_planner_error_results,
        "oracle_purification_boundary": build_oracle_purification_boundary,
        "oracle_by_planner": build_oracle_by_planner,
        "assurance_results": build_assurance_results,
        "reconciliation_results": build_reconciliation_results,
        "multi_intent_results": build_multi_intent_results,
        "overhead_results": build_overhead_results,
        "failure_taxonomy": build_failure_taxonomy,
        "limitations": build_limitations,
    }
    for name, builder in builders.items():
        df = builder()
        out_path = OUT_DIR / f"{name}.csv"
        df.to_csv(out_path, index=False)
        print(f"wrote {out_path} ({len(df)} rows)")
    print("DONE")


if __name__ == "__main__":
    main()
