"""JSON/YAML (de)serialization helpers for pydantic models used across `ibqn`.

Kept generic on purpose: `intent.parser`, `intent.repository`, and later
`metrics.export` all need the same "model <-> dict/JSON/YAML text/file" plumbing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

ModelT = TypeVar("ModelT", bound=BaseModel)


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Converts a pydantic model to a plain JSON-serializable dict."""
    return model.model_dump(mode="json")


def model_to_json(model: BaseModel, *, indent: int = 2) -> str:
    return json.dumps(model_to_dict(model), indent=indent)


def model_to_yaml(model: BaseModel) -> str:
    return yaml.safe_dump(model_to_dict(model), sort_keys=False)


def load_dict_from_file(path: str | Path) -> dict[str, Any]:
    """Loads a dict from a `.json`, `.yaml`, or `.yml` file, dispatching on suffix."""
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        return json.loads(text)
    if suffix in (".yaml", ".yml"):
        return yaml.safe_load(text)
    raise ValueError(f"Unsupported config file extension '{suffix}' for {file_path}")
