"""M10.2: `DeterministicExecutionContext` - an ISOLATED determinism
mechanism for M10's own new campaigns only. Never applied to, and never
changes the behavior of, any existing campaign (P01-P02B, P03, or M9's
own P02_variance/P04_retry_storm) - those keep their original, unmodified
execution path. Activated only by an explicit `determinism:` block in a
campaign's own YAML config (`enabled: true`), never a default.

Grounded in the M10.1 audit (`docs/predictability_m10/randomness_audit.md`):
the only randomness source dynamically confirmed to actually drive a real
trial's physical trajectory is the per-node/per-link `numpy.random.
default_rng(seed)` generator, seeded via `NetworkTopologySpec.
to_router_net_topo_config`'s `seed + index` derivation from the seed
handed to `SequenceAdapter`. Every OTHER candidate source audited (the
bare `random` module, qutip's module-level `_RAND` singleton, legacy
`numpy.random.*` globals) was confirmed DORMANT for IBQN's actual
simulation path - not merely assumed inert.

**What this context does and does not control** (stated plainly, not
implied):
- It reseeds Python's global `random` module (equivalent to calling
  SeQUeNCe's own `Timeline.seed()`, which does exactly this internally -
  see `randomness_audit.md`) - defense-in-depth, since the audit found
  this module unused in practice, not because it is known to matter.
- It derives one stable seed per RNG "namespace" (execution, generation,
  swap, purification, planner, internal_simulation, instrumentation) via
  SHA-256 (never Python's native, process-randomized `hash()`) - but
  SeQUeNCe's actual architecture gives each NODE exactly one generator
  shared across all of that node's generation/swap/purification
  sampling (`Entity.get_generator()`), not one stream per physical
  process. Only the `execution` namespace's derived value is therefore
  actually WIRED into `SequenceAdapter(seed=...)` (the one real hook
  SeQUeNCe exposes). The other namespaces are computed and recorded in
  `RngManifest` for full provenance and future extensibility, but are
  NOT separately injectable into SeQUeNCe's single-generator-per-node
  design without modifying SeQUeNCe itself - out of scope. This is a
  disclosed limitation, not a silent gap.
- `PYTHONHASHSEED` cannot be changed for an already-running process (a
  hard Python/CPython limitation, not specific to this project) - this
  context can only PIN it for a subprocess it launches (via
  `build_subprocess_environment`), documented, not worked around.
- L4's own internal-simulation seed isolation (`planning.planners.
  l4_simulation._derive_internal_seeds`, `INTERNAL_SEED_BASE_OFFSET`) is
  frozen, untouched planner code - this context's `internal_simulation`
  namespace seed is recorded for provenance only and is never fed into L4.
"""
from __future__ import annotations

import hashlib
import platform
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

MASTER_SEED_BYTE_LENGTH = 8
"""First 8 bytes (64 bits) of each namespace's SHA-256 digest are used as
the derived seed - ample range for `numpy.random.default_rng`/`random.
seed`, and far more collision-resistant than Python's native `hash()`
(which is process-randomized by `PYTHONHASHSEED` and explicitly the
wrong tool here - see the module docstring)."""

NAMESPACES = (
    "execution", "generation", "swap", "purification", "planner",
    "internal_simulation", "instrumentation",
)


@dataclass(frozen=True)
class DeterminismConfig:
    """Parsed from a campaign YAML's `determinism:` block. `enabled=False`
    (the default if the block is absent) means this context is a no-op -
    existing campaigns' behavior is never changed by this module merely
    existing."""

    enabled: bool = False
    master_seed: int = 0
    verify_replay: bool = False


def derive_namespace_seed(*, campaign_id: str, trial_id: str, namespace: str, master_seed: int) -> int:
    """`SHA-256(campaign_id + trial_id + namespace + master_seed)`,
    truncated to 64 bits - stable across processes/platforms/Python
    versions (unlike `hash()`, which is salted per-process by
    `PYTHONHASHSEED` and not guaranteed stable even within one process
    for non-string/bytes/int types)."""
    if namespace not in NAMESPACES:
        raise ValueError(f"unknown RNG namespace '{namespace}' - expected one of {NAMESPACES}")
    payload = f"{campaign_id}|{trial_id}|{namespace}|{master_seed}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:MASTER_SEED_BYTE_LENGTH], byteorder="big", signed=False)


@dataclass(frozen=True)
class RngManifest:
    """Everything M10.1's audit found relevant, recorded per-trial for
    full provenance - attached to every M10 trial record, never to
    P01-P02B/P03/M9's frozen schemas."""

    determinism_enabled: bool
    master_seed: int | None
    namespace_seeds: dict[str, int]
    execution_seed_used_by_sequence_adapter: int | None
    python_random_reseeded: bool
    python_hash_seed_env_value: str | None
    """The `PYTHONHASHSEED` value the CURRENT process inherited from its
    environment at import time - `None` if unset (randomized). This
    context cannot change it for an already-running process (see module
    docstring) - it can only report what this process has, and set it
    for a CHILD process it spawns (`build_subprocess_environment`)."""
    project_git_commit: str | None
    sequence_git_commit: str | None
    python_version: str
    numpy_version: str
    platform_system: str
    platform_release: str
    hostname: str
    verify_replay_requested: bool


def _read_python_hash_seed_env() -> str | None:
    import os

    return os.environ.get("PYTHONHASHSEED")


def apply_determinism(
    *, campaign_id: str, trial_id: str, config: DeterminismConfig,
    project_commit: str | None = None, sequence_commit: str | None = None,
) -> tuple[int | None, RngManifest]:
    """Call ONCE per trial, before constructing `SequenceAdapter`. Returns
    `(execution_seed, manifest)` - `execution_seed` is `None` when
    `config.enabled` is `False` (caller should fall back to its own
    `identity.seed`, unmodified - existing campaigns' behavior is
    preserved exactly)."""
    import numpy as np

    namespace_seeds = {
        ns: derive_namespace_seed(campaign_id=campaign_id, trial_id=trial_id, namespace=ns, master_seed=config.master_seed)
        for ns in NAMESPACES
    } if config.enabled else {}

    execution_seed = namespace_seeds.get("execution") if config.enabled else None

    python_random_reseeded = False
    if config.enabled:
        # Equivalent to SeQUeNCe's own `Timeline.seed(seed)` (which does
        # exactly `random.seed(seed)` internally, `kernel/timeline.py:166`)
        # - called directly here since no `Timeline` instance exists yet
        # at this point in trial construction.
        random.seed(execution_seed)
        python_random_reseeded = True

    manifest = RngManifest(
        determinism_enabled=config.enabled,
        master_seed=config.master_seed if config.enabled else None,
        namespace_seeds=namespace_seeds,
        execution_seed_used_by_sequence_adapter=execution_seed,
        python_random_reseeded=python_random_reseeded,
        python_hash_seed_env_value=_read_python_hash_seed_env(),
        project_git_commit=project_commit, sequence_git_commit=sequence_commit,
        python_version=sys.version.split()[0], numpy_version=np.__version__,
        platform_system=platform.system(), platform_release=platform.release(),
        hostname=platform.node(),
        verify_replay_requested=config.verify_replay,
    )
    return execution_seed, manifest


def build_subprocess_environment(config: DeterminismConfig, base_env: dict[str, str] | None = None) -> dict[str, str]:
    """`PYTHONHASHSEED` can only be fixed for a process from BEFORE it
    starts - this builds the environment dict to hand to
    `subprocess.run(..., env=...)` so the CHILD process (which does all
    the real simulation work in this project's subprocess-per-trial
    architecture) starts with a pinned hash seed. Has no effect on the
    CURRENT process - documented, not worked around."""
    import os

    env = dict(base_env if base_env is not None else os.environ)
    if config.enabled:
        env["PYTHONHASHSEED"] = "0"
    return env
