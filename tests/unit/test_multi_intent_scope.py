"""Tests backing the Fase J8 scope decision (docs/multi_intent_scope.md,
Option A - one active intent per endpoint): confirms `IntentPolicy.
priority` genuinely has no effect on planning or execution, so the
project never implies real priority support just because the field
exists in the schema (section 10.4 of the original prompt).

Node-conflict detection itself (the actual Option A boundary) is already
covered by `tests/integration/test_assurance_pipeline.py::
test_conflicting_node_usage_raises_instead_of_misrouting_callbacks`
(same-source/same-destination AND the "crossed" case) and disjoint-node
multi-intent isolation by `test_multi_intent_metric_isolation_end_to_end`
in the same file - not duplicated here.
"""
from __future__ import annotations

import pytest

from ibqn.demos.intents import simple_intent
from ibqn.demos.scenarios import ad_hoc_scenario
from ibqn.demos.topologies import three_node_spec
from ibqn.experiments.runner import run_scenario
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.planning.planner import IntentPlanner


def _intent_with_priority(priority: str):
    intent = simple_intent(intent_id=f"prio-{priority}", source="a", destination="b", min_fidelity=0.6, requested_pairs=10)
    return intent.model_copy(update={"policy": intent.policy.model_copy(update={"priority": priority})})


@pytest.mark.unit
def test_priority_does_not_affect_the_planner_decision():
    spec = three_node_spec()
    capabilities = NetworkCapabilities(spec)
    planner = IntentPlanner(capabilities)

    plans = {priority: planner.plan(_intent_with_priority(priority)) for priority in ("low", "normal", "high")}

    routes = {priority: plan.route for priority, plan in plans.items()}
    fidelities = {priority: plan.estimated_metrics.fidelity for priority, plan in plans.items()}
    assert len(set(map(tuple, routes.values()))) == 1, "priority must never change the planned route"
    assert len(set(fidelities.values())) == 1, "priority must never change the estimated fidelity"


@pytest.mark.unit
def test_priority_does_not_affect_real_simulated_outcome():
    spec = three_node_spec()
    outcomes = {}
    for priority in ("low", "normal", "high"):
        intent = _intent_with_priority(priority)
        scenario = ad_hoc_scenario(spec, [intent], seed=0, name=f"prio-{priority}-scenario")
        result = run_scenario(scenario, seed=0)
        trial = result.get(intent.id)
        outcomes[priority] = (trial.final_status.value, trial.evaluation.condition_results[0].observed)

    assert len({status for status, _ in outcomes.values()}) == 1, "priority must never change the final status"
    assert len({observed for _, observed in outcomes.values()}) == 1, "priority must never change delivered_pairs"


@pytest.mark.unit
def test_priority_field_is_declared_but_intentionally_unused_by_planning_or_execution():
    """Documents, via a direct source check, that intent.policy.priority
    is read only for display (demos.tables.intent_table) - never by
    planning.planner, execution.sequence_executor, or
    assurance.reconciliation - matching docs/multi_intent_scope.md."""
    import ast
    import inspect

    from ibqn.planning import planner as planner_module
    from ibqn.execution import sequence_executor as executor_module
    from ibqn.assurance import reconciliation as reconciliation_module

    for module in (planner_module, executor_module, reconciliation_module):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        priority_reads = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "priority"
        ]
        assert not priority_reads, f"{module.__name__} must not read .priority - see docs/multi_intent_scope.md"
