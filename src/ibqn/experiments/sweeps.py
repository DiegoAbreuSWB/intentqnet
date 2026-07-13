"""Parameter sweep registry and cartesian-product expansion for campaigns
(Fase H3, see docs/campaign_architecture.md).

A campaign never mutates the `NetworkTopologySpec`/`EntanglementIntent` a
scenario file declares - `apply_parameters` reconstructs immutable copies
in memory, one parameter combination at a time (both are frozen Pydantic
models, so every "mutation" here is actually `model_copy(update=...)`).
"""
from __future__ import annotations

import hashlib
import itertools
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from typing import Any

from ..intent.models import EntanglementIntent
from ..network.topology import NetworkTopologySpec
from ..planning.fidelity_estimation import FIDELITY_ESTIMATORS, resolve_fidelity_estimator
from ..planning.purification import NeverPurify, PurificationStrategy, PurifyUntilTarget
from ..planning.routing import HighestFidelityRouting, LeastLossRouting, RoutingStrategy, ShortestHopCountRouting


@dataclass(frozen=True)
class TrialParameters:
    """Everything a single trial needs beyond the campaign/seed/intent_id
    identity: a topology, an intent, and which named strategies to use -
    all rebuilt in memory from the campaign's base scenario, never read
    back from disk per trial."""

    topology_spec: NetworkTopologySpec
    intent: EntanglementIntent
    routing_strategy_name: str = "shortest_hop_count"
    purification_policy_name: str = "automatic"
    reconciliation_enabled: bool = False
    fidelity_estimator_name: str = "conservative_min"


class UnknownSweepParameterError(ValueError):
    """Raised when a campaign references a parameter name not in
    `SWEEP_PARAMETERS` - unknown parameters are rejected, never silently
    ignored (see the project brief's Fase H3, section 7)."""


class InvalidSweepValueError(ValueError):
    """Raised when a sweep value's type does not match the registered
    `SweepParameter.type` for its name."""


@dataclass(frozen=True)
class SweepParameter:
    name: str
    target: str
    type: type
    unit: str
    apply: Callable[[TrialParameters, Any], TrialParameters]


def _with_all_nodes(spec: NetworkTopologySpec, field_name: str, value: Any) -> NetworkTopologySpec:
    new_nodes = [node.model_copy(update={field_name: value}) for node in spec.nodes]
    return spec.model_copy(update={"nodes": new_nodes})


def _with_all_links(spec: NetworkTopologySpec, field_name: str, value: Any) -> NetworkTopologySpec:
    new_links = [link.model_copy(update={field_name: value}) for link in spec.quantum_links]
    return spec.model_copy(update={"quantum_links": new_links})


def _topology_node_field(field_name: str) -> Callable[[TrialParameters, Any], TrialParameters]:
    def apply(params: TrialParameters, value: Any) -> TrialParameters:
        return replace(params, topology_spec=_with_all_nodes(params.topology_spec, field_name, value))

    return apply


def _topology_link_field(field_name: str) -> Callable[[TrialParameters, Any], TrialParameters]:
    def apply(params: TrialParameters, value: Any) -> TrialParameters:
        return replace(params, topology_spec=_with_all_links(params.topology_spec, field_name, value))

    return apply


def _intent_requirement_field(field_name: str) -> Callable[[TrialParameters, Any], TrialParameters]:
    def apply(params: TrialParameters, value: Any) -> TrialParameters:
        new_requirements = params.intent.requirements.model_copy(update={field_name: value})
        new_intent = params.intent.model_copy(update={"requirements": new_requirements})
        return replace(params, intent=new_intent)

    return apply


def _apply_routing_strategy(params: TrialParameters, value: Any) -> TrialParameters:
    resolve_routing_strategy(value)  # raises UnknownStrategyError early if invalid
    return replace(params, routing_strategy_name=value)


def _apply_purification_policy(params: TrialParameters, value: Any) -> TrialParameters:
    resolve_purification_policy(value)  # raises UnknownStrategyError early if invalid
    return replace(params, purification_policy_name=value)


def _apply_reconciliation_enabled(params: TrialParameters, value: Any) -> TrialParameters:
    return replace(params, reconciliation_enabled=bool(value))


def _apply_fidelity_estimator(params: TrialParameters, value: Any) -> TrialParameters:
    resolve_fidelity_estimator(value)  # raises UnknownFidelityEstimatorError early if invalid
    return replace(params, fidelity_estimator_name=value)


SWEEP_PARAMETERS: dict[str, SweepParameter] = {
    "min_fidelity": SweepParameter(
        "min_fidelity", "intent.requirements.min_fidelity", float, "dimensionless",
        _intent_requirement_field("min_fidelity"),
    ),
    "reserved_memory_slots": SweepParameter(
        "reserved_memory_slots", "intent.requirements.reserved_memory_slots", int, "memory slots",
        _intent_requirement_field("reserved_memory_slots"),
    ),
    "min_delivered_pairs": SweepParameter(
        "min_delivered_pairs", "intent.requirements.min_delivered_pairs", int, "pairs",
        _intent_requirement_field("min_delivered_pairs"),
    ),
    "duration_s": SweepParameter(
        "duration_s", "intent.requirements.duration_s", float, "s",
        _intent_requirement_field("duration_s"),
    ),
    "memory_size": SweepParameter(
        "memory_size", "topology.nodes[*].memories", int, "memories",
        _topology_node_field("memories"),
    ),
    "attenuation_db_per_m": SweepParameter(
        "attenuation_db_per_m", "topology.quantum_links[*].attenuation_db_per_m", float, "dB/m",
        _topology_link_field("attenuation_db_per_m"),
    ),
    "distance_m": SweepParameter(
        "distance_m", "topology.quantum_links[*].distance_m", float, "m",
        _topology_link_field("distance_m"),
    ),
    "coherence_time_s": SweepParameter(
        "coherence_time_s", "topology.nodes[*].coherence_time_s", float, "s",
        _topology_node_field("coherence_time_s"),
    ),
    "raw_fidelity": SweepParameter(
        "raw_fidelity", "topology.nodes[*].raw_fidelity", float, "dimensionless",
        _topology_node_field("raw_fidelity"),
    ),
    "routing_strategy": SweepParameter(
        "routing_strategy", "strategy.routing", str, "n/a", _apply_routing_strategy,
    ),
    "purification_policy": SweepParameter(
        "purification_policy", "strategy.purification", str, "n/a", _apply_purification_policy,
    ),
    "reconciliation_enabled": SweepParameter(
        "reconciliation_enabled", "strategy.reconciliation_enabled", bool, "n/a", _apply_reconciliation_enabled,
    ),
    "fidelity_estimator": SweepParameter(
        "fidelity_estimator", "strategy.fidelity_estimator", str, "n/a", _apply_fidelity_estimator,
    ),
}


ROUTING_STRATEGIES: dict[str, type[RoutingStrategy]] = {
    "shortest_hop_count": ShortestHopCountRouting,
    "least_loss": LeastLossRouting,
    "highest_fidelity": HighestFidelityRouting,
}

PURIFICATION_POLICIES: dict[str, type[PurificationStrategy]] = {
    "disabled": NeverPurify,
    "automatic": PurifyUntilTarget,
}


class UnknownStrategyError(ValueError):
    """Raised when a campaign names a routing/purification strategy not in
    `ROUTING_STRATEGIES`/`PURIFICATION_POLICIES`."""


def resolve_routing_strategy(name: str) -> RoutingStrategy:
    try:
        return ROUTING_STRATEGIES[name]()
    except KeyError:
        raise UnknownStrategyError(
            f"unknown routing strategy '{name}' - supported: {sorted(ROUTING_STRATEGIES)}"
        ) from None


def resolve_purification_policy(name: str) -> PurificationStrategy:
    try:
        return PURIFICATION_POLICIES[name]()
    except KeyError:
        raise UnknownStrategyError(
            f"unknown purification policy '{name}' - supported: {sorted(PURIFICATION_POLICIES)}"
        ) from None


def ensure_known_parameters(names: Iterable[str]) -> None:
    unknown = sorted(set(names) - SWEEP_PARAMETERS.keys())
    if unknown:
        raise UnknownSweepParameterError(
            f"unsupported sweep parameter(s): {unknown} - supported: {sorted(SWEEP_PARAMETERS)}"
        )


def ensure_valid_values(parameter_grid: dict[str, list[Any]]) -> None:
    """Rejects values whose Python type doesn't match the parameter's
    registered `SweepParameter.type` (e.g. a string where a float is
    expected) - "unidades inválidas" in the project brief's terms."""
    for name, values in parameter_grid.items():
        expected_type = SWEEP_PARAMETERS[name].type
        for value in values:
            if expected_type is float:
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    raise InvalidSweepValueError(
                        f"parameter '{name}' expects {expected_type.__name__} ({SWEEP_PARAMETERS[name].unit}), "
                        f"got {value!r}"
                    )
            elif expected_type is bool:
                if not isinstance(value, bool):
                    raise InvalidSweepValueError(f"parameter '{name}' expects bool, got {value!r}")
            elif not isinstance(value, expected_type):
                raise InvalidSweepValueError(
                    f"parameter '{name}' expects {expected_type.__name__} ({SWEEP_PARAMETERS[name].unit}), "
                    f"got {value!r}"
                )


def expand_parameter_grid(parameter_grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Cartesian product of every parameter's value list. Deterministic
    order: parameter names sorted alphabetically (independent of the
    grid's declaration/dict-insertion order), values in their declared
    list order. Returns `[{}]` (one empty combination) for an empty grid -
    a campaign with no sweep still runs its baseline once per
    strategy/seed."""
    ensure_known_parameters(parameter_grid.keys())
    ensure_valid_values(parameter_grid)
    for name, values in parameter_grid.items():
        if not values:
            raise ValueError(f"parameter '{name}' has an empty value list - a sweep parameter needs at least one value")

    if not parameter_grid:
        return [{}]
    names = sorted(parameter_grid)
    value_lists = [parameter_grid[name] for name in names]
    return [dict(zip(names, combo)) for combo in itertools.product(*value_lists)]


def compute_parameter_hash(parameters: dict[str, Any]) -> str:
    """SHA-256 (truncated to 16 hex chars) of the parameter combination's
    canonical (sorted-keys) JSON serialization - stable across dict
    insertion order and across process runs, which is what makes
    `TrialIdentity.trial_id` deterministic (see docs/campaign_architecture.md)."""
    canonical = json.dumps(parameters, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def apply_parameters(
    topology_spec: NetworkTopologySpec,
    intent: EntanglementIntent,
    combination: dict[str, Any],
    *,
    routing_strategy_name: str = "shortest_hop_count",
    purification_policy_name: str = "automatic",
    reconciliation_enabled: bool = False,
    fidelity_estimator_name: str = "conservative_min",
) -> TrialParameters:
    """Applies one expanded parameter `combination` (as returned by
    `expand_parameter_grid`) to `topology_spec`/`intent`, returning a fresh
    `TrialParameters`. Base strategy selections are passed explicitly so a
    combination that doesn't sweep `routing_strategy`/`purification_policy`/
    `reconciliation_enabled`/`fidelity_estimator` still gets a well-defined
    value."""
    ensure_known_parameters(combination.keys())
    params = TrialParameters(
        topology_spec=topology_spec, intent=intent,
        routing_strategy_name=routing_strategy_name,
        purification_policy_name=purification_policy_name,
        reconciliation_enabled=reconciliation_enabled,
        fidelity_estimator_name=fidelity_estimator_name,
    )
    for name, value in combination.items():
        params = SWEEP_PARAMETERS[name].apply(params, value)
    return params
