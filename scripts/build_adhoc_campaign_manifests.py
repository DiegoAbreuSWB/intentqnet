"""Builds manifests for the three final campaigns that were run via a
standalone script rather than `run_programmatic_campaign`/`CampaignRunner`
(F01_architecture_baselines, F05_reconciliation, F06_overhead - see
docs/results_provenance.md) - found missing entirely during the Fase K1
audit. Derives `expected_trials`/`completed_trials` from the persisted
`trials.csv` (ground truth), never from assumption. Safe to re-run: it
only (re)writes `results/manifests/*.json`, never touches raw results.

`project_git_commit`/`sequence_git_commit`/`created_at` for these three
campaigns are INFERRED, not recorded (no manifest existed at execution
time to capture them) - see `INFERRED_ENV_NOTE` below for the reasoning,
and `docs/results_provenance.md` for the disclosed limitation.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = PROJECT_ROOT / "results"

COMMON_ENV = {
    "python_version": "3.13.14",
    "platform": "Windows-11-10.0.26200-SP0",
    "dependencies": {
        "pydantic": "2.13.4", "yaml": "6.0.3", "networkx": "3.6.1", "numpy": "2.5.1",
        "scipy": "1.18.0", "matplotlib": "3.11.0", "pandas": "3.0.3", "qutip": "5.3.0",
        "stim": "1.16.0", "gmpy2": "2.3.1", "nbformat": "5.10.4", "nbclient": "0.11.0",
    },
}
INFERRED_PROJECT_COMMIT = "f4343c314e5de5e01ee6970aaa14b5974c1b49ea"
INFERRED_SEQUENCE_COMMIT = "1f2680a5b9065e708a7497adc53a95b108029b98"
INFERRED_ENV_NOTE = (
    "No manifest was written at execution time (this campaign ran via a "
    "standalone script, not run_programmatic_campaign/CampaignRunner - see "
    "docs/results_provenance.md). created_at is unknown for the same reason. "
    "project_git_commit/sequence_git_commit/python_version/platform/"
    "dependencies are INFERRED, not recorded: this campaign ran in the same "
    "uninterrupted working session as F02/F03/F07/F08 (which did record "
    "their environment), strictly before any Fase J10 commit was made - so "
    "the environment must be identical to theirs (project_git_commit "
    "f4343c3, the last commit before any Fase J10 commit landed). Per-row "
    "project_git_commit/sequence_git_commit columns are absent from this "
    "campaign's trials.csv for the same reason (F01's execute_trial-based "
    "rows even pass project_commit=None/sequence_commit=None explicitly) - "
    "a known, disclosed traceability gap, not a fabricated value; see "
    "docs/results_provenance.md and results/audit/final_results_audit.md."
)


def write_manifest(campaign: str, description: str, blocks: list[dict], output_files: list[str]) -> None:
    manifest = {
        "campaign": campaign,
        "description": description,
        "created_at": None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "project_git_commit": INFERRED_PROJECT_COMMIT,
        "sequence_git_commit": INFERRED_SEQUENCE_COMMIT,
        **COMMON_ENV,
        "campaign_file": None,
        "execution_path": "ad_hoc_script (not run_programmatic_campaign/CampaignRunner)",
        "provenance_note": INFERRED_ENV_NOTE,
        "blocks": blocks,
        "scenario_files": [b["scenario"] for b in blocks],
        "intent_files": sorted({name for b in blocks for name in b["intent_files"]}),
        "seeds": sorted({seed for b in blocks for seed in b["seeds"]}),
        "expected_trials": sum(b["expected_trials"] for b in blocks),
        "completed_trials": sum(b["completed_trials"] for b in blocks),
        "skipped_trials": 0,
        "failed_trials": 0,
        "output_files": output_files,
    }
    out_path = RESULTS_DIR / "manifests" / f"{campaign}.json"
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"wrote {out_path}: expected={manifest['expected_trials']} completed={manifest['completed_trials']}")


def build_f01() -> None:
    f01 = pd.read_csv(RESULTS_DIR / "raw" / "F01_architecture_baselines" / "trials.csv")
    assert len(f01) == 120, f"expected 120 rows, found {len(f01)} - trials.csv changed since this script was written"
    write_manifest(
        "F01_architecture_baselines",
        "Fase J10 final campaign: F01_architecture_baselines - isolates the benefit of route "
        "choice/assurance/reconciliation and the cost of the intent-based abstraction.",
        blocks=[{
            "scenario": "diamond_heterogeneous",
            "intent_files": ["intent-diamond-demo"],
            "base_configuration": {
                "reserved_memory_slots": 10, "min_fidelity": 0.6, "stop_time_s": 0.2,
                "routing_strategy_where_applicable": "shortest_hop_count",
                "purification_policy_where_applicable": "automatic",
                "fidelity_estimator_where_applicable": "conservative_min",
            },
            "swept_factors": {"condition": sorted(f01["condition"].unique().tolist())},
            "seeds": sorted(f01["seed"].unique().tolist()),
            "expected_trials": 120, "completed_trials": len(f01), "skipped_trials": 0, "failed_trials": 0,
        }],
        output_files=[str(RESULTS_DIR / "raw" / "F01_architecture_baselines" / "trials.csv")],
    )


def build_f05() -> None:
    f05 = pd.read_csv(RESULTS_DIR / "raw" / "F05_reconciliation" / "trials.csv")
    assert len(f05) == 100, f"expected 100 rows, found {len(f05)} - trials.csv changed since this script was written"
    case_config = {
        "route_change_recoverable": {"topology": "diamond_spec()", "intent": "diamond_intent(requested_pairs=10, min_fidelity=0.6)"},
        "duration_increase_recoverable": {"topology": "three_node_spec(attenuation_db_per_m=0.01, stop_time_s=0.3)", "intent": "min_fidelity=0.6, min_delivered_pairs=30, duration=0.03"},
        "slot_increase_recoverable": {"topology": "three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.3, repeater_memories=40, end_memories=20)", "intent": "min_fidelity=0.6, min_delivered_pairs=30, duration=0.02, reserved_memory_slots=2"},
        "fidelity_ceiling_unrecoverable": {"topology": "three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)", "intent": "min_fidelity=0.9, min_delivered_pairs=10, duration=0.1"},
        "severe_loss_attempt": {"topology": "three_node_spec(attenuation_db_per_m=0.03, stop_time_s=0.3)", "intent": "min_fidelity=0.6, min_delivered_pairs=60, duration=0.03"},
    }
    blocks = []
    for case, cfg in case_config.items():
        case_rows = f05[f05["case"] == case]
        blocks.append({
            "scenario": case,
            "intent_files": [f"f05-{case}"],
            "base_configuration": cfg,
            "swept_factors": {},
            "seeds": sorted(case_rows["seed"].unique().tolist()),
            "expected_trials": 20, "completed_trials": len(case_rows), "skipped_trials": 0, "failed_trials": 0,
        })
    assert sum(b["completed_trials"] for b in blocks) == 100
    write_manifest(
        "F05_reconciliation",
        "Fase J10 final campaign: F05_reconciliation - reconciliation coverage across 5 "
        "recoverable/unrecoverable scenario classes, 20 seeds each.",
        blocks=blocks,
        output_files=[str(RESULTS_DIR / "raw" / "F05_reconciliation" / "trials.csv")],
    )


def build_f06() -> None:
    f06 = pd.read_csv(RESULTS_DIR / "raw" / "F06_overhead" / "trials.csv")
    assert len(f06) == 60, f"expected 60 rows, found {len(f06)} - trials.csv changed since this script was written"
    write_manifest(
        "F06_overhead",
        "Fase J10 final campaign: F06_overhead - per-stage wall-clock overhead decomposition "
        "(run_instrumented_trial) versus native/static baselines.",
        blocks=[{
            "scenario": "diamond_heterogeneous",
            "intent_files": ["intent-diamond-demo"],
            "base_configuration": {
                "reserved_memory_slots": 10, "min_fidelity": 0.6, "stop_time_s": 0.2,
                "routing_strategy": "shortest_hop_count", "purification_policy": "automatic",
                "fidelity_estimator": "conservative_min", "reconciliation_enabled": True,
            },
            "swept_factors": {"condition": sorted(f06["condition"].unique().tolist())},
            "seeds": sorted(f06["seed"].unique().tolist()),
            "expected_trials": 60, "completed_trials": len(f06), "skipped_trials": 0, "failed_trials": 0,
        }],
        output_files=[str(RESULTS_DIR / "raw" / "F06_overhead" / "trials.csv")],
    )


if __name__ == "__main__":
    build_f01()
    build_f05()
    build_f06()
    print("DONE")
