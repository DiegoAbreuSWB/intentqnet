"""Fase J9: determines how many seeds this project's campaigns actually
need, from data - never an arbitrary round number (see
docs/seed_justification.md).

`run_variability_pilot` executes each of `P00`'s five representative
scenarios at a growing seed count (5, 10, 20, 30 by default) using the
same `run_scenario`/`IntentPlanner` path every other trial in this
project uses - never a shortcut. `compute_variability_metrics` then
summarizes one metric's spread at a given seed count, and
`compute_ranking_stability` checks whether the *relative order* of
several routing strategies (by mean delivered_pairs) stays the same as
the seed count grows - a campaign whose conclusion is "strategy X beats
strategy Y" needs that ranking to be stable, not just each strategy's
own mean to look plausible.

`demos.*` imports below are deferred (inside the functions that need
them), not at module level: `demos/__init__.py` imports `demos.scenarios`,
which imports `experiments.scenarios.Scenario` - triggering
`experiments/__init__.py`, which (transitively) imports this module.
A top-level `from ..demos... import ...` here would therefore try to
import from `demos.scenarios` while it is still mid-initialization
(the same circular-import shape already documented and fixed in
`demos/planning.py`).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from scipy import stats

from ..intent.models import EntanglementIntent, SuccessCondition
from ..network.topology import NetworkTopologySpec
from ..planning.routing import HighestFidelityRouting, LeastLossRouting, RoutingStrategy, ShortestHopCountRouting
from .runner import run_scenario

DEFAULT_SEED_COUNTS: tuple[int, ...] = (5, 10, 20, 30)


@dataclass(frozen=True)
class PilotScenario:
    name: str
    topology_spec: NetworkTopologySpec
    intent: EntanglementIntent
    routing_strategies: dict[str, RoutingStrategy] = field(default_factory=lambda: {"default": ShortestHopCountRouting()})


def build_pilot_scenarios() -> list[PilotScenario]:
    """The five representative configurations section 11.2 asks for."""
    from ..demos.intents import diamond_intent, simple_intent  # deferred: see module docstring
    from ..demos.topologies import diamond_spec, three_node_spec

    linear_favorable_spec = three_node_spec(attenuation_db_per_m=1e-6, stop_time_s=0.2)
    linear_favorable_intent = simple_intent(
        intent_id="p00-linear-favorable", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.15,
    )

    linear_intermediate_spec = three_node_spec(attenuation_db_per_m=0.01, stop_time_s=0.2)
    linear_intermediate_intent = simple_intent(
        intent_id="p00-linear-intermediate", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=20, start_time=0.01, duration=0.05,
        success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=20)],
    )

    diamond_divergence_spec = diamond_spec(stop_time_s=0.2)
    diamond_divergence_intent = diamond_intent(requested_pairs=10, min_fidelity=0.6)

    purification_spec = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
    purification_intent = simple_intent(
        intent_id="p00-purification", source="a", destination="b", min_fidelity=0.70,
        requested_pairs=10, min_delivered_pairs=10, start_time=0.01, duration=0.1,
    )

    near_violation_spec = three_node_spec(attenuation_db_per_m=0.01, stop_time_s=0.2)
    near_violation_intent = simple_intent(
        intent_id="p00-near-violation", source="a", destination="b", min_fidelity=0.6,
        requested_pairs=10, min_delivered_pairs=15, start_time=0.01, duration=0.03,
        success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=15)],
    )

    return [
        PilotScenario("linear_favoravel", linear_favorable_spec, linear_favorable_intent),
        PilotScenario("linear_intermediario", linear_intermediate_spec, linear_intermediate_intent),
        PilotScenario(
            "diamante_divergencia", diamond_divergence_spec, diamond_divergence_intent,
            routing_strategies={
                "shortest_hop_count": ShortestHopCountRouting(),
                "least_loss": LeastLossRouting(),
                "highest_fidelity": HighestFidelityRouting(),
            },
        ),
        PilotScenario("com_purificacao", purification_spec, purification_intent),
        PilotScenario("proximo_violacao", near_violation_spec, near_violation_intent),
    ]


def run_pilot_trials(scenario: PilotScenario, strategy_name: str, seeds: list[int]) -> list[dict]:
    """Runs `scenario` under `scenario.routing_strategies[strategy_name]`
    for every seed in `seeds`, returning one dict per seed with
    `delivered_pairs`/`average_fidelity`/`satisfied` (`None` where no
    delivery evidence exists, never coerced to 0)."""
    from ..demos.scenarios import ad_hoc_scenario  # deferred: see module docstring

    strategy = scenario.routing_strategies[strategy_name]
    rows = []
    for seed in seeds:
        ad_hoc = ad_hoc_scenario(scenario.topology_spec, [scenario.intent], seed=seed, name=f"{scenario.name}-{strategy_name}-{seed}")
        result = run_scenario(ad_hoc, seed=seed, routing_strategy=strategy)
        trial = result.get(scenario.intent.id)
        delivered = None
        avg_fidelity = None
        if trial.evaluation is not None:
            for condition in trial.evaluation.condition_results:
                if condition.metric == "delivered_pairs":
                    delivered = condition.observed
                elif condition.metric == "average_fidelity":
                    avg_fidelity = condition.observed
        rows.append({
            "scenario": scenario.name, "strategy": strategy_name, "seed": seed,
            "final_status": trial.final_status.value,
            "satisfied": trial.satisfied,
            "delivered_pairs": delivered, "average_fidelity": avg_fidelity,
        })
    return rows


def compute_variability_metrics(values: list[float]) -> dict:
    """`mean`/`std`/`median`/`coefficient_of_variation`/`ci95_width`/
    `relative_ci95_width` over `values` - `None` (never `0`) wherever a
    statistic isn't defined for `n < 2`, and `coefficient_of_variation`/
    `relative_ci95_width` are `None` when the mean is exactly `0`
    (division would be meaningless, not just risky)."""
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "median": None, "coefficient_of_variation": None, "ci95_width": None, "relative_ci95_width": None}

    mean = statistics.mean(values)
    median = statistics.median(values)
    if n < 2:
        return {"n": n, "mean": mean, "std": None, "median": median, "coefficient_of_variation": None, "ci95_width": None, "relative_ci95_width": None}

    std = statistics.stdev(values)
    coefficient_of_variation = (std / mean) if mean != 0 else None

    t_critical = stats.t.ppf(0.975, df=n - 1)
    margin = t_critical * std / (n ** 0.5)
    ci95_width = 2 * margin
    relative_ci95_width = (ci95_width / mean) if mean != 0 else None

    return {
        "n": n, "mean": mean, "std": std, "median": median,
        "coefficient_of_variation": coefficient_of_variation,
        "ci95_width": ci95_width, "relative_ci95_width": relative_ci95_width,
    }


def compute_satisfaction_rate(satisfied_flags: list[bool | None]) -> float | None:
    known = [flag for flag in satisfied_flags if flag is not None]
    if not known:
        return None
    return sum(1 for flag in known if flag) / len(known)


def compute_ranking_stability(rows: list[dict], *, strategies: list[str], seed_counts: list[int]) -> dict[int, list[str]]:
    """For each seed count in `seed_counts`, ranks `strategies` by mean
    `delivered_pairs` over the FIRST `n` seeds (in the order they were
    run) - returns `{n: [strategy_name, ...]}` best-first, so callers can
    check whether the ranking order changes as `n` grows."""
    rankings: dict[int, list[str]] = {}
    for n in seed_counts:
        means = {}
        for strategy_name in strategies:
            strategy_rows = [r for r in rows if r["strategy"] == strategy_name][:n]
            delivered = [r["delivered_pairs"] for r in strategy_rows if r["delivered_pairs"] is not None]
            means[strategy_name] = statistics.mean(delivered) if delivered else float("-inf")
        rankings[n] = sorted(strategies, key=lambda name: means[name], reverse=True)
    return rankings
