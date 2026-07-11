import pytest

from ibqn.experiments.seeds import STRIDE, seeds_for_trials


@pytest.mark.unit
def test_seeds_for_trials_are_stride_apart():
    seeds = seeds_for_trials(base_seed=5, n_trials=4)
    assert seeds == [5, 5 + STRIDE, 5 + 2 * STRIDE, 5 + 3 * STRIDE]


@pytest.mark.unit
def test_seeds_for_trials_rejects_non_positive_count():
    with pytest.raises(ValueError, match="n_trials must be positive"):
        seeds_for_trials(base_seed=0, n_trials=0)
