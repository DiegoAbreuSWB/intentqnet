"""Collects per-intent evidence from `sequence.utils.metrics`, never from
values requested by the intent itself (see docs/assurance_design.md).

Only `EventTypes.DELIVERY` records carry an `intent_id` tag (added by
`execution.sequence_executor.IntentRequestApp`, not by SeQUeNCe's core -
see docs/assurance_design.md, sections 2-3): every other counter
(`eg`/`ep`/`es`) is keyed only by the node performing the action and cannot
be attributed to one intent when nodes are shared between intents. This
module therefore builds delivery evidence exclusively from intent-tagged
DELIVERY records, and exposes source-node counters separately, clearly
labeled as diagnostic (not a definition of "delivered").
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sequence.constants import SECOND
from sequence.utils import metrics
from sequence.utils.metrics.event_types import EventTypes

from ..intent.models import EntanglementIntent
from ..utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class DeliveredPair:
    """One end-to-end pair confirmed delivered for a specific intent.

    Sourced from a single `EventTypes.DELIVERY` record - never inferred from
    `entangle_time > 0` (see docs/assurance_design.md, section 6).
    """

    pair_number: int
    sim_time_s: float
    fidelity: float
    local_memory: str = ""
    remote_node: str = ""
    remote_memory: str = ""


@dataclass(frozen=True)
class IntentEvidence:
    """Everything the assurance evaluator is allowed to use to judge one
    intent. `source_node_metrics` is exclusive to this intent *only* because
    `SequenceExecutor` refuses to let two intents share a source/destination
    node (see docs/assurance_design.md, section 4) - it is diagnostic
    context, never itself proof of delivery."""

    intent_id: str
    delivered_pairs: list[DeliveredPair] = field(default_factory=list)
    source_node_metrics: dict = field(default_factory=dict)


def collect_intent_evidence(intent: EntanglementIntent, *, storage=None) -> IntentEvidence:
    """Builds `IntentEvidence` for `intent` from `sequence.utils.metrics`.

    Args:
        intent: the intent to collect evidence for.
        storage: metrics storage to read from (defaults to the global
            `sequence.utils.metrics.storage` singleton); overridable for tests.
    """
    record_source = storage if storage is not None else metrics.storage
    delivered: list[DeliveredPair] = []
    seen_pair_numbers: set[int] = set()

    for record in record_source.get_all():
        if record["event_type"] is not EventTypes.DELIVERY:
            continue
        if record.get("intent_id") != intent.id:
            continue
        pair_number = record["pair_number"]
        if pair_number in seen_pair_numbers:
            logger.warning(
                "duplicate DELIVERY pair_number=%d ignored", pair_number, extra={"intent_id": intent.id}
            )
            continue
        seen_pair_numbers.add(pair_number)
        delivered.append(
            DeliveredPair(
                pair_number=pair_number,
                sim_time_s=record["sim_time"] / SECOND,
                fidelity=record["fidelity"],
                local_memory=record.get("local_memory", ""),
                remote_node=record.get("remote_node", ""),
                remote_memory=record.get("remote_memory", ""),
            )
        )

    delivered.sort(key=lambda pair: pair.pair_number)

    source_node_metrics = metrics.collect_trial_metrics(intent.endpoints.source)

    return IntentEvidence(intent_id=intent.id, delivered_pairs=delivered, source_node_metrics=source_node_metrics)
