"""Tests for `ibqn.experiments.validation` (Fase H3.3)."""
import pandas as pd
import pytest

from ibqn.experiments.validation import validate_trials

_BASE_ROW = {
    "trial_id": "t1", "final_status": "SATISFIED", "satisfied": True, "accepted": True,
    "violations": "", "delivered_pairs": 10, "requested_pairs": 10, "excess_delivery_pairs": 0,
    "average_fidelity": 0.7, "minimum_fidelity": 0.65, "requested_fidelity": 0.6, "hop_count": 2,
    "eg_attempts": 10, "eg_success": 8, "ep_attempts": None, "ep_success": None,
    "es_attempts": None, "es_success": None, "throughput_active_window": 100.0,
    "throughput_delivery_interval": 100.0, "completion_time_s": 0.01, "recovered": None,
}


def _row(**overrides):
    row = dict(_BASE_ROW)
    row.update(overrides)
    return pd.DataFrame([row])


@pytest.mark.unit
def test_valid_row_has_no_issues():
    assert validate_trials(_row()) == []


@pytest.mark.unit
def test_fidelity_out_of_range_is_flagged():
    issues = validate_trials(_row(average_fidelity=1.5))
    assert any(i.check == "fidelity_range" for i in issues)


@pytest.mark.unit
def test_negative_count_is_flagged():
    issues = validate_trials(_row(delivered_pairs=-1))
    assert any(i.check == "nonnegative_count" for i in issues)


@pytest.mark.unit
def test_non_integer_count_is_flagged():
    issues = validate_trials(_row(delivered_pairs=3.5))
    assert any(i.check == "integer_count" for i in issues)


@pytest.mark.unit
def test_negative_throughput_is_flagged():
    issues = validate_trials(_row(throughput_active_window=-5.0))
    assert any(i.check == "nonnegative_throughput" for i in issues)


@pytest.mark.unit
def test_satisfied_status_requires_satisfied_true():
    issues = validate_trials(_row(final_status="SATISFIED", satisfied=False))
    assert any(i.check == "satisfied_status_consistency" for i in issues)


@pytest.mark.unit
def test_violated_status_requires_violations():
    issues = validate_trials(_row(final_status="VIOLATED", satisfied=False, violations=""))
    assert any(i.check == "violated_has_violations" for i in issues)


@pytest.mark.unit
def test_rejected_status_must_not_be_accepted():
    issues = validate_trials(_row(final_status="REJECTED", accepted=True, delivered_pairs=None))
    assert any(i.check == "rejected_not_accepted" for i in issues)


@pytest.mark.unit
def test_rejected_status_must_have_no_delivery_evidence():
    issues = validate_trials(_row(final_status="REJECTED", accepted=False, delivered_pairs=5))
    assert any(i.check == "rejected_no_evidence" for i in issues)


@pytest.mark.unit
def test_recovered_true_requires_satisfied_final_status():
    issues = validate_trials(_row(recovered=True, final_status="VIOLATED", satisfied=False))
    assert any(i.check == "recovered_implies_satisfied" for i in issues)


@pytest.mark.unit
def test_excess_delivery_pairs_must_match_formula():
    issues = validate_trials(_row(delivered_pairs=10, requested_pairs=10, excess_delivery_pairs=5))
    assert any(i.check == "excess_delivery_consistency" for i in issues)


@pytest.mark.unit
def test_excess_delivery_pairs_correct_when_matching_formula():
    issues = validate_trials(_row(delivered_pairs=15, requested_pairs=10, excess_delivery_pairs=5))
    assert not any(i.check == "excess_delivery_consistency" for i in issues)


@pytest.mark.unit
def test_completion_time_requires_full_delivery():
    issues = validate_trials(_row(delivered_pairs=3, requested_pairs=10, completion_time_s=0.01))
    assert any(i.check == "completion_time_requires_full_delivery" for i in issues)


@pytest.mark.unit
def test_missing_values_do_not_raise_or_get_flagged():
    """None/NaN fields (e.g. a REJECTED trial's fidelity fields) must be
    skipped by every check, never coerced to 0 and flagged as a fake
    violation."""
    issues = validate_trials(_row(
        final_status="REJECTED", accepted=False, satisfied=False, delivered_pairs=None,
        average_fidelity=None, minimum_fidelity=None, excess_delivery_pairs=None,
        completion_time_s=None, hop_count=None,
    ))
    assert issues == []


@pytest.mark.unit
def test_validate_trials_on_empty_dataframe_returns_no_issues():
    empty = pd.DataFrame(columns=list(_BASE_ROW))
    assert validate_trials(empty) == []
