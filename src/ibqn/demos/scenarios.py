"""Builds a real, in-memory `experiments.scenarios.Scenario` from a
`NetworkTopologySpec` and a list of already-constructed `EntanglementIntent`s,
without writing anything to disk.

This is the "central, safe trial" mechanism the H2 notebooks use whenever
they need to run more than one simulation in the same kernel:
`experiments.runner.run_scenario` already calls `sequence.utils.metrics.
configure()` at the start of every call (see docs/notebooks.md and
notebook 06's empirical demonstration of what happens without it), so
routing every H2 trial through `run_scenario(ad_hoc_scenario(...), ...)`
means no notebook ever has to call `metrics.configure()` by hand.
"""
from __future__ import annotations

from ..config.schemas import IntentReference, ScenarioSpec, SimulationSpec
from ..experiments.scenarios import Scenario
from ..intent.models import EntanglementIntent
from ..network.topology import NetworkTopologySpec


def ad_hoc_scenario(
    topology_spec: NetworkTopologySpec,
    intents: list[EntanglementIntent],
    *,
    seed: int,
    name: str = "ad-hoc-demo",
) -> Scenario:
    """Wraps `topology_spec`/`intents` in a real `ScenarioSpec` + `Scenario`
    pair, bypassing `Scenario.load`'s file resolution (the `IntentReference`
    is a placeholder - `intents` is supplied directly, not read from it).
    """
    spec = ScenarioSpec(
        name=name,
        simulation=SimulationSpec(duration_s=topology_spec.stop_time_s, seed=seed),
        nodes=topology_spec.nodes,
        quantum_links=topology_spec.quantum_links,
        classical_delay_s=topology_spec.classical_delay_s,
        formalism=topology_spec.formalism,
        intents=[IntentReference(file="<in-memory, see Scenario.intents>")],
    )
    return Scenario(spec=spec, intents=intents)
