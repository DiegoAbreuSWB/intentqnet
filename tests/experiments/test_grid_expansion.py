"""Tests for `ibqn.experiments.sweeps.expand_parameter_grid` (Fase H3.1)."""
import json

import pytest

from ibqn.experiments.sweeps import (
    InvalidSweepValueError,
    UnknownSweepParameterError,
    compute_parameter_hash,
    expand_parameter_grid,
)


@pytest.mark.unit
def test_empty_grid_yields_one_empty_combination():
    assert expand_parameter_grid({}) == [{}]


@pytest.mark.unit
def test_cartesian_product_size_and_content():
    combos = expand_parameter_grid({
        "min_fidelity": [0.65, 0.75, 0.85],
        "attenuation_db_per_m": [1e-5, 2e-5],
    })
    assert len(combos) == 6
    assert {"min_fidelity": 0.65, "attenuation_db_per_m": 1e-5} in combos
    assert {"min_fidelity": 0.85, "attenuation_db_per_m": 2e-5} in combos


@pytest.mark.unit
def test_expansion_order_is_deterministic_regardless_of_dict_order():
    grid_a = {"min_fidelity": [0.65, 0.75], "attenuation_db_per_m": [1e-5, 2e-5]}
    grid_b = {"attenuation_db_per_m": [1e-5, 2e-5], "min_fidelity": [0.65, 0.75]}
    assert expand_parameter_grid(grid_a) == expand_parameter_grid(grid_b)


@pytest.mark.unit
def test_rejects_unknown_parameter():
    with pytest.raises(UnknownSweepParameterError):
        expand_parameter_grid({"not_a_real_param": [1]})


@pytest.mark.unit
def test_rejects_empty_value_list():
    with pytest.raises(ValueError, match="empty value list"):
        expand_parameter_grid({"min_fidelity": []})


@pytest.mark.unit
def test_rejects_wrong_value_type():
    with pytest.raises(InvalidSweepValueError):
        expand_parameter_grid({"min_fidelity": ["not-a-float"]})


@pytest.mark.unit
def test_each_combination_is_json_serializable():
    combos = expand_parameter_grid({"routing_strategy": ["shortest_hop_count", "least_loss"]})
    for combo in combos:
        json.dumps(combo)  # must not raise


@pytest.mark.unit
def test_parameter_hash_is_stable_across_key_order():
    hash_a = compute_parameter_hash({"a": 1, "b": 2})
    hash_b = compute_parameter_hash({"b": 2, "a": 1})
    assert hash_a == hash_b


@pytest.mark.unit
def test_parameter_hash_changes_with_different_values():
    hash_a = compute_parameter_hash({"min_fidelity": 0.65})
    hash_b = compute_parameter_hash({"min_fidelity": 0.70})
    assert hash_a != hash_b
