"""Fase K1 final-results audit: cross-checks every final campaign
(F01-F08) across manifest, trials.csv, and (where applicable) processed
outputs, and reports PASS/FAIL per campaign plus a small number of
cross-campaign checks (F04's derivation from F02+F03, and whether final
figures/tables exist with an identifiable data source).

Read-only: never modifies results/raw, results/processed, or
results/manifests. Run after any campaign or manifest change to confirm
nothing drifted; re-run after Fase K2/K4 (figures/notebooks) for the
full PASS across every check.

Usage: python scripts/audit_final_results.py
Writes: results/audit/final_results_audit.json, .md
Exit code: 0 if every campaign PASSes, 1 otherwise (CI-friendly).
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"

FINAL_CAMPAIGNS = [
    "F01_architecture_baselines", "F02_routing", "F03_purification", "F05_reconciliation",
    "F06_overhead", "F07_estimators", "F08_resource_semantics",
]
PILOT_CAMPAIGNS = ["C01_routing_strategy", "C02_fidelity_throughput", "C03_assurance_outcomes", "C04_reconciliation_effectiveness"]

# Campaigns whose trials.csv has no `trial_id` column (ad-hoc scripts,
# not run_programmatic_campaign/CampaignRunner) - uniqueness/grouping
# falls back to this logical key instead.
FALLBACK_KEY_COLUMNS = {
    "F01_architecture_baselines": ["condition", "seed"],
    "F05_reconciliation": ["case", "seed"],
    "F06_overhead": ["condition", "seed"],
}

# swept_factors key -> trials.csv column name, where they differ.
GRID_KEY_TO_COLUMN = {
    "min_fidelity": "requested_fidelity",
    "condition": "condition",
    "case": "case",
}


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | FAIL | WARN | SKIP
    detail: str


@dataclass
class CampaignAudit:
    campaign: str
    checks: list[CheckResult] = field(default_factory=list)
    expected_trials: int | None = None
    raw_rows: int | None = None
    processed_rows: int | None = None
    manifest_status: str = "unknown"

    @property
    def overall(self) -> str:
        if any(c.status == "FAIL" for c in self.checks):
            return "FAIL"
        if any(c.status == "WARN" for c in self.checks):
            return "WARN"
        return "PASS"


def _manifest_path(campaign: str) -> Path:
    return RESULTS_DIR / "manifests" / f"{campaign}.json"


def _trials_path(campaign: str) -> Path:
    return RESULTS_DIR / "raw" / campaign / "trials.csv"


def _key_columns(campaign: str, df: pd.DataFrame) -> list[str]:
    if "trial_id" in df.columns:
        return ["trial_id"]
    return FALLBACK_KEY_COLUMNS[campaign]


def audit_campaign(campaign: str) -> CampaignAudit:
    audit = CampaignAudit(campaign=campaign)
    manifest_file = _manifest_path(campaign)
    trials_file = _trials_path(campaign)

    if not trials_file.exists():
        audit.checks.append(CheckResult("trials_csv_exists", "FAIL", f"missing: {trials_file}"))
        return audit
    df = pd.read_csv(trials_file)
    audit.raw_rows = len(df)
    audit.checks.append(CheckResult("trials_csv_exists", "PASS", f"{len(df)} rows"))

    if not manifest_file.exists():
        audit.checks.append(CheckResult("manifest_exists", "FAIL", f"missing: {manifest_file}"))
        return audit
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    audit.manifest_status = "present"
    audit.checks.append(CheckResult("manifest_exists", "PASS", str(manifest_file.name)))

    # 1. expected == completed + failed + skipped
    expected = manifest["expected_trials"]
    audit.expected_trials = expected
    total = manifest["completed_trials"] + manifest["failed_trials"] + manifest["skipped_trials"]
    if total == expected:
        audit.checks.append(CheckResult("manifest_arithmetic", "PASS", f"{expected} == {manifest['completed_trials']}+{manifest['failed_trials']}+{manifest['skipped_trials']}"))
    else:
        audit.checks.append(CheckResult("manifest_arithmetic", "FAIL", f"expected={expected} != completed({manifest['completed_trials']})+failed({manifest['failed_trials']})+skipped({manifest['skipped_trials']})={total}"))

    # 2. trials.csv row count matches manifest's completed_trials
    if len(df) == manifest["completed_trials"]:
        audit.checks.append(CheckResult("row_count_matches_manifest", "PASS", f"{len(df)} rows == completed_trials"))
    else:
        audit.checks.append(CheckResult("row_count_matches_manifest", "FAIL", f"{len(df)} rows != completed_trials ({manifest['completed_trials']})"))

    # 3. key uniqueness (trial_id, or a campaign-specific fallback key)
    key_cols = _key_columns(campaign, df)
    n_dupes = int(df.duplicated(subset=key_cols).sum())
    if n_dupes == 0:
        audit.checks.append(CheckResult("key_uniqueness", "PASS", f"0 duplicates on {key_cols}"))
    else:
        audit.checks.append(CheckResult("key_uniqueness", "FAIL", f"{n_dupes} duplicate rows on {key_cols}"))

    # 4. every block's seeds/expected count show up in trials.csv exactly
    for block in manifest["blocks"]:
        scenario = block["scenario"]
        scenario_col = "scenario" if "scenario" in df.columns else ("condition" if campaign in ("F01_architecture_baselines", "F06_overhead") else "case")
        if scenario_col == "condition" or scenario_col == "case":
            # F01/F05/F06: one block IS the scenario/case itself (no separate scenario column beyond the key column)
            block_rows = df[df[scenario_col] == scenario] if campaign == "F05_reconciliation" else df
        else:
            block_rows = df[df[scenario_col] == scenario]

        actual_seeds = set(int(s) for s in block_rows["seed"].unique())
        expected_seeds = set(block["seeds"])
        if actual_seeds == expected_seeds:
            audit.checks.append(CheckResult(f"seeds_complete[{scenario}]", "PASS", f"{len(actual_seeds)} seeds present"))
        else:
            missing = expected_seeds - actual_seeds
            extra = actual_seeds - expected_seeds
            audit.checks.append(CheckResult(f"seeds_complete[{scenario}]", "FAIL", f"missing={sorted(missing)} extra={sorted(extra)}"))

        if len(block_rows) == block["expected_trials"]:
            audit.checks.append(CheckResult(f"block_row_count[{scenario}]", "PASS", f"{len(block_rows)} rows"))
        else:
            audit.checks.append(CheckResult(f"block_row_count[{scenario}]", "FAIL", f"{len(block_rows)} rows != expected {block['expected_trials']}"))

        # every combination of swept_factors x seeds appears exactly once
        swept = block.get("swept_factors") or {}
        if swept and scenario_col not in ("condition",):
            import itertools
            keys = sorted(swept)
            columns = [GRID_KEY_TO_COLUMN.get(k, k) for k in keys]
            if all(c in block_rows.columns for c in columns):
                combos = list(itertools.product(*[swept[k] for k in keys]))
                bad_combos = []
                for combo in combos:
                    mask = pd.Series(True, index=block_rows.index)
                    for col, value in zip(columns, combo):
                        mask &= (block_rows[col] == value)
                    count = int(mask.sum())
                    if count != len(block["seeds"]):
                        bad_combos.append((combo, count))
                if not bad_combos:
                    audit.checks.append(CheckResult(f"grid_combinations_complete[{scenario}]", "PASS", f"{len(combos)} combinations x {len(block['seeds'])} seeds"))
                else:
                    audit.checks.append(CheckResult(f"grid_combinations_complete[{scenario}]", "FAIL", f"bad combos: {bad_combos[:5]}"))

    # 5. commit consistency (only for campaigns with a per-row commit column)
    if "project_git_commit" in df.columns:
        commit_counts = df["project_git_commit"].dropna().value_counts().to_dict()
        if len(commit_counts) <= 1:
            audit.checks.append(CheckResult("commit_consistency", "PASS", f"single commit: {list(commit_counts)}"))
        else:
            # Not automatically wrong: a campaign legitimately extended in a
            # later session (e.g. denser thresholds added to an existing
            # scenario, Fase K2) will have >1 commit, each internally
            # consistent for the rows it covers - see the manifest's
            # per-block history. Flagged for a human to double-check, not
            # auto-failed.
            audit.checks.append(CheckResult(
                "commit_consistency", "WARN",
                f"multiple commits (check manifest blocks - may be a legitimately extended campaign): {commit_counts}",
            ))
    else:
        audit.checks.append(CheckResult(
            "commit_consistency", "WARN",
            "no per-row project_git_commit column (ad-hoc script - see docs/results_provenance.md known gap)",
        ))

    return audit


def audit_f04_derivation() -> CheckResult:
    combined_path = RESULTS_DIR / "processed" / "F04_planner_vs_operation" / "combined_trials_with_categories.csv"
    if not combined_path.exists():
        return CheckResult("f04_derives_from_f02_f03", "FAIL", f"missing: {combined_path}")
    combined = pd.read_csv(combined_path)
    f02 = pd.read_csv(_trials_path("F02_routing"))
    f03 = pd.read_csv(_trials_path("F03_purification"))
    expected_ids = set(f02["trial_id"]) | set(f03["trial_id"])
    actual_ids = set(combined["trial_id"])
    if len(combined) == len(f02) + len(f03) and actual_ids == expected_ids:
        return CheckResult("f04_derives_from_f02_f03", "PASS", f"{len(combined)} rows == {len(f02)} (F02) + {len(f03)} (F03), trial_id sets match")
    return CheckResult(
        "f04_derives_from_f02_f03", "FAIL",
        f"{len(combined)} rows vs {len(f02)}+{len(f03)}={len(f02) + len(f03)}; trial_id set match: {actual_ids == expected_ids}",
    )


def audit_final_figures() -> list[CheckResult]:
    figures_dir = RESULTS_DIR / "figures" / "final"
    if not figures_dir.exists():
        return [CheckResult("final_figures_present", "SKIP", "results/figures/final/ does not exist yet (Fase K2 not run)")]

    checks = []
    sources_file = figures_dir / "sources.json"
    if not sources_file.exists():
        checks.append(CheckResult("final_figures_have_sources_json", "FAIL", f"missing: {sources_file}"))
        return checks
    sources = json.loads(sources_file.read_text(encoding="utf-8"))
    checks.append(CheckResult("final_figures_have_sources_json", "PASS", f"{len(sources)} entries"))

    pdfs = sorted(p.stem for p in figures_dir.glob("*.pdf"))
    pngs = sorted(p.stem for p in figures_dir.glob("*.png"))
    if pdfs and set(pdfs) == set(pngs):
        checks.append(CheckResult("every_figure_has_pdf_and_png", "PASS", f"{len(pdfs)} figures"))
    else:
        checks.append(CheckResult("every_figure_has_pdf_and_png", "FAIL", f"pdf-only: {set(pdfs) - set(pngs)}, png-only: {set(pngs) - set(pdfs)}"))

    missing_source = [name for name in pdfs if name not in sources]
    if not missing_source:
        checks.append(CheckResult("every_figure_has_identifiable_source", "PASS", "all figures listed in sources.json"))
    else:
        checks.append(CheckResult("every_figure_has_identifiable_source", "FAIL", f"no source entry: {missing_source}"))

    return checks


def render_markdown(campaign_audits: list[CampaignAudit], cross_checks: list[CheckResult]) -> str:
    lines = ["# Final results audit (Fase K1)\n"]
    lines.append("| Campaign | Expected | Raw rows | Manifest | Audit |")
    lines.append("|---|---:|---:|---|---|")
    for a in campaign_audits:
        lines.append(f"| {a.campaign} | {a.expected_trials} | {a.raw_rows} | {a.manifest_status} | {a.overall} |")
    lines.append("")

    for a in campaign_audits:
        lines.append(f"## {a.campaign} - {a.overall}\n")
        lines.append("| Check | Status | Detail |")
        lines.append("|---|---|---|")
        for c in a.checks:
            lines.append(f"| {c.name} | {c.status} | {c.detail} |")
        lines.append("")

    lines.append("## Cross-campaign checks\n")
    lines.append("| Check | Status | Detail |")
    lines.append("|---|---|---|")
    for c in cross_checks:
        lines.append(f"| {c.name} | {c.status} | {c.detail} |")

    return "\n".join(lines) + "\n"


def main() -> int:
    campaign_audits = [audit_campaign(name) for name in FINAL_CAMPAIGNS]
    cross_checks = [audit_f04_derivation(), *audit_final_figures()]

    audit_dir = RESULTS_DIR / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)

    json_report = {
        "campaigns": {
            a.campaign: {
                "overall": a.overall, "expected_trials": a.expected_trials, "raw_rows": a.raw_rows,
                "manifest_status": a.manifest_status,
                "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in a.checks],
            }
            for a in campaign_audits
        },
        "cross_campaign_checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in cross_checks],
        "pilot_campaigns_excluded_from_final_audit": PILOT_CAMPAIGNS,
    }
    (audit_dir / "final_results_audit.json").write_text(json.dumps(json_report, indent=2), encoding="utf-8")
    (audit_dir / "final_results_audit.md").write_text(render_markdown(campaign_audits, cross_checks), encoding="utf-8")

    any_fail = any(a.overall == "FAIL" for a in campaign_audits) or any(c.status == "FAIL" for c in cross_checks)
    for a in campaign_audits:
        print(f"{a.campaign}: {a.overall}")
    print(f"cross-campaign: {'FAIL' if any(c.status == 'FAIL' for c in cross_checks) else 'PASS'}")
    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(main())
