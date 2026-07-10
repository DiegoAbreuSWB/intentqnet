"""In-memory store correlating each `EntanglementIntent` with its
`IntentLifecycle` and (once terminal) `IntentResult`.

v1 is intentionally in-memory only: experiments (`experiments.runner`, Etapa F)
create a fresh `IntentRepository` per run so results stay reproducible per
seed, rather than accumulating state across unrelated campaigns.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..utils.logging import get_logger
from .lifecycle import IntentLifecycle
from .models import EntanglementIntent, IntentResult, IntentStatus

logger = get_logger(__name__)


@dataclass
class IntentRecord:
    intent: EntanglementIntent
    lifecycle: IntentLifecycle
    result: IntentResult | None = field(default=None)


class IntentRepository:
    def __init__(self) -> None:
        self._records: dict[str, IntentRecord] = {}

    def add(self, intent: EntanglementIntent, *, sim_time: float | None = None) -> IntentRecord:
        """Registers a new intent in status RECEIVED.

        Raises:
            ValueError: if an intent with the same id is already registered.
        """
        if intent.id in self._records:
            raise ValueError(f"intent '{intent.id}' is already registered")
        record = IntentRecord(intent=intent, lifecycle=IntentLifecycle(intent.id, sim_time=sim_time))
        self._records[intent.id] = record
        logger.info("intent registered", extra={"intent_id": intent.id})
        return record

    def get(self, intent_id: str) -> IntentRecord:
        try:
            return self._records[intent_id]
        except KeyError:
            raise KeyError(f"no intent registered with id '{intent_id}'") from None

    def list(self) -> list[IntentRecord]:
        return list(self._records.values())

    def transition(
        self, intent_id: str, to_status: IntentStatus, reason: str, *, sim_time: float | None = None
    ) -> IntentRecord:
        record = self.get(intent_id)
        record.lifecycle.transition(to_status, reason, sim_time=sim_time)
        logger.info(
            "intent transitioned to %s (%s)", to_status.value, reason, extra={"intent_id": intent_id}
        )
        if record.lifecycle.is_terminal:
            record.result = IntentResult(
                intent_id=intent_id,
                final_status=to_status,
                satisfied=(to_status == IntentStatus.COMPLETED),
                reason=reason,
                sim_time_completed=sim_time,
            )
        return record
