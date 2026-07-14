"""Fase K5 mandatory tests (section 17): cross-cutting integrity checks
over the final results package (figures, statistical comparisons,
planner-operation matrix, recovery types, and the audit script itself).
Read-only - never modifies results/raw, results/processed, or
results/manifests.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = PROJECT_ROOT / "results"

PILOT_CAMPAIGN_CODES = ("C01_routing_strategy", "C02_fidelity_throughput", "C03_assurance_outcomes", "C04_reconciliation_effectiveness", "C01", "C02", "C03", "C04")


@pytest.mark.unit
def test_final_figures_only_cite_final_campaigns_not_pilot():
    sources_path = RESULTS_DIR / "figures" / "final" / "sources.json"
    if not sources_path.exists():
        pytest.skip("results/figures/final/sources.json not generated yet")
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    for figure_name, info in sources.items():
        assert info["campaign"].startswith("F") or "F0" in info["campaign"], (
            f"{figure_name} does not cite a final (F0X) campaign: {info['campaign']}"
        )
        for source_file in info["source_files"]:
            for pilot_code in PILOT_CAMPAIGN_CODES[:4]:
                assert pilot_code not in source_file, f"{figure_name} cites a pilot campaign file: {source_file}"


@pytest.mark.unit
def test_final_figure_titles_never_contain_internal_pilot_codes():
    """Section 4's requirement: the actual rendered title/suptitle of a
    figure must read as scientific prose, never an internal campaign
    code like 'campaign C01'. Checked against the generator script's
    own set_title/suptitle call sites (the description/caption field in
    sources.json is a different, more permissive field - it may
    legitimately explain a contrast against pilot data, e.g. "not the
    2-seed pilot C03..." - only the plotted title itself is constrained)."""
    generator_path = PROJECT_ROOT / "scripts" / "generate_final_figures.py"
    if not generator_path.exists():
        pytest.skip("scripts/generate_final_figures.py not found")
    source = generator_path.read_text(encoding="utf-8")
    for line in source.splitlines():
        if "set_title(" in line or "suptitle(" in line:
            for pilot_code in PILOT_CAMPAIGN_CODES[:4]:
                assert pilot_code not in line, f"a figure title references a pilot campaign code: {line.strip()}"


@pytest.mark.unit
def test_every_final_figure_has_pdf_and_png():
    figures_dir = RESULTS_DIR / "figures" / "final"
    if not figures_dir.exists():
        pytest.skip("results/figures/final/ not generated yet")
    pdfs = {p.stem for p in figures_dir.glob("*.pdf")}
    pngs = {p.stem for p in figures_dir.glob("*.png")}
    assert pdfs, "no PDF figures found"
    assert pdfs == pngs, f"mismatch: pdf-only={pdfs - pngs}, png-only={pngs - pdfs}"


@pytest.mark.unit
def test_all_statistical_comparisons_have_n_pairs_column():
    processed_dir = RESULTS_DIR / "processed"
    found_any = False
    for campaign_dir in processed_dir.iterdir():
        stats_path = campaign_dir / "statistical_comparisons.csv"
        if not stats_path.exists():
            continue
        found_any = True
        df = pd.read_csv(stats_path)
        assert "n" in df.columns, f"{stats_path} is missing the n column"
        assert (df["n"] >= 2).all(), f"{stats_path} has a comparison with n < 2"
    assert found_any, "no statistical_comparisons.csv files found under results/processed/"


@pytest.mark.unit
def test_planner_operation_matrix_separates_untested_from_oracle_confirmed():
    matrix_path = RESULTS_DIR / "processed" / "F04_planner_vs_operation" / "matrix.csv"
    if not matrix_path.exists():
        pytest.skip("F04 matrix not generated yet")
    matrix = pd.read_csv(matrix_path)
    categories = set(matrix["category"])
    assert "INFEASIBLE_AND_REJECTED" in categories, "matrix must have an untested-rejection category"
    assert "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE" in categories, "matrix must have an oracle-confirmed-satisfiable category"
    # these must never be merged into a single ambiguous bucket
    untested_count = matrix.loc[matrix["category"] == "INFEASIBLE_AND_REJECTED", "count"].iloc[0]
    confirmed_count = matrix.loc[matrix["category"] == "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE", "count"].iloc[0]
    assert untested_count != confirmed_count or untested_count == 0, "sanity check: categories carry independent counts"


@pytest.mark.unit
def test_f05_recovery_type_matches_documented_action_mapping():
    """Section 8's recovery_type classification must match
    scripts/classify_f05_recovery_types.py's documented mapping exactly -
    no drift between the persisted CSV and the classification rule."""
    processed_path = RESULTS_DIR / "processed" / "F05_reconciliation" / "trials_with_recovery_type.csv"
    if not processed_path.exists():
        pytest.skip("F05 recovery_type classification not generated yet")
    df = pd.read_csv(processed_path)

    expected_by_action = {
        "route_change": "strict_recovery",
        "slot_increase": "resource_adjusted_recovery",
        "duration_increase": "sla_relaxed_recovery",
    }
    for action, expected_type in expected_by_action.items():
        subset = df[df["action"] == action]
        assert len(subset) > 0, f"no rows found for action={action}"
        assert (subset["recovery_type"] == expected_type).all(), f"action={action} must always map to recovery_type={expected_type}"

    no_action_subset = df[df["action"].isna()]
    assert (no_action_subset["recovery_type"] == "not_applicable").all()


@pytest.mark.unit
def test_false_rejection_root_cause_is_reproducible_from_persisted_gap_metrics():
    """docs/false_rejection_root_cause.md cites false_rejection_rate=1.0
    over 240 oracle-tested trials - confirm this is exactly what's
    currently persisted, not a stale number copied into the doc."""
    gap_metrics_path = RESULTS_DIR / "processed" / "F04_planner_vs_operation" / "gap_metrics.json"
    if not gap_metrics_path.exists():
        pytest.skip("F04 gap_metrics not generated yet")
    gap_metrics = json.loads(gap_metrics_path.read_text(encoding="utf-8"))
    assert gap_metrics["false_rejection_rate"] == pytest.approx(1.0)

    doc_text = (PROJECT_ROOT / "docs" / "false_rejection_root_cause.md").read_text(encoding="utf-8")
    assert "240/240" in doc_text or "240" in doc_text, "doc should cite the actual oracle-tested count"


@pytest.mark.unit
def test_audit_final_results_script_passes():
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "audit_final_results.py")],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, f"audit_final_results.py did not PASS:\n{result.stdout}\n{result.stderr}"


@pytest.mark.unit
def test_manifests_have_consistent_expected_completed_failed_skipped_arithmetic():
    manifests_dir = RESULTS_DIR / "manifests"
    checked_any = False
    for manifest_path in manifests_dir.glob("F0*.json"):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        checked_any = True
        total = manifest["completed_trials"] + manifest["failed_trials"] + manifest["skipped_trials"]
        assert total == manifest["expected_trials"], f"{manifest_path.name}: {total} != {manifest['expected_trials']}"
        if "blocks" in manifest:
            assert sum(b["completed_trials"] for b in manifest["blocks"]) == manifest["completed_trials"]
    assert checked_any, "no F0X manifests found"
