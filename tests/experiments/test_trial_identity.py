"""Tests for `ibqn.experiments.records.TrialIdentity` (Fase H3.1)."""
import pytest

from ibqn.experiments.records import TrialIdentity
from ibqn.experiments.sweeps import compute_parameter_hash


@pytest.mark.unit
def test_trial_id_is_stable_for_the_same_identity():
    identity_a = TrialIdentity(
        campaign="C01", scenario="diamond", parameter_hash="abc123",
        strategy="shortest_hop_count", seed=42, intent_id="intent-001",
    )
    identity_b = TrialIdentity(
        campaign="C01", scenario="diamond", parameter_hash="abc123",
        strategy="shortest_hop_count", seed=42, intent_id="intent-001",
    )
    assert identity_a.trial_id == identity_b.trial_id


@pytest.mark.unit
def test_trial_id_differs_when_any_field_differs():
    base = dict(campaign="C01", scenario="diamond", parameter_hash="abc123", strategy="shortest_hop_count", seed=42, intent_id="intent-001")
    base_id = TrialIdentity(**base).trial_id

    for field_name, new_value in [
        ("campaign", "C02"), ("scenario", "linear"), ("parameter_hash", "def456"),
        ("strategy", "least_loss"), ("seed", 43), ("intent_id", "intent-002"),
    ]:
        varied = dict(base, **{field_name: new_value})
        assert TrialIdentity(**varied).trial_id != base_id, f"changing '{field_name}' must change trial_id"


@pytest.mark.unit
def test_trial_id_is_not_a_sequential_index():
    """trial_id must be derivable purely from the identity fields - never
    depend on execution order (e.g. an incrementing counter)."""
    identity = TrialIdentity(
        campaign="C01", scenario="diamond", parameter_hash=compute_parameter_hash({"min_fidelity": 0.65}),
        strategy="shortest_hop_count", seed=42, intent_id="intent-001",
    )
    assert identity.trial_id == "C01:diamond:" + compute_parameter_hash({"min_fidelity": 0.65}) + ":shortest_hop_count:42:intent-001"


@pytest.mark.unit
def test_same_seed_and_configuration_reproduce_the_same_trial_id():
    """Same configuration (parameters serialized identically) + same seed
    => same trial_id, regardless of how many times it's computed."""
    parameters = {"min_fidelity": 0.7, "attenuation_db_per_m": 2e-5}
    ids = [
        TrialIdentity(
            campaign="C02", scenario="diamond", parameter_hash=compute_parameter_hash(parameters),
            strategy="automatic", seed=1042, intent_id="intent-001",
        ).trial_id
        for _ in range(5)
    ]
    assert len(set(ids)) == 1
