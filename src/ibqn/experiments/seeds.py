"""Seed generation for repeated trials (see the project brief, section 22:
every experiment must run multiple seeds and record each repetition).

`NetworkTopologySpec.to_router_net_topo_config` derives per-node/per-link
seeds as `base_seed + index` for up to `len(nodes) + len(quantum_links)`
consecutive integers. If two trials' base seeds were close together (e.g.
consecutive integers), their derived per-node seed ranges could overlap and
correlate supposedly-independent trials. `STRIDE` is chosen larger than any
topology this project's test suite builds, keeping trials' seed ranges
disjoint.
"""
from __future__ import annotations

STRIDE = 1000


def seeds_for_trials(base_seed: int, n_trials: int) -> list[int]:
    """Returns `n_trials` seeds, `STRIDE` apart, starting at `base_seed`."""
    if n_trials <= 0:
        raise ValueError(f"n_trials must be positive, got {n_trials}")
    return [base_seed + i * STRIDE for i in range(n_trials)]
