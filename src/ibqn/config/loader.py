"""Loads a `ScenarioSpec` from a YAML/JSON file, accepting either a bare
mapping or one wrapped under a `scenario:` root key (the shape used in the
project brief's example scenario files).
"""
from __future__ import annotations

from pathlib import Path

from ..utils.serialization import load_dict_from_file
from .schemas import ScenarioSpec


def load_scenario_file(path: str | Path) -> ScenarioSpec:
    raw = load_dict_from_file(path)
    payload = raw["scenario"] if "scenario" in raw and len(raw) == 1 else raw
    return ScenarioSpec.model_validate(payload)
