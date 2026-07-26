"""P1 tests: the predictability-paper input audit must actually catch
problems, not just report PASS unconditionally, and every file the
evidence matrix cites must really exist. Remaining section-26 test
categories (figures/tables/LaTeX compilation/bibliography) are added in
later phases (P3 onward) once those artifacts exist - not before."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from audit_predictability_paper_inputs import (  # noqa: E402
    KNOWN_FINAL_STATUS_VALUES,
    M10_CAMPAIGNS,
    audit_campaign,
    check_evidence_matrix_numbers,
)


@pytest.mark.unit
def test_audit_report_files_exist_after_running():
    report_json = PROJECT_ROOT / "results" / "predictability_paper" / "audit_report.json"
    report_txt = PROJECT_ROOT / "results" / "predictability_paper" / "audit_report.txt"
    assert report_json.exists(), "run scripts/audit_predictability_paper_inputs.py first"
    assert report_txt.exists()


@pytest.mark.unit
def test_audit_report_verdict_is_pass_or_fail():
    report = json.loads((PROJECT_ROOT / "results" / "predictability_paper" / "audit_report.json").read_text())
    assert report["verdict"] in ("PASS", "FAIL")


@pytest.mark.unit
def test_no_duplicate_trial_ids_in_any_m10_campaign():
    for name, path in M10_CAMPAIGNS.items():
        assert path.exists(), f"{name} raw data missing"
        df = pd.read_csv(path)
        assert df["trial_id"].duplicated().sum() == 0, f"{name} has duplicate trial_id rows"


@pytest.mark.unit
def test_audit_campaign_flags_duplicates(tmp_path):
    """The audit function must actually detect duplicates, not just pass
    everything through - a positive-control test."""
    bad_csv = tmp_path / "trials.csv"
    bad_csv.write_text("trial_id,final_status,seed\nt1,SATISFIED,0\nt1,SATISFIED,0\n", encoding="utf-8")
    result = audit_campaign("fake_campaign", bad_csv)
    assert result["status"] == "FAIL"
    assert result["n_duplicate_trial_ids"] == 1


@pytest.mark.unit
def test_audit_campaign_flags_unexpected_status(tmp_path):
    bad_csv = tmp_path / "trials.csv"
    bad_csv.write_text("trial_id,final_status,seed\nt1,NOT_A_REAL_STATUS,0\n", encoding="utf-8")
    result = audit_campaign("fake_campaign", bad_csv)
    assert result["status"] == "FAIL"
    assert "NOT_A_REAL_STATUS" in result["unexpected_final_status_values"]


@pytest.mark.unit
def test_audit_campaign_missing_file_fails():
    result = audit_campaign("does_not_exist", Path("/nonexistent/path/trials.csv"))
    assert result["status"] == "FAIL"
    assert result["exists"] is False


@pytest.mark.unit
def test_evidence_matrix_numbers_cross_check_currently_matches():
    """This is the live cross-check the paper phase depends on - if this
    ever fails, the evidence matrix or the underlying data has drifted
    and must be reconciled before any manuscript number is trusted."""
    result = check_evidence_matrix_numbers()
    mismatches = [c for c in result["checks"] if not c["match"]]
    assert not mismatches, f"evidence matrix numbers out of sync with data: {mismatches}"


@pytest.mark.unit
def test_evidence_matrix_file_references_all_exist():
    """Every file path mentioned in evidence_matrix.md (backtick-quoted)
    that looks like a project-relative path must actually exist."""
    matrix_path = PROJECT_ROOT / "docs" / "paper_predictability" / "evidence_matrix.md"
    text = matrix_path.read_text(encoding="utf-8")
    candidates = re.findall(r"`((?:results|docs|scripts|src|configs)/[^`]+?\.(?:csv|json|md|py))`", text)
    assert candidates, "no file references found - matrix format may have changed"
    missing = [c for c in set(candidates) if not (PROJECT_ROOT / c).exists()]
    assert not missing, f"evidence_matrix.md references missing files: {missing}"


@pytest.mark.unit
def test_frozen_planner_study_files_unchanged():
    """Guards against this new phase accidentally touching frozen M9/M10
    results while building paper inputs - same row-count-guard pattern
    used throughout M10."""
    expected_row_counts = {
        "results/planner_study/raw/P02b_resource_aware_planners/trials.csv": 1201,
        "results/planner_study/raw/P03_l4_cost/trials.csv": 61,
        "results/predictability_m10/raw/P10_replay_determinism/trials.csv": 161,
        "results/predictability_m10/raw/P11_boundary_search/trials.csv": 353,
        "results/predictability_m10/raw/P12_boundary_variability/trials.csv": 821,
        "results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv": 17,
        "results/predictability_m10/raw/P14_tail_event_study/trials.csv": 121,
        "results/predictability_m10/raw/P15_balanced_factorial/trials.csv": 241,
    }
    for relative_path, expected in expected_row_counts.items():
        path = PROJECT_ROOT / relative_path
        with open(path, encoding="utf-8") as f:
            n_lines = sum(1 for _ in f)
        assert n_lines == expected, f"{relative_path} row count changed ({n_lines} != {expected})"
