"""Environment/version introspection for `notebooks/00_environment_validation.ipynb`.

Reports only what can be read from the running environment - never a
hardcoded version string - so the notebook output is honest evidence of
what actually ran, not documentation copy-pasted into a cell.
"""
from __future__ import annotations

import importlib
import importlib.metadata
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import sequence

import ibqn
from ..network.capabilities import NetworkCapabilities
from ..network.sequence_adapter import SequenceAdapter
from ..network.topology import DEFAULT_FORMALISM, NetworkTopologySpec, NodeSpec, QuantumLinkSpec

_DEPENDENCIES = [
    "pydantic", "yaml", "networkx", "numpy", "scipy", "matplotlib", "pandas",
    "qutip", "stim", "gmpy2", "nbformat", "nbclient",
]


@dataclass(frozen=True)
class EnvironmentInfo:
    python_version: str
    platform: str
    sequence_version: str
    sequence_commit: str | None
    ibqn_version: str
    project_commit: str | None
    default_formalism: str
    dependency_versions: dict[str, str] = field(default_factory=dict)


def _git_commit(repo_root: Path) -> str | None:
    """Returns the git HEAD commit for `repo_root`, or `None` if it isn't a
    git checkout (e.g. installed from a wheel) or `git` is unavailable."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, timeout=10, check=True,
        )
        return result.stdout.strip()
    except Exception:
        return None


def _sequence_commit() -> str | None:
    """Git HEAD commit of the SeQUeNCe checkout backing the imported
    `sequence` package."""
    return _git_commit(Path(sequence.__file__).resolve().parent.parent)


def project_git_commit() -> str | None:
    """Git HEAD commit of this project's own repository (not the vendored
    SeQUeNCe submodule) - recorded on every `TrialRecord` (Fase H3) so a
    persisted result can be traced back to the exact `ibqn` code that
    produced it."""
    return _git_commit(Path(ibqn.__file__).resolve().parent.parent.parent)


def _dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _DEPENDENCIES:
        try:
            module = importlib.import_module(name)
        except ImportError:
            versions[name] = "NOT INSTALLED"
            continue
        versions[name] = getattr(module, "__version__", "unknown")
    return versions


def collect_environment_info() -> EnvironmentInfo:
    return EnvironmentInfo(
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        sequence_version=sequence.__version__,
        sequence_commit=_sequence_commit(),
        ibqn_version=ibqn.__version__,
        project_commit=project_git_commit(),
        default_formalism=DEFAULT_FORMALISM,
        dependency_versions=_dependency_versions(),
    )


def run_smoke_test() -> dict[str, object]:
    """Builds the smallest possible topology (2 routers + 1 BSM link) and
    runs the `Timeline` to completion, returning a few real, observed
    facts - not a canned "ok" string - so a broken environment fails loudly."""
    spec = NetworkTopologySpec(
        nodes=[NodeSpec(id="a", memories=2), NodeSpec(id="b", memories=2)],
        quantum_links=[QuantumLinkSpec(source="a", destination="b", distance_m=1000, attenuation_db_per_m=1e-5)],
        stop_time_s=0.01,
    )
    capabilities = NetworkCapabilities(spec)
    adapter = SequenceAdapter(spec, seed=0)
    adapter.run()
    return {
        "routers_built": len(adapter.router_ids()),
        "graph_nodes": capabilities.graph().number_of_nodes(),
        "graph_edges": capabilities.graph().number_of_edges(),
        "events_executed": adapter.get_timeline().run_counter,
    }
