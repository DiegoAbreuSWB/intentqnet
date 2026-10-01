"""Interchangeable purification strategies, consulted by
`planning.feasibility.evaluate_route` to decide whether a candidate route
that falls short of the intent's `min_fidelity` should be considered
feasible anyway (banking on purification) - AND, since the physical-realism
revision (docs/physical_model.md), what purification policy the network
actually executes for the resulting reservation.

Each strategy therefore has two faces:

- `decide(...)`: the planning-time ESTIMATE (how many rounds, what output
  fidelity), computed with the formalism-aware one-round model handed in
  as `physics` (`ibqn.physics.PurificationPhysics`; Dur-Briegel's ideal
  BBPSSW when omitted, exactly the pre-revision formula).
- `execution_mode`: the policy `execution.sequence_executor` installs on
  the real SeQUeNCe reservation (`Reservation.purification_mode`, read by
  `ep_rule_condition_*` when the resource manager builds its rules):
  `'until_target'` (SeQUeNCe's default: keep purifying any pair below the
  target, including already-purified ones), `'once'` (SeQUeNCe's other
  native mode: a pair is purified at most one time), or `'never'` (an IBQN
  value SeQUeNCe's conditions fall through on, so no purification rule
  ever fires).

Before this revision only the estimate existed - SeQUeNCe always executed
`'until_target'` regardless of the strategy, so `NeverPurify` was a
planning-only baseline. The estimate/execution split is deliberate:
`PurifyUntilTarget` keeps its historical ONE-round estimate against an
`until_target` execution (the L1 mismatch studied in
docs/false_rejection_root_cause.md), while `PurifyOnce` is the consistent
one-round policy at both planning and execution time.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

from ..physics import IDEAL_BBPSSW, PurificationPhysics

PurificationMode = Literal["never", "once", "until_target"]
PURIFICATION_MODES: tuple[str, ...] = ("never", "once", "until_target")


def executed_purification_mode(plan_mode: str, allow_purification: bool) -> str:
    """The purification policy a reservation actually runs: the plan's
    `purification_mode`, unless the intent forbids purification
    (`intent.policy.allow_purification` is False), in which case nothing is
    ever purified no matter which strategy planned the route.

    The planning side always honored the flag (`decide` refuses to bank on
    purification). The execution side has to honor it separately since
    fidelity became state-derived: a pair that met the target when it was
    planned can decohere below it at run time, and `'until_target'` would
    then purify it against the intent's policy."""
    return plan_mode if allow_purification else "never"


@dataclass(frozen=True)
class PurificationDecision:
    attempt: bool
    fidelity_estimate: float
    rounds_estimate: int
    note: str
    execution_mode: str = "until_target"
    """The `PurificationStrategy.execution_mode` of the strategy that made
    this decision - carried along so `ExecutionPlan.purification_mode` can
    be filled without the planner having to know the strategy."""
    success_probability_estimate: float | None = None
    """Estimated success probability of the (last) projected round, from
    `physics.improve` - `None` when no round was projected."""


class PurificationStrategy(ABC):
    execution_mode: str = "until_target"

    @abstractmethod
    def decide(
        self,
        swap_only_fidelity: float,
        target_fidelity: float,
        allow_purification: bool,
        *,
        physics: PurificationPhysics | None = None,
    ) -> PurificationDecision:
        """`swap_only_fidelity`: end-to-end estimate before purification (see
        `feasibility.estimate_swap_only_fidelity`). `allow_purification`:
        `intent.policy.allow_purification`. `physics`: the one-round BBPSSW
        model for the pair's two endpoint nodes
        (`NetworkCapabilities.physics.purification_between`); defaults to
        ideal-gate Dur-Briegel."""


class NeverPurify(PurificationStrategy):
    """Baseline strategy: never purifies, regardless of policy - useful for
    A/B comparison against `PurifyUntilTarget` (see the article experiments
    in the project brief, section 21 "Baselines"). Executes as `'never'`:
    no purification rule is ever installed, so a route whose swapped pairs
    fall short of the target delivers nothing (the swap rules themselves
    require both inputs to meet the reservation's target fidelity)."""

    execution_mode = "never"

    def decide(self, swap_only_fidelity, target_fidelity, allow_purification, *, physics=None):
        return PurificationDecision(
            attempt=False, fidelity_estimate=swap_only_fidelity, rounds_estimate=0,
            note="never-purify baseline strategy", execution_mode=self.execution_mode,
        )


def _one_round_decision(
    strategy: PurificationStrategy, swap_only_fidelity: float, target_fidelity: float, allow_purification: bool,
    physics: PurificationPhysics | None, *, note_suffix: str,
) -> PurificationDecision:
    if swap_only_fidelity >= target_fidelity:
        return PurificationDecision(
            attempt=False, fidelity_estimate=swap_only_fidelity, rounds_estimate=0,
            note="single swap already meets target_fidelity", execution_mode=strategy.execution_mode,
        )
    if not allow_purification:
        return PurificationDecision(
            attempt=False, fidelity_estimate=swap_only_fidelity, rounds_estimate=0,
            note="target_fidelity exceeds the single-swap estimate and allow_purification is False",
            execution_mode=strategy.execution_mode,
        )
    success_probability, purified_fidelity = (physics or IDEAL_BBPSSW).improve(swap_only_fidelity)
    return PurificationDecision(
        attempt=True, fidelity_estimate=purified_fidelity, rounds_estimate=1,
        note=f"one-round static estimate; {note_suffix}", execution_mode=strategy.execution_mode,
        success_probability_estimate=success_probability,
    )


class PurifyUntilTarget(PurificationStrategy):
    """This project's original strategy (L1's model): estimates a SINGLE
    analytical purification round, while the network executes SeQUeNCe's
    default `'until_target'` mode - which may run as many rounds as the
    target requires. That planning/execution mismatch is the "one-round
    ceiling" false-rejection phenomenon documented in
    docs/false_rejection_root_cause.md, preserved here on purpose."""

    execution_mode = "until_target"

    def decide(self, swap_only_fidelity, target_fidelity, allow_purification, *, physics=None):
        return _one_round_decision(
            self, swap_only_fidelity, target_fidelity, allow_purification, physics,
            note_suffix="SeQUeNCe's 'until_target' mode may run a different number of rounds at execution time",
        )


class PurifyOnce(PurificationStrategy):
    """Consistent one-round policy: estimates one round AND executes
    SeQUeNCe's native `'once'` mode, in which each pair is purified at most
    one time. Cheaper in raw pairs than `'until_target'`; a pair whose
    single round leaves it below the target is never delivered."""

    execution_mode = "once"

    def decide(self, swap_only_fidelity, target_fidelity, allow_purification, *, physics=None):
        return _one_round_decision(
            self, swap_only_fidelity, target_fidelity, allow_purification, physics,
            note_suffix="executed as SeQUeNCe's 'once' mode (each pair purified at most one time)",
        )
