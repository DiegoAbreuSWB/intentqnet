"""Tests that `execute_trial` isolates independent trials in the same
process (Fase H3.2, section 9): fresh topology/Timeline/planner/repository
per trial, `sequence.utils.metrics` reset first, no contamination between
back-to-back calls.
"""
import pytest
from sequence.utils import metrics

from ibqn.demos.intents import diamond_intent, simple_intent
from ibqn.demos.topologies import diamond_spec, three_node_spec
from ibqn.experiments.records import TrialIdentity
from ibqn.experiments.runner import execute_trial
from ibqn.experiments.sweeps import apply_parameters, compute_parameter_hash


def _identity(**overrides):
    fields = dict(campaign="iso-test", scenario="scn", parameter_hash="h", strategy="s", seed=0, intent_id="intent-001")
    fields.update(overrides)
    return TrialIdentity(**fields)


@pytest.mark.unit
def test_two_back_to_back_trials_do_not_contaminate_each_other():
    """Same topology/intent, two different routing strategies, run one
    right after the other in this same process - each trial's native
    counters and delivered_pairs must reflect only its own run."""
    spec = diamond_spec()
    intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    params_a = apply_parameters(spec, intent, {"routing_strategy": "shortest_hop_count"})
    params_b = apply_parameters(spec, intent, {"routing_strategy": "least_loss"})

    record_a = execute_trial(_identity(intent_id=intent.id, seed=0), params_a, project_commit=None, sequence_commit=None)
    record_b = execute_trial(_identity(intent_id=intent.id, seed=0), params_b, project_commit=None, sequence_commit=None)

    assert record_a.route == "r1 -> bad -> r3"
    assert record_b.route == "r1 -> good1 -> good2 -> r3"
    # the two routes have very different delivery counts on this topology (see notebook 12/16 of Fase H2) -
    # if metrics leaked between calls, record_b's counters would be inflated by record_a's
    assert record_b.delivered_pairs > record_a.delivered_pairs * 5
    assert record_a.eg_attempts is not None and record_b.eg_attempts is not None
    assert record_a.eg_attempts != record_b.eg_attempts


@pytest.mark.unit
def test_running_the_same_trial_twice_gives_identical_results():
    """Same identity, same parameters, same seed, run twice in the same
    process - must reproduce the same key results (a weaker, in-process
    version of the reproducibility requirement in section 35)."""
    spec = three_node_spec(stop_time_s=0.1)
    intent = simple_intent(intent_id="intent-001", source="a", destination="b", min_fidelity=0.65, requested_pairs=10, duration=0.05)
    params = apply_parameters(spec, intent, {})
    identity = _identity(intent_id="intent-001", seed=7)

    record_1 = execute_trial(identity, params, project_commit=None, sequence_commit=None)
    record_2 = execute_trial(identity, params, project_commit=None, sequence_commit=None)

    assert record_1.delivered_pairs == record_2.delivered_pairs
    assert record_1.route == record_2.route
    assert record_1.final_status == record_2.final_status
    assert record_1.average_fidelity == record_2.average_fidelity


@pytest.mark.unit
def test_execute_trial_resets_metrics_storage_for_the_next_caller():
    """`sequence.utils.metrics.storage` after a trial must reflect only
    that trial - not an accumulation of every trial run so far in a
    long-running campaign process. Verified by comparing "trial 2 run
    right after trial 1" against "trial 2 run alone from a fresh reset":
    if execute_trial isolates correctly, both must leave the same number
    of records in storage."""
    spec = three_node_spec(stop_time_s=0.1)
    intent = simple_intent(intent_id="intent-001", source="a", destination="b", min_fidelity=0.65, requested_pairs=10, duration=0.05)
    params = apply_parameters(spec, intent, {})

    execute_trial(_identity(intent_id="intent-001", seed=1), params, project_commit=None, sequence_commit=None)
    execute_trial(_identity(intent_id="intent-001", seed=2), params, project_commit=None, sequence_commit=None)
    count_after_two_back_to_back_calls = len(metrics.storage.get_all())

    metrics.configure()
    execute_trial(_identity(intent_id="intent-001", seed=2), params, project_commit=None, sequence_commit=None)
    count_running_the_same_trial_alone = len(metrics.storage.get_all())

    assert count_after_two_back_to_back_calls == count_running_the_same_trial_alone
    assert count_running_the_same_trial_alone > 0
