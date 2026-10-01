"""`planner_study_runner.execute_trial_with_policy`'s execution cache:
planners that choose the same route and purification mode for the same
case share ONE simulation, and every record is identical to what running
each planner on its own produces.
"""
from __future__ import annotations

import pytest

from ibqn.experiments import planner_study_runner
from ibqn.experiments.realistic_suite import run_planner_case_job

LEVELS = ["L1", "L2", "L2-R", "L2-RB"]
NOT_COMPARED = {"planning_time_s", "simulation_wall_time_s", "timestamp"}  # wall-clock fields


def _job(levels, *, min_fidelity=0.60, allow_purification=True):
    return dict(
        campaign="CACHE", topology="chain1", hardware="literature", planner_levels=levels, seed=3, regime="test",
        combo=dict(min_fidelity=min_fidelity, reserved_memory_slots=4, duration_s=0.05, min_delivered_pairs=3,
                   allow_purification=allow_purification),
        source="a", destination="b", project_commit=None, sequence_commit=None,
    )


def _comparable(row):
    return {k: v for k, v in row.items() if k not in NOT_COMPARED}


@pytest.fixture
def executions(monkeypatch):
    calls = []
    stock = planner_study_runner._execute_plan

    def counting(intent, topology_spec, plan, *, seed):
        calls.append((tuple(plan.route), plan.purification_mode))
        return stock(intent, topology_spec, plan, seed=seed)

    monkeypatch.setattr(planner_study_runner, "_execute_plan", counting)
    return calls


@pytest.mark.unit
def test_planners_choosing_the_same_plan_share_one_simulation_with_identical_records(executions):
    shared = run_planner_case_job(_job(LEVELS))
    simulations_shared = len(executions)

    separate = [run_planner_case_job(_job([level]))[0] for level in LEVELS]
    simulations_separate = len(executions) - simulations_shared

    assert [row["planner_level"] for row in shared] == LEVELS
    for shared_row, separate_row in zip(shared, separate):
        assert _comparable(shared_row) == _comparable(separate_row)

    admitted = [row for row in shared if row["final_status"] != "REJECTED"]
    assert len(admitted) >= 2                                   # the case really exercises sharing
    assert len({(row["route"], row["purification_mode"]) for row in admitted}) == simulations_shared
    assert simulations_separate == len(admitted) > simulations_shared
    assert all(row["delivered_pairs"] == admitted[0]["delivered_pairs"] for row in admitted)


@pytest.mark.unit
def test_the_cache_key_separates_executed_purification_modes(executions):
    """Same route, but one intent forbids purification: the executed modes
    differ ('never' vs 'until_target'), so nothing may be shared between a
    cache used for one and a cache used for the other - and within one case
    the key carries the mode that is actually executed."""
    run_planner_case_job(_job(["L1", "L2"], allow_purification=False))
    assert len(executions) == 1
    rows = run_planner_case_job(_job(["L1", "L2"], allow_purification=False))
    assert {row["purification_mode"] for row in rows} == {"never"}
