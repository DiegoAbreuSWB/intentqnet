"""Routing-strategy comparison helpers for notebooks 12 and 16.

Two comparisons, deliberately kept separate:
- `compare_routing_strategies`: pre-simulation estimates only (every
  candidate route each strategy considers, via `planning.feasibility.
  evaluate_route` - the exact function `IntentPlanner` itself calls).
- `compare_routing_strategies_across_seeds`: real simulation outcomes,
  routed through `ad_hoc_scenario`/`experiments.runner.run_scenario` so
  `sequence.utils.metrics` is reset before every trial (see
  `demos.scenarios` for why that matters).
"""
from __future__ import annotations

import time

import pandas as pd

from ..experiments.runner import run_scenario
from ..intent.models import EntanglementIntent
from ..network.capabilities import NetworkCapabilities
from ..network.topology import NetworkTopologySpec
from ..planning.feasibility import evaluate_route
from ..planning.planner import IntentPlanner
from ..planning.routing import RoutingStrategy
from .scenarios import ad_hoc_scenario


def compare_routing_strategies(
    capabilities: NetworkCapabilities,
    intent: EntanglementIntent,
    strategies: dict[str, RoutingStrategy],
) -> pd.DataFrame:
    """Every candidate route each strategy considers (not just its winner),
    with the same fidelity/loss/purification/feasibility estimate
    `IntentPlanner.plan` itself would compute for that route. Columns:
    strategy, rank, route, hops, estimated_loss_db, estimated_fidelity,
    purification_required, feasible."""
    rows = []
    for strategy_name, strategy in strategies.items():
        candidates = strategy.find_candidate_paths(capabilities, intent.endpoints.source, intent.endpoints.destination)
        for rank, route in enumerate(candidates):
            result = evaluate_route(capabilities, route, intent)
            loss_db = sum(
                capabilities.link(route[i], route[i + 1]).loss_db for i in range(len(route) - 1)
            )
            estimated_fidelity = result.purified_fidelity_estimate if result.requires_purification else result.swap_only_fidelity
            rows.append(
                {
                    "strategy": strategy_name,
                    "rank": rank,
                    "route": " -> ".join(route),
                    "hops": len(route) - 1,
                    "estimated_loss_db": round(loss_db, 4),
                    "estimated_fidelity": round(estimated_fidelity, 4),
                    "purification_required": result.requires_purification,
                    "feasible": result.feasible,
                }
            )
    return pd.DataFrame(rows)


def compare_routing_strategies_across_seeds(
    topology_spec: NetworkTopologySpec,
    intent: EntanglementIntent,
    strategies: dict[str, RoutingStrategy],
    seeds: list[int],
) -> pd.DataFrame:
    """Runs `intent` once per (strategy, seed) pair via `ad_hoc_scenario` +
    `run_scenario` (resets `sequence.utils.metrics` before every trial) and
    reports both the planner's estimate and what was actually observed.
    Columns: strategy, seed, route, hops, estimated_fidelity,
    observed_delivered_pairs, observed_average_fidelity,
    observed_throughput_pairs_per_s, final_status, planning_time_s."""
    capabilities = NetworkCapabilities(topology_spec)
    rows = []
    for strategy_name, strategy in strategies.items():
        for seed in seeds:
            start = time.perf_counter()
            plan = IntentPlanner(capabilities, routing_strategy=strategy).plan(intent)
            planning_time_s = time.perf_counter() - start

            scenario = ad_hoc_scenario(topology_spec, [intent], seed=seed, name=f"{strategy_name}-seed{seed}")
            result = run_scenario(scenario, seed=seed, routing_strategy=strategy)
            trial = result.get(intent.id)

            delivered = None
            avg_fidelity = None
            if trial.evaluation is not None:
                for condition in trial.evaluation.condition_results:
                    if condition.metric == "delivered_pairs":
                        delivered = condition.observed
                    elif condition.metric == "average_fidelity":
                        avg_fidelity = condition.observed

            throughput = delivered / intent.requirements.duration if delivered is not None else None

            rows.append(
                {
                    "strategy": strategy_name,
                    "seed": seed,
                    "route": " -> ".join(plan.route) if plan.route else "(none)",
                    "hops": max(len(plan.route) - 1, 0),
                    "estimated_fidelity": round(plan.estimated_metrics.fidelity, 4) if plan.estimated_metrics else None,
                    "observed_delivered_pairs": delivered,
                    "observed_average_fidelity": round(avg_fidelity, 4) if avg_fidelity is not None else None,
                    "observed_throughput_pairs_per_s": round(throughput, 2) if throughput is not None else None,
                    "final_status": trial.final_status.value,
                    "planning_time_s": round(planning_time_s, 6),
                }
            )
    return pd.DataFrame(rows)
