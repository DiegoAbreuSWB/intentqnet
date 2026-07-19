"""Unit tests for M10.2's `DeterministicExecutionContext` (`experiments.
deterministic_context`) - namespace seed derivation, RNG manifest,
subprocess-environment construction, and the "disabled by default" no-op
guarantee (existing campaigns must never be affected by this module
merely existing)."""
from __future__ import annotations

import random

import pytest

from ibqn.experiments.deterministic_context import (
    NAMESPACES,
    DeterminismConfig,
    apply_determinism,
    build_subprocess_environment,
    derive_namespace_seed,
)


@pytest.mark.unit
def test_disabled_config_is_a_full_noop():
    config = DeterminismConfig(enabled=False)
    execution_seed, manifest = apply_determinism(campaign_id="c", trial_id="t", config=config)
    assert execution_seed is None
    assert manifest.determinism_enabled is False
    assert manifest.namespace_seeds == {}
    assert manifest.python_random_reseeded is False


@pytest.mark.unit
def test_enabled_config_derives_execution_seed_and_reseeds_random():
    config = DeterminismConfig(enabled=True, master_seed=42)
    before_state = random.getstate()
    execution_seed, manifest = apply_determinism(campaign_id="c", trial_id="t", config=config)
    after_state = random.getstate()
    assert execution_seed is not None
    assert manifest.determinism_enabled is True
    assert manifest.python_random_reseeded is True
    assert before_state != after_state  # random.seed() changed the global state


@pytest.mark.unit
def test_namespace_seed_derivation_is_stable_across_calls():
    a = derive_namespace_seed(campaign_id="camp", trial_id="trial1", namespace="execution", master_seed=1)
    b = derive_namespace_seed(campaign_id="camp", trial_id="trial1", namespace="execution", master_seed=1)
    assert a == b


@pytest.mark.unit
def test_namespace_seed_derivation_differs_by_namespace():
    seeds = {
        ns: derive_namespace_seed(campaign_id="camp", trial_id="trial1", namespace=ns, master_seed=1)
        for ns in NAMESPACES
    }
    assert len(set(seeds.values())) == len(NAMESPACES)  # all distinct


@pytest.mark.unit
def test_namespace_seed_derivation_differs_by_trial_id():
    a = derive_namespace_seed(campaign_id="camp", trial_id="trial1", namespace="execution", master_seed=1)
    b = derive_namespace_seed(campaign_id="camp", trial_id="trial2", namespace="execution", master_seed=1)
    assert a != b


@pytest.mark.unit
def test_namespace_seed_derivation_differs_by_master_seed():
    a = derive_namespace_seed(campaign_id="camp", trial_id="trial1", namespace="execution", master_seed=1)
    b = derive_namespace_seed(campaign_id="camp", trial_id="trial1", namespace="execution", master_seed=2)
    assert a != b


@pytest.mark.unit
def test_unknown_namespace_rejected():
    with pytest.raises(ValueError):
        derive_namespace_seed(campaign_id="c", trial_id="t", namespace="not_a_real_namespace", master_seed=1)


@pytest.mark.unit
def test_all_seven_namespaces_present_when_enabled():
    config = DeterminismConfig(enabled=True, master_seed=1)
    _, manifest = apply_determinism(campaign_id="c", trial_id="t", config=config)
    assert set(manifest.namespace_seeds.keys()) == set(NAMESPACES)


@pytest.mark.unit
def test_manifest_records_full_provenance_fields():
    config = DeterminismConfig(enabled=True, master_seed=1)
    _, manifest = apply_determinism(
        campaign_id="c", trial_id="t", config=config, project_commit="abc123", sequence_commit="def456",
    )
    assert manifest.project_git_commit == "abc123"
    assert manifest.sequence_git_commit == "def456"
    assert manifest.python_version
    assert manifest.numpy_version
    assert manifest.platform_system
    assert manifest.hostname


@pytest.mark.unit
def test_subprocess_environment_pins_hash_seed_only_when_enabled():
    disabled_env = build_subprocess_environment(DeterminismConfig(enabled=False), base_env={"PATH": "x"})
    assert "PYTHONHASHSEED" not in disabled_env

    enabled_env = build_subprocess_environment(DeterminismConfig(enabled=True), base_env={"PATH": "x"})
    assert enabled_env["PYTHONHASHSEED"] == "0"


@pytest.mark.unit
def test_master_seed_derivation_is_not_pythons_native_hash():
    """Guards against accidentally using `hash()` (process-randomized by
    PYTHONHASHSEED, and not guaranteed stable across processes) instead
    of SHA-256 - the whole point of this derivation."""
    seed = derive_namespace_seed(campaign_id="c", trial_id="t", namespace="execution", master_seed=1)
    assert seed != hash(("c", "t", "execution", 1)) % (2 ** 63)
