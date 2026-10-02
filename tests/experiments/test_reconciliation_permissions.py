"""The intent's policy bounds what reconciliation may do (IntentPolicy):
the trial runner's only lever is a route change, so it reconciles only an
intent that allows rerouting."""
from __future__ import annotations

import pytest

from ibqn.demos.intents import diamond_intent
from ibqn.demos.topologies import diamond_spec
from ibqn.experiments.records import TrialIdentity
from ibqn.experiments.runner import execute_trial
from ibqn.experiments.sweeps import TrialParameters


@pytest.mark.unit
def test_trial_runner_reconciles_only_an_intent_that_allows_rerouting():
    spec = diamond_spec()
    allows = diamond_intent(requested_pairs=10, min_fidelity=0.6)
    forbids = allows.model_copy(update={"policy": allows.policy.model_copy(update={"allow_rerouting": False})})
    records = {}
    for name, intent in (("allows", allows), ("forbids", forbids)):
        identity = TrialIdentity(campaign="test", scenario="diamond", parameter_hash=name, strategy="shortest_hop_count",
                                 seed=0, intent_id=intent.id)
        params = TrialParameters(topology_spec=spec, intent=intent, routing_strategy_name="shortest_hop_count",
                                 purification_policy_name="automatic", reconciliation_enabled=True)
        records[name] = execute_trial(identity, params, project_commit=None, sequence_commit=None)

    # the fewest-hops route violates the delivery goal; the detour recovers it - when the intent allows the move
    assert records["allows"].recovered is True and records["allows"].final_status == "SATISFIED"
    assert records["allows"].route == "r1 -> good1 -> good2 -> r3"
    assert records["forbids"].recovered is None and records["forbids"].final_status == "VIOLATED"
    assert records["forbids"].route == "r1 -> bad -> r3"
