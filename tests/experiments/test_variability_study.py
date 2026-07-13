"""Tests for `ibqn.experiments.variability_study`'s pure statistics (Fase
J9) - see docs/seed_justification.md. The five pilot scenarios
themselves are exercised for real in the one-off pilot run that produced
docs/seed_justification.md's numbers, not re-run on every test suite
execution (210 real simulations); `build_pilot_scenarios`/
`run_pilot_trials` still get a light smoke test here.
"""
from __future__ import annotations

import pytest

from ibqn.experiments.variability_study import (
    build_pilot_scenarios,
    compute_ranking_stability,
    compute_satisfaction_rate,
    compute_variability_metrics,
    run_pilot_trials,
)


@pytest.mark.unit
def test_variability_metrics_on_empty_input_are_all_none():
    metrics = compute_variability_metrics([])
    assert metrics == {
        "n": 0, "mean": None, "std": None, "median": None,
        "coefficient_of_variation": None, "ci95_width": None, "relative_ci95_width": None,
    }


@pytest.mark.unit
def test_variability_metrics_with_a_single_value_has_no_spread():
    metrics = compute_variability_metrics([10.0])
    assert metrics["n"] == 1
    assert metrics["mean"] == 10.0
    assert metrics["median"] == 10.0
    assert metrics["std"] is None
    assert metrics["ci95_width"] is None
    assert metrics["coefficient_of_variation"] is None


@pytest.mark.unit
def test_variability_metrics_known_values():
    values = [10.0, 12.0, 8.0, 11.0, 9.0]
    metrics = compute_variability_metrics(values)
    assert metrics["n"] == 5
    assert metrics["mean"] == pytest.approx(10.0)
    assert metrics["median"] == pytest.approx(10.0)
    assert metrics["std"] > 0
    assert metrics["coefficient_of_variation"] == pytest.approx(metrics["std"] / metrics["mean"])
    assert metrics["ci95_width"] > 0
    assert metrics["relative_ci95_width"] == pytest.approx(metrics["ci95_width"] / metrics["mean"])


@pytest.mark.unit
def test_variability_metrics_zero_mean_never_divides_by_zero():
    metrics = compute_variability_metrics([-1.0, 1.0, -1.0, 1.0])
    assert metrics["mean"] == pytest.approx(0.0)
    assert metrics["coefficient_of_variation"] is None
    assert metrics["relative_ci95_width"] is None
    assert metrics["ci95_width"] is not None  # ci95_width itself doesn't depend on the mean


@pytest.mark.unit
def test_satisfaction_rate_ignores_none_and_never_divides_by_zero():
    assert compute_satisfaction_rate([True, True, False, None]) == pytest.approx(2 / 3)
    assert compute_satisfaction_rate([None, None]) is None
    assert compute_satisfaction_rate([]) is None


@pytest.mark.unit
def test_ranking_stability_detects_a_stable_ranking():
    rows = (
        [{"strategy": "a", "delivered_pairs": 100.0} for _ in range(30)]
        + [{"strategy": "b", "delivered_pairs": 10.0} for _ in range(30)]
    )
    stability = compute_ranking_stability(rows, strategies=["a", "b"], seed_counts=[5, 10, 20, 30])
    assert all(ranking == ["a", "b"] for ranking in stability.values())


@pytest.mark.unit
def test_ranking_stability_can_detect_a_flip():
    # 'a' starts ahead on the first 5 rows, but 'b' overtakes once more rows are included
    a_rows = [{"strategy": "a", "delivered_pairs": v} for v in [100, 100, 100, 100, 100, 1, 1, 1, 1, 1]]
    b_rows = [{"strategy": "b", "delivered_pairs": v} for v in [50, 50, 50, 50, 50, 200, 200, 200, 200, 200]]
    stability = compute_ranking_stability(a_rows + b_rows, strategies=["a", "b"], seed_counts=[5, 10])
    assert stability[5] == ["a", "b"]
    assert stability[10] == ["b", "a"]


@pytest.mark.unit
def test_build_pilot_scenarios_returns_the_five_required_configurations():
    scenarios = build_pilot_scenarios()
    names = {s.name for s in scenarios}
    assert names == {
        "linear_favoravel", "linear_intermediario", "diamante_divergencia", "com_purificacao", "proximo_violacao",
    }
    diamond = next(s for s in scenarios if s.name == "diamante_divergencia")
    assert set(diamond.routing_strategies) == {"shortest_hop_count", "least_loss", "highest_fidelity"}


@pytest.mark.unit
def test_run_pilot_trials_smoke_test():
    scenario = next(s for s in build_pilot_scenarios() if s.name == "linear_favoravel")
    rows = run_pilot_trials(scenario, "default", [0, 1])
    assert len(rows) == 2
    assert all(r["scenario"] == "linear_favoravel" for r in rows)
    assert all(r["delivered_pairs"] is not None for r in rows)
