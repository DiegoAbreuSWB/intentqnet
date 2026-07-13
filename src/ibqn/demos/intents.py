"""Reusable `EntanglementIntent` builders for the H2 "intent-based
architecture" notebooks (`notebooks/10`-`19`), so each notebook declares
its scenario-specific parameters (fidelity, pair count, timing) without
repeating the full nested-model construction.
"""
from __future__ import annotations

from ..intent.models import (
    EntanglementIntent,
    IntentEndpoints,
    IntentPolicy,
    IntentRequirements,
    IntentValidation,
    SuccessCondition,
)


def simple_intent(
    *,
    intent_id: str,
    source: str,
    destination: str,
    min_fidelity: float,
    requested_pairs: int = 10,
    start_time: float = 0.02,
    duration: float = 0.1,
    min_throughput: float = 1.0,
    max_latency: float = 1.0,
    min_delivered_pairs: int | None = None,
    allow_purification: bool = True,
    success_conditions: list[SuccessCondition] | None = None,
) -> EntanglementIntent:
    """One-hop-to-many-hop entanglement intent with a single `delivered_pairs`
    + `average_fidelity` success condition pair by default. Pass
    `success_conditions` explicitly to declare a *different* bar for success
    than `min_fidelity`/`requested_pairs` - the two are independent fields
    in the real model (see notebook 13).

    `requested_pairs` (this builder's own long-standing keyword, kept
    unchanged so every existing notebook keeps working) sizes the
    *memory pool* handed to SeQUeNCe - `IntentRequirements`'s
    `reserved_memory_slots` field, via the legacy-field migration in
    `intent.models.IntentRequirements`. Pass `min_delivered_pairs`
    explicitly to *also* declare a distinct, OPTIONAL service-level
    delivery goal (Fase J2, see docs/intent_resource_semantics.md) - it
    stays `None` (not silently equal to `requested_pairs`) unless given."""
    conditions = success_conditions if success_conditions is not None else [
        SuccessCondition(metric="delivered_pairs", operator=">=", expected=requested_pairs),
        SuccessCondition(metric="average_fidelity", operator=">=", expected=min_fidelity),
    ]
    declared_metrics = sorted({condition.metric for condition in conditions})
    return EntanglementIntent(
        id=intent_id,
        endpoints=IntentEndpoints(source=source, destination=destination),
        requirements=IntentRequirements(
            min_fidelity=min_fidelity, min_throughput=min_throughput, max_latency=max_latency,
            requested_pairs=requested_pairs, start_time=start_time, duration=duration,
            min_delivered_pairs=min_delivered_pairs,
        ),
        policy=IntentPolicy(allow_purification=allow_purification),
        validation=IntentValidation(metrics=declared_metrics, success_conditions=conditions),
    )


def diamond_intent(
    *,
    intent_id: str = "intent-diamond-demo",
    requested_pairs: int = 10,
    min_fidelity: float = 0.6,
    start_time: float = 0.02,
    duration: float = 0.1,
) -> EntanglementIntent:
    """The `r1 -> r3` intent used against `topologies.diamond_spec()`,
    mirroring `tests/integration/test_reconciliation.py`'s calibration (see
    that module's docstring for why these defaults make `bad` fast-but-
    insufficient and the `good1`/`good2` detour slow-but-sufficient)."""
    return simple_intent(
        intent_id=intent_id, source="r1", destination="r3", min_fidelity=min_fidelity,
        requested_pairs=requested_pairs, start_time=start_time, duration=duration,
        success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=requested_pairs)],
    )
