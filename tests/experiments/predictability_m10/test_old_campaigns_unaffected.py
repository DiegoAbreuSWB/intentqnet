"""Guards against M10 accidentally touching frozen prior-phase data -
P01-P02B/P03 (planner-family study) and M9's own predictability
campaigns must be untouched by anything M10 adds."""
from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Row counts as of the end of each frozen phase (header + data rows) -
# a regression guard, not a cryptographic proof: if M10 code accidentally
# appended to or truncated one of these files, this catches it immediately.
EXPECTED_ROW_COUNTS = {
    "results/planner_study/raw/P01_l1_l2_purification_three_node/trials.csv": 321,
    "results/planner_study/raw/P01_l1_l2_purification_four_node/trials.csv": 321,
    "results/planner_study/raw/P02_l1_l2_l3/trials.csv": 361,
    "results/planner_study/raw/P02b_resource_aware_planners/trials.csv": 1201,
    "results/planner_study/raw/P03_l4_cost/trials.csv": 61,
    "results/predictability/raw/P04_retry_storm/trials.csv": 41,
    "results/predictability/raw/P02_variance/trials.csv": 201,
}


@pytest.mark.unit
@pytest.mark.parametrize("relative_path", list(EXPECTED_ROW_COUNTS.keys()))
def test_frozen_campaign_row_count_unchanged(relative_path):
    path = PROJECT_ROOT / relative_path
    if not path.exists():
        pytest.skip(f"{relative_path} not present in this checkout")
    with open(path, encoding="utf-8") as f:
        n_lines = sum(1 for _ in f)
    assert n_lines == EXPECTED_ROW_COUNTS[relative_path], (
        f"{relative_path} row count changed ({n_lines} != {EXPECTED_ROW_COUNTS[relative_path]}) - "
        "a frozen prior-phase campaign must never be modified"
    )


@pytest.mark.unit
def test_m10_writes_to_its_own_directory_only():
    from ibqn.experiments.predictability_m10_records import trials_csv_path

    path = trials_csv_path("results/predictability_m10", "P10_replay_determinism")
    assert "predictability_m10" in str(path)
    assert "planner_study" not in str(path)
    assert str(path).count("predictability/raw") == 0  # never M9's own directory either
