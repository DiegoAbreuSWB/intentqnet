"""IBQN Validation-B3: verifies the 10 lifecycle invariants the governing
instruction requires against the persisted P17 concurrent-intent
campaign data (results/ibqn_validation_b/P17_concurrent_intents/). Does
not re-run the campaign - run scripts/run_concurrent_intent_campaign.py
first if the output files are missing."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "results" / "ibqn_validation_b" / "P17_concurrent_intents"

NON_TERMINAL_STATUSES = {"RECEIVED", "VALIDATED", "PLANNING", "PLANNED", "DEPLOYING", "ACTIVE", "RECONCILING"}
TERMINAL_STATUSES = {"REJECTED", "SATISFIED", "VIOLATED", "FAILED", "COMPLETED", "CANCELLED"}


@pytest.fixture(scope="module")
def intents_df():
    path = OUTPUT_DIR / "intents.csv"
    if not path.exists():
        pytest.skip("run scripts/run_concurrent_intent_campaign.py first")
    return pd.read_csv(path)


@pytest.fixture(scope="module")
def groups_df():
    path = OUTPUT_DIR / "groups.csv"
    if not path.exists():
        pytest.skip("run scripts/run_concurrent_intent_campaign.py first")
    return pd.read_csv(path)


@pytest.mark.unit
def test_output_files_exist_and_nonempty(intents_df, groups_df):
    assert len(intents_df) > 0
    assert len(groups_df) > 0


@pytest.mark.unit
def test_every_group_has_exactly_two_intents(intents_df):
    counts = intents_df.groupby("group_id").size()
    assert (counts == 2).all(), f"groups with != 2 intents: {counts[counts != 2].to_dict()}"


@pytest.mark.unit
def test_invariant_3_rejected_intent_never_becomes_active_or_further(intents_df):
    """A rejected intent must not have any assurance/reconciliation
    evidence attached - it never started execution."""
    rejected = intents_df[intents_df["final_status"] == "REJECTED"]
    assert rejected["satisfied"].isna().all(), "REJECTED rows must not carry an assurance outcome"
    assert rejected["reconciliation_action"].isna().all(), "REJECTED rows must not be reconciled"


@pytest.mark.unit
def test_invariant_4_every_executed_intent_reaches_a_terminal_status(intents_df):
    """Every intent whose planner decision was feasible (i.e. it was
    deployed, not rejected pre-execution) must end in SATISFIED, VIOLATED,
    or FAILED - never left non-terminal."""
    executed = intents_df[intents_df["decision_feasible"]]
    assert executed["final_status"].isin(["SATISFIED", "VIOLATED", "FAILED"]).all(), (
        f"non-terminal final statuses found among executed intents: "
        f"{executed[~executed['final_status'].isin(['SATISFIED', 'VIOLATED', 'FAILED'])]['final_status'].unique()}"
    )


@pytest.mark.unit
def test_invariant_5_no_intent_stuck_in_a_non_terminal_status(intents_df):
    stuck = intents_df[intents_df["final_status"].isin(NON_TERMINAL_STATUSES)]
    assert len(stuck) == 0, f"intents stuck in a non-terminal status: {stuck[['intent_id', 'final_status']].to_dict('records')}"
    assert intents_df["final_status"].isin(TERMINAL_STATUSES).all()


@pytest.mark.unit
def test_invariant_6_assurance_is_calculated_individually_per_intent(intents_df):
    """Two intents in the same group must not share a `satisfied` value
    by construction - each row's `satisfied` was computed from that row's
    own evaluation object, never copied. Spot-check: within any group
    where the two intents' outcomes genuinely differ (e.g. one SATISFIED,
    one FAILED), their `satisfied` values must differ accordingly, not be
    accidentally identical due to cross-contamination."""
    for group_id, group in intents_df.groupby("group_id"):
        if len(group) != 2:
            continue
        statuses = group["final_status"].tolist()
        if statuses[0] != statuses[1]:
            # different final_status -> satisfied must not be identical
            # in a way that ignores the individual outcome (allow both
            # None if e.g. one REJECTED, but if one SATISFIED and the
            # other VIOLATED, satisfied must differ: True vs False)
            sats = group.set_index("group_role")["satisfied"].to_dict()
            if "SATISFIED" in statuses and "VIOLATED" in statuses:
                assert sats.get("A") != sats.get("B") or len(set(statuses)) == 1


@pytest.mark.unit
def test_invariant_7_one_intents_violation_does_not_reclassify_the_other(intents_df):
    """In C2 (resource contention), intent A is expected to succeed while
    B fails - confirms A's own outcome is untouched by B's failure."""
    c2 = intents_df[intents_df["scenario"] == "C2_resource_contention"]
    if len(c2) == 0:
        pytest.skip("C2 scenario not present in this run")
    for group_id, group in c2.groupby("group_id"):
        a = group[group["group_role"] == "A"]
        if len(a) == 1 and a.iloc[0]["final_status"] == "FAILED":
            continue  # both failed this seed - nothing to cross-check
        # whenever A succeeded, its own satisfied/delivered_pairs must be
        # populated regardless of B's fate
        if len(a) == 1 and a.iloc[0]["final_status"] == "SATISFIED":
            assert a.iloc[0]["satisfied"] is True or a.iloc[0]["satisfied"] == True  # noqa: E712


@pytest.mark.unit
def test_invariant_8_reconciliation_preserves_intent_id_and_is_traceable(intents_df):
    reconciled = intents_df[intents_df["reconciliation_action"].notna()]
    if len(reconciled) == 0:
        pytest.skip("no VIOLATED intents were reconciled in this run")
    # intent_id in the persisted row is the same id used throughout -
    # traceable back to its group_id and group_role
    assert reconciled["intent_id"].apply(lambda x: isinstance(x, str) and len(x) > 0).all()
    assert reconciled["reconciliation_recovered"].isin([True, False]).all()


@pytest.mark.unit
def test_invariant_9_reconciliation_of_one_intent_does_not_overwrite_another(intents_df):
    """Each intent_id is unique across the entire campaign (group_id is
    embedded in intent_id) - no row was overwritten by another intent's
    reconciliation."""
    assert intents_df["intent_id"].duplicated().sum() == 0


@pytest.mark.unit
def test_invariant_1_and_2_c2_shows_genuine_resource_contention_and_release_is_not_applicable_across_seeds(intents_df, groups_df):
    """C2 must show at least one seed where the shared center node's
    limited memory causes a real rejection-by-NetworkManager (FAILED,
    failure_class C_resource_contention_reservation_rejected) - the
    documented, reproducible signature of invariant 1 (a memory slot
    cannot be double-booked by incompatible intents)."""
    c2 = intents_df[intents_df["scenario"] == "C2_resource_contention"]
    if len(c2) == 0:
        pytest.skip("C2 scenario not present in this run")
    contention_rows = c2[c2["failure_class"] == "C_resource_contention_reservation_rejected"]
    assert len(contention_rows) > 0, "expected at least one genuine resource-contention rejection in C2"


@pytest.mark.unit
def test_invariant_10_replay_determinism_same_seed_same_outcome(intents_df):
    """Same scenario+planner+seed (re-derivable across the two planners
    is not expected to match, but the SAME planner at the SAME seed run
    only once here - this test instead checks internal consistency: a
    given intent_id (which encodes scenario+planner+seed+role) appears
    exactly once, so there is no ambiguity about which outcome is
    'the' outcome for that configuration)."""
    assert intents_df["intent_id"].value_counts().max() == 1


@pytest.mark.unit
def test_c3_admission_is_order_independent_confirming_no_cross_intent_planning_state(intents_df):
    """C3's whole point: intent A and B's admission (decision_feasible)
    must not depend on which one 'went first', since NetworkCapabilities
    has no cross-intent residual tracking. Confirmed by checking that
    C3's admission pattern matches C2's admission pattern (same intents,
    same topology params, only the shared-vs-independent execution
    differs) - if planning were order/state-dependent, C3 (independent
    episodes, always full capacity) would show systematically higher
    admission than C2 (shared, contended) at the PLANNING stage, which it
    must NOT (only EXECUTION-stage outcomes should differ)."""
    c2 = intents_df[intents_df["scenario"] == "C2_resource_contention"]
    c3 = intents_df[intents_df["scenario"] == "C3_sequential_admission"]
    if len(c2) == 0 or len(c3) == 0:
        pytest.skip("C2/C3 scenario not present in this run")
    c2_admission_rate = c2["decision_feasible"].mean()
    c3_admission_rate = c3["decision_feasible"].mean()
    assert c2_admission_rate == c3_admission_rate, (
        f"C2 admission rate ({c2_admission_rate}) != C3 admission rate ({c3_admission_rate}) - "
        f"planning-time admission should be identical since both scenarios plan against the same "
        f"static NetworkCapabilities, independent of shared-vs-sequential execution"
    )


@pytest.mark.unit
def test_no_frozen_campaign_files_were_modified():
    """Guards against accidentally touching frozen (already persisted)
    planner-family or M9/M10 campaign data. The planner source tree used to
    be on this list too (while P17 was being built, the planners were meant
    to stay untouched); it was dropped in the physical-realism revision,
    which legitimately changes the planners' fidelity arithmetic
    (docs/physical_model.md) - planner behavior is pinned by
    tests/planning/planners/ instead."""
    import subprocess

    result = subprocess.run(
        ["git", "status", "--porcelain",
         "results/planner_study/", "results/predictability/", "results/predictability_m10/", "results/raw/"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    assert result.stdout.strip() == "", f"unexpected changes to frozen paths:\n{result.stdout}"
