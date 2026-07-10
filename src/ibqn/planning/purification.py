"""Interchangeable purification strategies, consulted by
`planning.feasibility.evaluate_route` to decide whether a candidate route
that falls short of the intent's `min_fidelity` should be considered
feasible anyway (banking on purification).

There is no "configurable number of rounds" strategy: SeQUeNCe's
`Reservation.purification_mode` only supports `'until_target'`
(`sequence/network_management/reservation.py`) - an implicit, self-limiting
mechanism installed automatically by `ResourceManager.generate_load_rules`,
not a parameter the reservation API exposes. Forcing a specific round count
would require bypassing the reservation flow and installing `Rule`s by hand
(the same limitation documented for `planning.swapping`); this planner
version does not do that, and only estimates a single analytical round
(see docs/sequence_code_analysis.md, section 4.7 and section 4.4).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from sequence.entanglement_management.purification.bbpssw_circuit import BBPSSWCircuit


@dataclass(frozen=True)
class PurificationDecision:
    attempt: bool
    fidelity_estimate: float
    rounds_estimate: int
    note: str


class PurificationStrategy(ABC):
    @abstractmethod
    def decide(self, swap_only_fidelity: float, target_fidelity: float, allow_purification: bool) -> PurificationDecision:
        """`swap_only_fidelity`: single-swap estimate (see
        `feasibility.estimate_swap_only_fidelity`). `allow_purification`:
        `intent.policy.allow_purification`."""


class NeverPurify(PurificationStrategy):
    """Baseline strategy: never purifies, regardless of policy - useful for
    A/B comparison against `PurifyUntilTarget` (see the article experiments
    in the project brief, section 21 "Baselines")."""

    def decide(self, swap_only_fidelity, target_fidelity, allow_purification):
        return PurificationDecision(
            attempt=False, fidelity_estimate=swap_only_fidelity, rounds_estimate=0,
            note="never-purify baseline strategy",
        )


class PurifyUntilTarget(PurificationStrategy):
    """Mirrors what `SequenceExecutor` actually gets today by delegating to
    SeQUeNCe's default reservation mechanism (Etapa D, no custom `Rule`s
    installed): purify only if the single-swap estimate falls short of
    `target_fidelity` and the intent's policy allows it."""

    def decide(self, swap_only_fidelity, target_fidelity, allow_purification):
        if swap_only_fidelity >= target_fidelity:
            return PurificationDecision(
                attempt=False, fidelity_estimate=swap_only_fidelity, rounds_estimate=0,
                note="single swap already meets target_fidelity",
            )
        if not allow_purification:
            return PurificationDecision(
                attempt=False, fidelity_estimate=swap_only_fidelity, rounds_estimate=0,
                note="target_fidelity exceeds the single-swap estimate and allow_purification is False",
            )
        purified_fidelity = BBPSSWCircuit.improved_fidelity(swap_only_fidelity)
        return PurificationDecision(
            attempt=True, fidelity_estimate=purified_fidelity, rounds_estimate=1,
            note="one-round static estimate (BBPSSWCircuit.improved_fidelity); SeQUeNCe's 'until_target' "
                 "mode may run a different number of rounds at execution time",
        )
