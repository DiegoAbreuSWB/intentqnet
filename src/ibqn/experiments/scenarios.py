"""`Scenario`: a loaded `ScenarioSpec` plus its resolved `EntanglementIntent`
objects, ready to hand to `experiments.runner.run_scenario`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config.loader import load_scenario_file
from ..config.schemas import ScenarioSpec
from ..intent.models import EntanglementIntent
from ..intent.parser import load_intent_file
from ..network.topology import NetworkTopologySpec


@dataclass
class Scenario:
    spec: ScenarioSpec
    intents: list[EntanglementIntent]

    @classmethod
    def load(cls, path: str | Path) -> "Scenario":
        scenario_path = Path(path)
        spec = load_scenario_file(scenario_path)
        intents = [
            load_intent_file(scenario_path.parent / reference.file) for reference in spec.intents
        ]
        return cls(spec=spec, intents=intents)

    def topology_spec(self) -> NetworkTopologySpec:
        return self.spec.to_network_topology_spec()
