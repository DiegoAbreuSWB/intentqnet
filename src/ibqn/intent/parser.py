"""Parses an `EntanglementIntent` from a plain Python dict, JSON/YAML text, or
a JSON/YAML file - matching the constraint that intents "will be provided by
Python objects, JSON, or YAML" (no natural-language interpretation in v1).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from .models import EntanglementIntent, SuccessCondition


def _normalize_validation(raw_validation: dict[str, Any]) -> dict[str, Any]:
    """Converts the YAML/JSON `success_conditions` mapping (metric -> "op value")
    into the `list[SuccessCondition]` shape `IntentValidation` expects."""
    raw_conditions = raw_validation.get("success_conditions")
    if isinstance(raw_conditions, dict):
        conditions = [
            SuccessCondition.parse(metric, expression).model_dump()
            for metric, expression in raw_conditions.items()
        ]
        normalized = dict(raw_validation)
        normalized["success_conditions"] = conditions
        return normalized
    return raw_validation


def parse_intent_dict(data: dict[str, Any]) -> EntanglementIntent:
    """Builds an `EntanglementIntent` from a plain dict.

    Accepts both a bare intent mapping and one wrapped under an `intent:` root
    key (the shape used in standalone intent YAML/JSON files).
    """
    payload = data["intent"] if "intent" in data and len(data) == 1 else data
    payload = dict(payload)
    if "validation" in payload:
        payload["validation"] = _normalize_validation(payload["validation"])
    return EntanglementIntent.model_validate(payload)


def parse_intent_json(text: str) -> EntanglementIntent:
    return parse_intent_dict(json.loads(text))


def parse_intent_yaml(text: str) -> EntanglementIntent:
    return parse_intent_dict(yaml.safe_load(text))


def load_intent_file(path: str | Path) -> EntanglementIntent:
    """Loads an intent from a `.json`, `.yaml`, or `.yml` file, dispatching on suffix."""
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        return parse_intent_json(text)
    if suffix in (".yaml", ".yml"):
        return parse_intent_yaml(text)
    raise ValueError(f"Unsupported intent file extension '{suffix}' for {file_path}")
