"""Tests for the H2 "intent-based architecture" demo helpers: `demos.
intents`, `demos.scenarios`, `demos.planning`, `demos.reconciliation`,
`demos.visualization`, and the new H2-specific `demos.tables` functions.
"""
import matplotlib
import pandas as pd
import pytest
from sequence.utils import metrics

from ibqn.demos.intents import diamond_intent, simple_intent
from ibqn.demos.planning import (
    compare_purification_policies,
    compare_routing_strategies,
    compare_routing_strategies_across_seeds,
)
from ibqn.demos.reconciliation import run_two_episode_reconciliation
from ibqn.demos.scenarios import ad_hoc_scenario
from ibqn.demos.tables import intent_table, lifecycle_table, reconciliation_episodes_table
from ibqn.demos.topologies import diamond_spec, star_spec, three_node_spec
from ibqn.demos.visualization import draw_topology
from ibqn.experiments.runner import run_scenario
from ibqn.intent.models import IntentStatus
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.planning.purification import NeverPurify, PurifyUntilTarget
from ibqn.planning.routing import HighestFidelityRouting, LeastLossRouting, ShortestHopCountRouting

matplotlib.use("Agg")


@pytest.fixture(autouse=True)
def _reset_metrics():
    metrics.configure()
    metrics.reset_metrics()
    yield


@pytest.mark.unit
def test_diamond_spec_has_five_nodes_and_five_links():
    spec = diamond_spec()
    assert {n.id for n in spec.nodes} == {"r1", "r3", "bad", "good1", "good2"}
    assert len(spec.quantum_links) == 5


@pytest.mark.unit
def test_diamond_intent_targets_r1_to_r3():
    intent = diamond_intent(requested_pairs=7, min_fidelity=0.6)
    assert intent.endpoints.source == "r1"
    assert intent.endpoints.destination == "r3"
    assert intent.requirements.requested_pairs == 7
    assert intent.requirements.min_fidelity == 0.6


@pytest.mark.unit
def test_simple_intent_default_conditions_match_requirements():
    intent = simple_intent(intent_id="i1", source="a", destination="b", min_fidelity=0.7, requested_pairs=5)
    conditions = {c.metric: c for c in intent.validation.success_conditions}
    assert conditions["delivered_pairs"].expected == 5
    assert conditions["average_fidelity"].expected == 0.7


@pytest.mark.unit
def test_simple_intent_accepts_independent_success_conditions():
    """`requirements.min_fidelity` (used for planning) and
    `validation.success_conditions` (used for assurance) are independent -
    see notebook 13."""
    from ibqn.intent.models import SuccessCondition

    intent = simple_intent(
        intent_id="i2", source="a", destination="b", min_fidelity=0.5, requested_pairs=5,
        success_conditions=[SuccessCondition(metric="average_fidelity", operator=">=", expected=0.95)],
    )
    assert intent.requirements.min_fidelity == 0.5
    assert intent.validation.success_conditions[0].expected == 0.95


@pytest.mark.unit
def test_ad_hoc_scenario_runs_through_run_scenario():
    spec = three_node_spec(stop_time_s=0.1)
    intent = simple_intent(intent_id="demo", source="a", destination="b", min_fidelity=0.65, requested_pairs=10)
    scenario = ad_hoc_scenario(spec, [intent], seed=0)

    result = run_scenario(scenario, seed=0)
    trial = result.get("demo")

    assert trial.final_status == IntentStatus.SATISFIED
    assert trial.satisfied is True


@pytest.mark.unit
def test_compare_routing_strategies_estimates_diverge_on_diamond():
    spec = diamond_spec()
    intent = diamond_intent()
    capabilities = NetworkCapabilities(spec)

    df = compare_routing_strategies(
        capabilities, intent,
        {
            "ShortestHopCount": ShortestHopCountRouting(),
            "LeastLoss": LeastLossRouting(),
            "HighestFidelity": HighestFidelityRouting(),
        },
    )

    assert set(df.columns) == {
        "strategy", "rank", "route", "hops", "estimated_loss_db",
        "estimated_fidelity", "purification_required", "feasible",
    }
    winners = df[df["rank"] == 0].set_index("strategy")["route"]
    assert winners["ShortestHopCount"] == "r1 -> bad -> r3"
    assert winners["LeastLoss"] == "r1 -> good1 -> good2 -> r3"
    assert winners["HighestFidelity"] == "r1 -> bad -> r3"


@pytest.mark.unit
def test_compare_routing_strategies_across_seeds_reports_observed_and_estimated():
    spec = diamond_spec()
    intent = diamond_intent()

    df = compare_routing_strategies_across_seeds(
        spec, intent,
        {"ShortestHopCount": ShortestHopCountRouting(), "LeastLoss": LeastLossRouting()},
        seeds=[0],
    )

    assert len(df) == 2
    assert {"observed_delivered_pairs", "observed_average_fidelity", "planning_time_s"} <= set(df.columns)
    shortest_row = df[df["strategy"] == "ShortestHopCount"].iloc[0]
    least_loss_row = df[df["strategy"] == "LeastLoss"].iloc[0]
    assert shortest_row["route"] == "r1 -> bad -> r3"
    assert least_loss_row["route"] == "r1 -> good1 -> good2 -> r3"


@pytest.mark.unit
def test_run_two_episode_reconciliation_reproduces_violated_then_satisfied():
    spec = diamond_spec()
    intent = diamond_intent()

    demo = run_two_episode_reconciliation(
        spec, intent, first_seed=0, second_seed=1,
        first_routing_strategy=ShortestHopCountRouting(), second_routing_strategy=LeastLossRouting(),
    )

    assert len(demo.episodes) == 2
    assert demo.episodes[0].final_status == IntentStatus.VIOLATED
    assert demo.episodes[0].route == ["r1", "bad", "r3"]
    assert demo.episodes[1].final_status == IntentStatus.SATISFIED
    assert demo.episodes[1].route == ["r1", "good1", "good2", "r3"]
    assert len(demo.trigger_violations) >= 1
    assert demo.repository.get(intent.id).lifecycle.status == IntentStatus.SATISFIED


@pytest.mark.unit
def test_run_two_episode_reconciliation_stops_after_one_episode_when_satisfied():
    spec = three_node_spec(stop_time_s=0.1)
    intent = simple_intent(intent_id="demo", source="a", destination="b", min_fidelity=0.65, requested_pairs=10)

    demo = run_two_episode_reconciliation(spec, intent, first_seed=0, second_seed=1)

    assert len(demo.episodes) == 1
    assert demo.episodes[0].final_status == IntentStatus.SATISFIED
    assert demo.trigger_violations == []


@pytest.mark.unit
def test_draw_topology_draws_every_declared_node():
    spec = diamond_spec()
    ax = draw_topology(spec, highlight_route=["r1", "bad", "r3"], title="diamond")
    assert ax.get_title() == "diamond"
    matplotlib.pyplot.close(ax.figure)


@pytest.mark.unit
def test_intent_table_has_one_row_per_declared_field():
    intent = diamond_intent()
    df = intent_table(intent)
    assert "field" in df.columns and "value" in df.columns
    assert (df["field"] == "id").sum() == 1
    assert df.loc[df["field"] == "id", "value"].iloc[0] == intent.id


@pytest.mark.unit
def test_lifecycle_table_has_one_row_per_transition():
    spec = three_node_spec(stop_time_s=0.1)
    intent = simple_intent(intent_id="demo", source="a", destination="b", min_fidelity=0.65, requested_pairs=10)
    scenario = ad_hoc_scenario(spec, [intent], seed=0)
    result = run_scenario(scenario, seed=0)

    demo = run_two_episode_reconciliation(spec, simple_intent(intent_id="demo2", source="a", destination="b", min_fidelity=0.65, requested_pairs=10), first_seed=0, second_seed=1)
    df = lifecycle_table(demo.repository.get("demo2").lifecycle)

    assert list(df.columns) == ["from_status", "to_status", "reason", "sim_time_s"]
    assert len(df) == len(demo.repository.get("demo2").lifecycle.history)
    assert result.get("demo").final_status == IntentStatus.SATISFIED  # sanity check, unrelated repository


@pytest.mark.unit
def test_reconciliation_episodes_table_has_expected_columns():
    spec = diamond_spec()
    intent = diamond_intent()
    demo = run_two_episode_reconciliation(
        spec, intent, first_seed=0, second_seed=1,
        first_routing_strategy=ShortestHopCountRouting(), second_routing_strategy=LeastLossRouting(),
    )
    df = reconciliation_episodes_table(demo)

    assert list(df.columns) == ["episode", "strategy", "route", "delivered_pairs", "average_fidelity", "status"]
    assert len(df) == 2
    assert df.iloc[0]["status"] == "VIOLATED"
    assert df.iloc[1]["status"] == "SATISFIED"


@pytest.mark.unit
def test_compare_purification_policies_distinguishes_feasible_from_rejected():
    spec = three_node_spec()

    def make_intent(target):
        return simple_intent(intent_id=f"purif-{target}", source="a", destination="b", min_fidelity=target, requested_pairs=10, duration=0.1)

    df = compare_purification_policies(
        spec, make_intent,
        {"NeverPurify": NeverPurify(), "PurifyUntilTarget": PurifyUntilTarget()},
        fidelity_targets=[0.65, 0.70],
        seed=0,
    )

    assert set(df.columns) == {
        "min_fidelity", "policy", "requires_purification", "estimated_fidelity",
        "feasible", "final_status", "observed_delivered_pairs", "observed_average_fidelity",
    }
    row = df[(df["min_fidelity"] == 0.65) & (df["policy"] == "NeverPurify")].iloc[0]
    assert bool(row["feasible"]) is True
    assert bool(row["requires_purification"]) is False

    row_never = df[(df["min_fidelity"] == 0.70) & (df["policy"] == "NeverPurify")].iloc[0]
    assert bool(row_never["feasible"]) is False
    assert row_never["final_status"] == "REJECTED"

    row_purify = df[(df["min_fidelity"] == 0.70) & (df["policy"] == "PurifyUntilTarget")].iloc[0]
    assert bool(row_purify["feasible"]) is True
    assert bool(row_purify["requires_purification"]) is True
    assert row_purify["final_status"] == "SATISFIED"


@pytest.mark.unit
def test_star_spec_has_one_center_and_n_leaves():
    spec = star_spec(n_leaves=4)
    assert {n.id for n in spec.nodes} == {"center", "leaf1", "leaf2", "leaf3", "leaf4"}
    assert len(spec.quantum_links) == 4
    assert all(link.source == "center" for link in spec.quantum_links)
