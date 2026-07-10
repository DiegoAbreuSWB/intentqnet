"""Structured logging setup shared by all `ibqn` modules.

Every log record includes the emitting module name and, when available, the
`intent_id` it relates to, via the `extra={"intent_id": ...}` convention.
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def _configure_root() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-8s %(name)s intent_id=%(intent_id)s - %(message)s"
        )
    )
    handler.addFilter(_DefaultIntentIdFilter())
    root = logging.getLogger("ibqn")
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    root.propagate = False
    _CONFIGURED = True


class _DefaultIntentIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "intent_id"):
            record.intent_id = "-"
        return True


def get_logger(name: str) -> logging.Logger:
    """Returns a logger under the shared `ibqn` namespace.

    Args:
        name: dotted module name, typically `__name__`.
    """
    _configure_root()
    return logging.getLogger(f"ibqn.{name}")
