"""IBQN Validation-A: verifies the architectural-claims audit script
produces the exact numbers cited in docs/paper_ibqn_validation/, derived
directly from frozen campaign data - not recomputed by hand in the docs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from audit_ibqn_architectural_claims import (  # noqa: E402
    assurance_correctness_check,
    false_rejection_false_feasibility_oracle,
    overhead_breakdown,
    planner_family_lifecycle_counts,
    reconciliation_counts,
)


@pytest.mark.unit
def test_audit_report_files_exist_after_running():
    out_dir = PROJECT_ROOT / "results" / "ibqn_validation"
    assert (out_dir / "audit_report.json").exists(), "run scripts/audit_ibqn_architectural_claims.py first"
    assert (out_dir / "audit_report.txt").exists()


@pytest.mark.unit
def test_planner_family_lifecycle_counts_match_expected():
    rows = {r["planner_level"]: r for r in planner_family_lifecycle_counts()}
    expected = {
        "L1": dict(submitted=240, admitted=90, rejected=150, satisfied=36, violated=54),
        "L2": dict(submitted=240, admitted=160, rejected=80, satisfied=36, violated=124),
        "L2-R": dict(submitted=240, admitted=50, rejected=190, satisfied=50, violated=0),
        "L3": dict(submitted=240, admitted=240, rejected=0, satisfied=66, violated=134),
        "L3-R": dict(submitted=240, admitted=240, rejected=0, satisfied=66, violated=134),
        "L4": dict(submitted=76, admitted=73, rejected=3, satisfied=67, violated=1),
    }
    for level, exp in expected.items():
        assert level in rows, f"missing planner level {level}"
        for key, value in exp.items():
            assert rows[level][key] == value, f"{level}.{key}: got {rows[level][key]}, expected {value}"


@pytest.mark.unit
def test_l2r_has_zero_observed_false_feasibility():
    """The single most load-bearing number for the architecture-vs-planner
    narrative: L2-R admitted 50 intents and none were VIOLATED. If this
    ever changes, the "planner quality varies, architecture doesn't"
    story in the paper needs to be re-checked before anything is written
    from it."""
    rows = {r["planner_level"]: r for r in planner_family_lifecycle_counts()}
    assert rows["L2-R"]["violated"] == 0
    assert rows["L2-R"]["false_feasibility_rate_among_admitted"] == 0.0


@pytest.mark.unit
def test_assurance_correctness_check_passes_on_real_data():
    result = assurance_correctness_check()
    assert result["correct"] is True
    assert result["satisfied_flag_disagrees_with_final_status_SATISFIED"] == 0
    assert result["rejected_trials_with_an_assurance_evaluation"] == 0


@pytest.mark.unit
def test_assurance_correctness_check_would_catch_a_real_mismatch(tmp_path, monkeypatch):
    """Positive control: feed a deliberately inconsistent CSV and confirm
    the check actually flags it, rather than always reporting PASS."""
    import audit_ibqn_architectural_claims as mod

    bad_csv = tmp_path / "trials.csv"
    bad_csv.write_text(
        "trial_id,final_status,satisfied\n"
        "t1,SATISFIED,False\n"
        "t2,REJECTED,True\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "P02B_PATH", bad_csv)
    result = mod.assurance_correctness_check()
    assert result["correct"] is False
    assert result["satisfied_flag_disagrees_with_final_status_SATISFIED"] == 1
    assert result["rejected_trials_with_an_assurance_evaluation"] == 1


@pytest.mark.unit
def test_false_rejection_oracle_numbers_match_frozen_f04_output():
    result = false_rejection_false_feasibility_oracle()
    metrics = result["gap_metrics"]
    assert metrics["n_total"] == 600
    assert metrics["false_rejection_rate"] == 1.0
    assert metrics["false_feasibility_rate"] == 0.15
    categories = {row["category"]: row["count"] for row in result["matrix"]}
    assert categories["INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE"] == 240
    assert categories["FEASIBLE_BUT_VIOLATED"] == 30


@pytest.mark.unit
def test_reconciliation_counts_match_frozen_f05_data():
    result = reconciliation_counts()
    assert result["n_trials"] == 100
    assert result["n_violated_entering_reconciliation"] == 75
    assert result["n_recovered_true"] == 54
    assert result["n_recovered_false"] == 21


@pytest.mark.unit
def test_overhead_breakdown_orchestration_ratio_is_small():
    """Sanity bound, not an exact-match test: architectural orchestration
    overhead should be a small fraction of total trial wall time given
    F06's simulation-dominated workload - if this ever exceeds, say, 50%,
    the overhead claim in the paper needs re-examination, not blind
    repetition of a stale number."""
    result = overhead_breakdown()
    assert result["n_trials"] == 60
    assert 0.0 <= result["mean_orchestration_overhead_ratio"] < 0.5


@pytest.mark.unit
def test_no_duplicate_trial_ids_in_f04_f05_f06_sources():
    for relative_path in [
        "results/processed/F04_planner_vs_operation/combined_trials_with_categories.csv",
        "results/raw/F05_reconciliation/trials.csv",
        "results/raw/F06_overhead/trials.csv",
    ]:
        path = PROJECT_ROOT / relative_path
        assert path.exists(), f"missing {relative_path}"
        df = pd.read_csv(path)
        if "trial_id" in df.columns:
            assert df["trial_id"].duplicated().sum() == 0, f"{relative_path} has duplicate trial_id rows"


@pytest.mark.unit
def test_frozen_ibqn_validation_source_files_unchanged():
    """Row-count guards matching the pattern used throughout M9/M10 and
    the P1 predictability audit - proves this new phase did not
    accidentally touch frozen data while deriving these numbers."""
    expected_row_counts = {
        "results/planner_study/raw/P02b_resource_aware_planners/trials.csv": 1201,
        "results/planner_study/raw/P03_l4_cost/trials.csv": 61,
        "results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv": 17,
        "results/processed/F04_planner_vs_operation/matrix.csv": 6,
        "results/raw/F05_reconciliation/trials.csv": 101,
        "results/raw/F06_overhead/trials.csv": 61,
    }
    for relative_path, expected in expected_row_counts.items():
        path = PROJECT_ROOT / relative_path
        with open(path, encoding="utf-8") as f:
            n_lines = sum(1 for _ in f)
        assert n_lines == expected, f"{relative_path} row count changed ({n_lines} != {expected})"
