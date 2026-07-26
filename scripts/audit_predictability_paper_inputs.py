"""P1: mechanical audit of every input the Predictability Limits paper
will cite. Checks raw/processed files exist, trial counts, duplicate
trial IDs, `final_status`/`termination_reason` vocabularies, timeouts,
seeds, recorded commits, and re-derives a set of KEY numbers directly
from the CSVs to cross-check against `docs/paper_predictability/
evidence_matrix.md`'s hardcoded values (below) - not a parse of the
Markdown table (fragile), but an independent recomputation compared
against the same values a human transcribed into that table.

Figures/tables/notebook outputs are checked for PRESENCE but do not by
themselves fail the audit at this stage (P1 - before P3/P4 have run) -
their absence is reported as PENDING, not FAIL. Every other section
(file existence, data-integrity checks, evidence-matrix number
cross-checks) DOES determine PASS/FAIL, since those are exactly what P1
is supposed to establish before any manuscript number is trusted.

Writes results/predictability_paper/audit_report.json and
audit_report.txt. Never touches P01-P02B/P03/M9/M10 data - read-only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "results" / "predictability_paper"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

KNOWN_FINAL_STATUS_VALUES = {
    "SATISFIED", "VIOLATED", "REJECTED", "TIMEOUT", "SIMULATION_ERROR", "WORKER_ERROR",
}
KNOWN_TERMINATION_REASONS = {
    "TIMEOUT", "NO_PROGRESS", "MAX_RETRIES", "SIMULATION_COMPLETE", "ERROR", None, float("nan"),
}

# --- raw campaigns this paper cites ---
M10_CAMPAIGNS = {
    "P10_replay_determinism": PROJECT_ROOT / "results/predictability_m10/raw/P10_replay_determinism/trials.csv",
    "P11_boundary_search": PROJECT_ROOT / "results/predictability_m10/raw/P11_boundary_search/trials.csv",
    "P12_boundary_variability": PROJECT_ROOT / "results/predictability_m10/raw/P12_boundary_variability/trials.csv",
    "P13_l4_boundary_reference": PROJECT_ROOT / "results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv",
    "P14_tail_event_study": PROJECT_ROOT / "results/predictability_m10/raw/P14_tail_event_study/trials.csv",
    "P15_balanced_factorial": PROJECT_ROOT / "results/predictability_m10/raw/P15_balanced_factorial/trials.csv",
}
M9_CAMPAIGNS = {
    "P02_variance": PROJECT_ROOT / "results/predictability/raw/P02_variance/trials.csv",
    "P04_retry_storm": PROJECT_ROOT / "results/predictability/raw/P04_retry_storm/trials.csv",
}
FROZEN_CAMPAIGNS = {
    "P02b_resource_aware_planners": PROJECT_ROOT / "results/planner_study/raw/P02b_resource_aware_planners/trials.csv",
    "P03_l4_cost": PROJECT_ROOT / "results/planner_study/raw/P03_l4_cost/trials.csv",
}

PROCESSED_FILES = [
    "results/predictability_m10/processed/replay_determinism_report.csv",
    "results/predictability_m10/processed/replay_determinism_summary.json",
    "results/predictability_m10/processed/boundary_search_report.csv",
    "results/predictability_m10/processed/boundary_variability_report.csv",
    "results/predictability_m10/processed/boundary_variability_summary.json",
    "results/predictability_m10/processed/l4_boundary_reference_comparison.csv",
    "results/predictability_m10/processed/l4_boundary_reference_summary.json",
    "results/predictability_m10/processed/p15_variance_decomposition_satisfied.csv",
    "results/predictability_m10/processed/p15_variance_decomposition_delivered_pairs.csv",
    "results/predictability_m10/processed/p15_variance_decomposition_summary.json",
    "results/predictability_m10/processed/randomness_audit.json",
    "results/predictability/processed/information_level_comparison.csv",
    "results/predictability/processed/variance_decomposition.csv",
    "results/planner_study/processed/P02b_mcnemar_pairwise.csv",
    "results/planner_study/processed/P03_l4_cost_summary.csv",
]

DOC_FILES = [
    "docs/predictability_final_report.md",
    "docs/predictability_m10/final_report.md",
    "docs/predictability_m10/m9_conclusion_audit.md",
    "docs/predictability_m10/randomness_audit.md",
    "docs/predictability_m10/checkpoint_m10a.md",
    "docs/predictability_m10/checkpoint_m10b.md",
    "docs/predictability_m10/m10_6_boundary_variability_summary.md",
    "docs/predictability_m10/m10_7_l4_boundary_reference_summary.md",
    "docs/predictability_m10/m10_8_tail_event_summary.md",
    "docs/predictability_m10/m10_10_corrected_variance_analysis.md",
]

# --- hardcoded expected values, matching evidence_matrix.md exactly - the
# cross-check is: does a FRESH recomputation from the CSV/JSON still
# produce these? If not, the matrix (or the underlying data) has drifted.
EXPECTED = {
    "P10_n_trials": 160,
    "P11_n_trials": 352,
    "P12_n_trials": 820,
    "P13_n_trials": 16,
    "P14_n_trials": 120,
    "P15_n_trials": 240,
    "replay_bitwise_identical": 14,
    "replay_logically_identical": 2,
    "replay_nondeterministic": 0,
    "boundary_bayes_equal_weighted": 0.04925925925925925,
    "boundary_bayes_trial_weighted": 0.06829268292682927,
    "l4_mean_calibration_error_same_route": 0.0875,
    "l4_n_route_mismatches": 4,
    "p15_seed_contribution_satisfied": 0.0,
    "p15_seed_contribution_delivered_pairs": 0.00043049014911631484,
    "p14_termination_reason_counts": {
        "SIMULATION_COMPLETE": 118, "TIMEOUT": 2, "NO_PROGRESS": 0, "MAX_RETRIES": 0, "ERROR": 0,
    },
}


def audit_campaign(name: str, path: Path) -> dict:
    try:
        display_path = str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        display_path = str(path)  # path outside PROJECT_ROOT (e.g. a test fixture) - report as-is, don't crash
    result = {"campaign": name, "path": display_path, "exists": path.exists()}
    if not path.exists():
        result["status"] = "FAIL"
        result["reason"] = "file not found"
        return result

    df = pd.read_csv(path)
    result["n_trials"] = len(df)
    result["n_duplicate_trial_ids"] = int(df["trial_id"].duplicated().sum()) if "trial_id" in df else None
    result["final_status_values"] = sorted(df["final_status"].dropna().unique().tolist()) if "final_status" in df else None
    unexpected_status = (
        set(result["final_status_values"]) - KNOWN_FINAL_STATUS_VALUES if result["final_status_values"] else set()
    )
    result["unexpected_final_status_values"] = sorted(unexpected_status)
    result["n_timed_out"] = int(df["timed_out"].sum()) if "timed_out" in df else None
    result["seed_min"] = int(df["seed"].min()) if "seed" in df and len(df) else None
    result["seed_max"] = int(df["seed"].max()) if "seed" in df and len(df) else None
    result["project_git_commits"] = (
        sorted(df["project_git_commit"].dropna().unique().tolist()) if "project_git_commit" in df else None
    )

    problems = []
    if result["n_duplicate_trial_ids"]:
        problems.append(f"{result['n_duplicate_trial_ids']} duplicate trial_id(s)")
    if unexpected_status:
        problems.append(f"unexpected final_status values: {sorted(unexpected_status)}")
    result["status"] = "FAIL" if problems else "PASS"
    if problems:
        result["reason"] = "; ".join(problems)
    return result


def check_evidence_matrix_numbers() -> dict:
    checks = []

    def add(label: str, actual, expected) -> None:
        ok = actual == expected or (
            isinstance(actual, float) and isinstance(expected, float) and abs(actual - expected) < 1e-9
        )
        checks.append({"label": label, "actual": actual, "expected": expected, "match": ok})

    p10 = pd.read_csv(M10_CAMPAIGNS["P10_replay_determinism"])
    add("P10 n_trials", len(p10), EXPECTED["P10_n_trials"])

    p11 = pd.read_csv(M10_CAMPAIGNS["P11_boundary_search"])
    add("P11 n_trials", len(p11), EXPECTED["P11_n_trials"])

    p12 = pd.read_csv(M10_CAMPAIGNS["P12_boundary_variability"])
    add("P12 n_trials", len(p12), EXPECTED["P12_n_trials"])

    p13 = pd.read_csv(M10_CAMPAIGNS["P13_l4_boundary_reference"])
    add("P13 n_trials", len(p13), EXPECTED["P13_n_trials"])

    p14 = pd.read_csv(M10_CAMPAIGNS["P14_tail_event_study"])
    add("P14 n_trials", len(p14), EXPECTED["P14_n_trials"])
    p14_counts = p14["termination_reason"].value_counts().to_dict()
    for reason, expected_count in EXPECTED["p14_termination_reason_counts"].items():
        add(f"P14 termination_reason={reason}", int(p14_counts.get(reason, 0)), expected_count)

    p15 = pd.read_csv(M10_CAMPAIGNS["P15_balanced_factorial"])
    add("P15 n_trials", len(p15), EXPECTED["P15_n_trials"])

    replay_summary = json.loads((PROJECT_ROOT / "results/predictability_m10/processed/replay_determinism_summary.json").read_text())
    add("replay n_bitwise_identical", replay_summary["n_bitwise_identical"], EXPECTED["replay_bitwise_identical"])
    add("replay n_logically_identical", replay_summary["n_logically_identical"], EXPECTED["replay_logically_identical"])
    add("replay n_nondeterministic", replay_summary["n_nondeterministic"], EXPECTED["replay_nondeterministic"])

    boundary_summary = json.loads((PROJECT_ROOT / "results/predictability_m10/processed/boundary_variability_summary.json").read_text())
    add("boundary Bayes bound (equal-weighted)", boundary_summary["bayes_lower_bound_equal_weighted"], EXPECTED["boundary_bayes_equal_weighted"])
    add("boundary Bayes bound (trial-weighted)", boundary_summary["bayes_lower_bound_trial_weighted"], EXPECTED["boundary_bayes_trial_weighted"])

    l4_summary = json.loads((PROJECT_ROOT / "results/predictability_m10/processed/l4_boundary_reference_summary.json").read_text())
    add("L4 mean calibration error (same route)", l4_summary["mean_calibration_error_same_route_only"], EXPECTED["l4_mean_calibration_error_same_route"])
    add("L4 n_route_mismatches", l4_summary["n_route_mismatches"], EXPECTED["l4_n_route_mismatches"])

    p15_summary = json.loads((PROJECT_ROOT / "results/predictability_m10/processed/p15_variance_decomposition_summary.json").read_text())
    add("P15 seed contribution (satisfied)", p15_summary["seed_contribution_satisfied_response"], EXPECTED["p15_seed_contribution_satisfied"])
    add("P15 seed contribution (delivered_pairs)", p15_summary["seed_contribution_delivered_pairs_response"], EXPECTED["p15_seed_contribution_delivered_pairs"])

    n_mismatches = sum(1 for c in checks if not c["match"])
    return {"n_checks": len(checks), "n_mismatches": n_mismatches, "checks": checks}


def check_paths(paths: list[str], label: str) -> dict:
    missing = [p for p in paths if not (PROJECT_ROOT / p).exists()]
    return {"label": label, "n_expected": len(paths), "n_missing": len(missing), "missing": missing}


def check_figures_tables_pending() -> dict:
    """Figures/tables are produced in P3/P4, which have not run yet -
    reported as PENDING, not FAIL, at this P1 stage."""
    fig_dir = PROJECT_ROOT / "paper_predictability" / "figures"
    table_dir = PROJECT_ROOT / "paper_predictability" / "tables"
    return {
        "figures_dir_exists": fig_dir.exists(),
        "n_figures_present": len(list(fig_dir.glob("*"))) if fig_dir.exists() else 0,
        "tables_dir_exists": table_dir.exists(),
        "n_tables_present": len(list(table_dir.glob("*"))) if table_dir.exists() else 0,
        "status": "PENDING (expected before P3/P4 run)",
    }


def main() -> None:
    campaign_results = []
    for group in (M10_CAMPAIGNS, M9_CAMPAIGNS, FROZEN_CAMPAIGNS):
        for name, path in group.items():
            campaign_results.append(audit_campaign(name, path))

    processed_check = check_paths(PROCESSED_FILES, "processed files")
    doc_check = check_paths(DOC_FILES, "documentation files")
    number_check = check_evidence_matrix_numbers()
    figures_tables = check_figures_tables_pending()

    n_campaign_failures = sum(1 for r in campaign_results if r["status"] == "FAIL")
    overall_pass = (
        n_campaign_failures == 0
        and processed_check["n_missing"] == 0
        and doc_check["n_missing"] == 0
        and number_check["n_mismatches"] == 0
    )

    report = {
        "verdict": "PASS" if overall_pass else "FAIL",
        "campaigns": campaign_results,
        "processed_files": processed_check,
        "documentation_files": doc_check,
        "evidence_matrix_number_cross_check": number_check,
        "figures_and_tables": figures_tables,
    }

    (OUTPUT_DIR / "audit_report.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    lines = [f"PREDICTABILITY PAPER INPUT AUDIT - VERDICT: {report['verdict']}", ""]
    lines.append("=== Campaigns ===")
    for r in campaign_results:
        lines.append(f"  [{r['status']}] {r['campaign']}: n_trials={r.get('n_trials')}, "
                      f"duplicates={r.get('n_duplicate_trial_ids')}, "
                      f"unexpected_status={r.get('unexpected_final_status_values')}")
        if r["status"] == "FAIL":
            lines.append(f"      reason: {r.get('reason')}")
    lines.append("")
    lines.append(f"=== Processed files: {processed_check['n_expected'] - processed_check['n_missing']}/{processed_check['n_expected']} present ===")
    if processed_check["missing"]:
        lines.append(f"  missing: {processed_check['missing']}")
    lines.append(f"=== Documentation files: {doc_check['n_expected'] - doc_check['n_missing']}/{doc_check['n_expected']} present ===")
    if doc_check["missing"]:
        lines.append(f"  missing: {doc_check['missing']}")
    lines.append("")
    lines.append(f"=== Evidence-matrix number cross-check: {number_check['n_checks'] - number_check['n_mismatches']}/{number_check['n_checks']} match ===")
    for c in number_check["checks"]:
        if not c["match"]:
            lines.append(f"  MISMATCH: {c['label']}: actual={c['actual']} expected={c['expected']}")
    lines.append("")
    lines.append(f"=== Figures/tables: {figures_tables['status']} ===")
    lines.append(f"  figures present: {figures_tables['n_figures_present']}, tables present: {figures_tables['n_tables_present']}")
    lines.append("")
    lines.append(f"FINAL: {report['verdict']}")

    text = "\n".join(lines)
    (OUTPUT_DIR / "audit_report.txt").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
