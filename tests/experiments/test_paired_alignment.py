"""Tests for `ibqn.experiments.aggregation.align_paired_trials` (Fase H3.3,
section 17).

`parameter_hash` in these fixtures deliberately *differs* between the two
`strategy` values, exactly like a real campaign: `parameter_hash` is a
hash of the whole swept combination (see `sweeps.compute_parameter_hash`),
and `routing_strategy`/`purification_policy`/`reconciliation_enabled` are
themselves swept parameters via `CampaignSpec.effective_parameter_grid` -
so two trials that only differ in `compare` never share a
`parameter_hash`. An earlier version of these tests used the same fixed
`parameter_hash` for every row, which hid this until campaign C04 was
actually run (see docs/campaign_architecture.md).
"""
import pandas as pd
import pytest

from ibqn.experiments.aggregation import align_paired_trials

_PAIR_ON = ["scenario", "seed", "intent_id"]


def _trials_df():
    return pd.DataFrame([
        {"strategy": "a", "seed": 0, "scenario": "s", "parameter_hash": "hash-a", "intent_id": "i",
         "delivered_pairs": 10, "average_fidelity": 0.70, "accepted": True, "final_status": "SATISFIED", "recovered": None},
        {"strategy": "a", "seed": 1, "scenario": "s", "parameter_hash": "hash-a", "intent_id": "i",
         "delivered_pairs": 12, "average_fidelity": 0.71, "accepted": True, "final_status": "SATISFIED", "recovered": None},
        {"strategy": "b", "seed": 0, "scenario": "s", "parameter_hash": "hash-b", "intent_id": "i",
         "delivered_pairs": 400, "average_fidelity": 0.60, "accepted": True, "final_status": "VIOLATED", "recovered": False},
        {"strategy": "b", "seed": 1, "scenario": "s", "parameter_hash": "hash-b", "intent_id": "i",
         "delivered_pairs": 420, "average_fidelity": 0.61, "accepted": True, "final_status": "SATISFIED", "recovered": True},
    ])


@pytest.mark.unit
def test_align_paired_trials_matches_by_shared_keys():
    df = _trials_df()
    paired = align_paired_trials(df, pair_on=_PAIR_ON, compare="strategy", metrics=["delivered_pairs"])
    assert len(paired) == 2  # seed 0 and seed 1, each pairing strategy a vs b
    assert paired["paired"].all()
    row_seed0 = paired[paired["seed"] == 0].iloc[0]
    assert row_seed0["delivered_pairs_a"] == 10
    assert row_seed0["delivered_pairs_b"] == 400
    assert row_seed0["delivered_pairs_diff"] == 390


@pytest.mark.unit
def test_including_parameter_hash_in_pair_on_breaks_pairing():
    """Regression test: `parameter_hash` differs across `compare` values in
    real campaign data (see the module docstring), so including it in
    `pair_on` must make every row fail to pair - documenting the pitfall
    found running campaign C04, not silently "fixing" it here."""
    df = _trials_df()
    paired = align_paired_trials(
        df, pair_on=_PAIR_ON + ["parameter_hash"], compare="strategy", metrics=["delivered_pairs"],
    )
    assert not paired["paired"].any()


@pytest.mark.unit
def test_align_paired_trials_reports_missing_pairs_explicitly():
    df = _trials_df()
    # drop strategy "b"'s seed=1 row, leaving seed=1 unpaired
    df = df.drop(index=3).reset_index(drop=True)
    paired = align_paired_trials(df, pair_on=_PAIR_ON, compare="strategy", metrics=["delivered_pairs"])
    assert len(paired) == 2
    unpaired_row = paired[paired["seed"] == 1].iloc[0]
    assert unpaired_row["paired"] == False  # noqa: E712 (explicit bool comparison for clarity)
    assert pd.isna(unpaired_row["delivered_pairs_b"])
    assert pd.isna(unpaired_row["delivered_pairs_diff"])


@pytest.mark.unit
def test_align_paired_trials_requires_exactly_two_compare_values():
    df = _trials_df()
    df.loc[len(df)] = {
        "strategy": "c", "seed": 0, "scenario": "s", "parameter_hash": "hash-c", "intent_id": "i",
        "delivered_pairs": 1, "average_fidelity": 0.5, "accepted": True, "final_status": "SATISFIED", "recovered": None,
    }
    with pytest.raises(ValueError, match="exactly 2 distinct values"):
        align_paired_trials(df, pair_on=_PAIR_ON, compare="strategy")


@pytest.mark.unit
def test_align_paired_trials_diff_direction_is_b_minus_a_alphabetically():
    """`compare` values are sorted alphabetically to decide which side is
    "a" and which is "b" - deterministic regardless of row order."""
    df = _trials_df()
    paired = align_paired_trials(df, pair_on=_PAIR_ON, compare="strategy", metrics=["delivered_pairs"])
    row_seed0 = paired[paired["seed"] == 0].iloc[0]
    # "a" < "b" alphabetically, so diff = b - a = 400 - 10 = 390 (not -390)
    assert row_seed0["delivered_pairs_diff"] == 400 - 10
