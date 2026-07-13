"""`CampaignSpec`: a declarative campaign - a base scenario, a parameter
grid to sweep, strategies to compare, and seeds to repeat - loaded from
YAML/JSON (see docs/campaign_architecture.md and configs/campaigns/*.yaml
for real examples).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..planning.fidelity_estimation import FIDELITY_ESTIMATORS
from ..utils.serialization import load_dict_from_file
from .sweeps import (
    PURIFICATION_POLICIES,
    ROUTING_STRATEGIES,
    ensure_known_parameters,
    ensure_valid_values,
)

_STRATEGY_CATEGORIES: dict[str, dict[str, type]] = {
    "routing": ROUTING_STRATEGIES,
    "purification": PURIFICATION_POLICIES,
    "fidelity_estimator": FIDELITY_ESTIMATORS,
}


class ExecutionOptions(BaseModel):
    model_config = ConfigDict(frozen=True)

    continue_on_error: bool = True
    resume: bool = True


class CampaignSpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    description: str = ""
    scenario_file: str = Field(min_length=1, description="path to a scenario YAML/JSON, relative to the campaign file's directory")
    intents: list[str] = Field(min_length=1, description="paths to intent YAML/JSON files, relative to the campaign file's directory")
    seeds: list[int] = Field(min_length=1)
    strategies: dict[str, list[str]] = Field(default_factory=dict)
    parameter_grid: dict[str, list[Any]] = Field(default_factory=dict)
    execution: ExecutionOptions = Field(default_factory=ExecutionOptions)
    output_directory: str = "results"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _strategies_reference_known_names(self) -> "CampaignSpec":
        for category, names in self.strategies.items():
            if category not in _STRATEGY_CATEGORIES:
                raise ValueError(
                    f"unknown strategy category '{category}' in campaign '{self.name}' - "
                    f"supported categories: {sorted(_STRATEGY_CATEGORIES)}"
                )
            if not names:
                raise ValueError(f"strategy category '{category}' has an empty list of names")
            known = _STRATEGY_CATEGORIES[category]
            unknown = sorted(set(names) - known.keys())
            if unknown:
                raise ValueError(
                    f"unknown {category} strategy name(s) {unknown} in campaign '{self.name}' - "
                    f"supported: {sorted(known)}"
                )
        return self

    @model_validator(mode="after")
    def _parameter_grid_is_well_formed(self) -> "CampaignSpec":
        ensure_known_parameters(self.parameter_grid.keys())
        for name, values in self.parameter_grid.items():
            if not values:
                raise ValueError(f"parameter '{name}' has an empty value list in campaign '{self.name}'")
        ensure_valid_values(self.parameter_grid)
        return self

    def effective_parameter_grid(self) -> dict[str, list[Any]]:
        """Merges `strategies` into `parameter_grid` under the sweep
        parameter names the runner actually expands over
        (`routing_strategy`/`purification_policy`/`fidelity_estimator`), so
        campaigns can use the more readable `strategies: {routing: [...]}`
        shape while everything downstream goes through the same
        `sweeps.expand_parameter_grid` mechanism."""
        merged = dict(self.parameter_grid)
        if "routing" in self.strategies:
            merged["routing_strategy"] = list(self.strategies["routing"])
        if "purification" in self.strategies:
            merged["purification_policy"] = list(self.strategies["purification"])
        if "fidelity_estimator" in self.strategies:
            merged["fidelity_estimator"] = list(self.strategies["fidelity_estimator"])
        return merged


def load_campaign_file(path: str | Path) -> CampaignSpec:
    """Loads a `CampaignSpec` from `path`, then checks that `scenario_file`
    and every entry in `intents` actually exist on disk (relative to
    `path`'s directory) - file-existence is an I/O concern kept out of the
    Pydantic model itself (mirroring `config.loader.load_scenario_file`)."""
    campaign_path = Path(path)
    raw = load_dict_from_file(campaign_path)
    payload = raw["campaign"] if "campaign" in raw and len(raw) == 1 else raw
    spec = CampaignSpec.model_validate(payload)

    base_dir = campaign_path.parent
    scenario_path = base_dir / spec.scenario_file
    if not scenario_path.exists():
        raise FileNotFoundError(f"campaign '{spec.name}' references a missing scenario_file: {scenario_path}")
    for intent_file in spec.intents:
        intent_path = base_dir / intent_file
        if not intent_path.exists():
            raise FileNotFoundError(f"campaign '{spec.name}' references a missing intent file: {intent_path}")

    return spec
