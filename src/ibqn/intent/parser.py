"""Parses an `EntanglementIntent` from a plain Python dict, JSON/YAML text, or
a JSON/YAML file - matching the constraint that intents "will be provided by
Python objects, JSON, or YAML" (no natural-language interpretation in v1).
"""
from __future__ import annotations

import json
import time
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


def _merge_resources_and_time_blocks(payload: dict[str, Any]) -> dict[str, Any]:
    """Accepts the Fase J2 spec's literal top-level `resources:`/`time:`
    sibling blocks (e.g. `resources: {reserved_memory_slots: 10}`,
    `time: {start_time_s: 0.01, duration_s: 0.1}`) by folding their keys
    into `requirements` before model validation - `IntentRequirements`
    itself only ever sees one flat mapping (see docs/intent_resource_semantics.md
    for why this project keeps a single `requirements` model instead of
    three separate ones)."""
    sibling_keys = [key for key in ("resources", "time") if key in payload]
    if not sibling_keys:
        return payload
    merged_requirements = dict(payload.get("requirements", {}))
    for sibling_key in sibling_keys:
        for field_name, value in dict(payload[sibling_key]).items():
            if field_name in merged_requirements and merged_requirements[field_name] != value:
                raise ValueError(
                    f"intent declares '{sibling_key}.{field_name}'={value!r} and "
                    f"'requirements.{field_name}'={merged_requirements[field_name]!r} with different "
                    f"values - specify only one"
                )
            merged_requirements[field_name] = value
    payload = {k: v for k, v in payload.items() if k not in sibling_keys}
    payload["requirements"] = merged_requirements
    return payload


def parse_intent_dict(data: dict[str, Any]) -> EntanglementIntent:
    """Builds an `EntanglementIntent` from a plain dict.

    Accepts both a bare intent mapping and one wrapped under an `intent:` root
    key (the shape used in standalone intent YAML/JSON files).
    """
    payload = data["intent"] if "intent" in data and len(data) == 1 else data
    payload = dict(payload)
    payload = _merge_resources_and_time_blocks(payload)
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


def load_intent_file_with_timing(path: str | Path) -> tuple[EntanglementIntent, float, float]:
    """Same as `load_intent_file`, but also returns
    `(parsing_wall_time_s, validation_wall_time_s)` split at the exact
    seam between "read the file and normalize its shape" and "pydantic's
    own field validation" (Fase J7, see docs/overhead_methodology.md) -
    reuses the same private helpers `parse_intent_dict` does, so this is
    not a second, divergent parsing path."""
    file_path = Path(path)
    t0 = time.perf_counter()
    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        data = json.loads(text)
    elif suffix in (".yaml", ".yml"):
        data = yaml.safe_load(text)
    else:
        raise ValueError(f"Unsupported intent file extension '{suffix}' for {file_path}")

    payload = data["intent"] if "intent" in data and len(data) == 1 else data
    payload = dict(payload)
    payload = _merge_resources_and_time_blocks(payload)
    if "validation" in payload:
        payload["validation"] = _normalize_validation(payload["validation"])
    t1 = time.perf_counter()

    intent = EntanglementIntent.model_validate(payload)
    t2 = time.perf_counter()

    return intent, (t1 - t0), (t2 - t1)
