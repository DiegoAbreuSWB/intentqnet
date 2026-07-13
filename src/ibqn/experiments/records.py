"""`TrialIdentity` (deterministic trial addressing) and `TrialRecord` (the
persisted row for one trial) - see docs/campaign_architecture.md, sections
3-4.
"""
from __future__ import annotations

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class TrialIdentity:
    """Addresses one trial: campaign x scenario x parameter combination x
    strategy x seed x intent. `trial_id` is stable for the same
    configuration regardless of execution order - never a sequential
    index - which is what makes `resume` a simple "already in trials.csv?"
    check (see docs/campaign_architecture.md, section 6)."""

    campaign: str
    scenario: str
    parameter_hash: str
    strategy: str
    seed: int
    intent_id: str

    @property
    def trial_id(self) -> str:
        return f"{self.campaign}:{self.scenario}:{self.parameter_hash}:{self.strategy}:{self.seed}:{self.intent_id}"


@dataclass
class TrialRecord:
    """One persisted row in `results/raw/<campaign>/trials.csv`. Fields
    with no real evidence are `None` (never `0`/`0.0`) - see
    docs/campaign_architecture.md, section 4, and docs/metrics.md."""

    # --- identity ---
    campaign: str
    trial_id: str
    scenario: str
    parameter_hash: str
    seed: int
    intent_id: str
    routing_strategy: str
    purification_policy: str
    reconciliation_enabled: bool

    # --- plan / requested parameters (always known before simulating) ---
    route: str
    hop_count: int | None
    reserved_memory_slots: int
    """Memory pool size reserved from SeQUeNCe (a RESOURCE) - formerly
    named `requested_pairs`; see docs/intent_resource_semantics.md. NOT a
    delivery cap - see `delivery_ratio`/`excess_delivery_pairs` below,
    which are computed against `min_delivered_pairs` instead."""
    min_delivered_pairs: int | None
    """OPTIONAL service-level delivery goal declared by the intent (Fase
    J2) - `None` when the intent doesn't declare one."""
    requested_fidelity: float
    fidelity_estimator: str
    """Name of the `planning.fidelity_estimation.LinkFidelityEstimator`
    used to plan this trial (Fase J1)."""
    estimated_fidelity: float | None
    observed_fidelity: float | None
    """Same value as `average_fidelity` - kept as an explicit, separately
    named column for direct comparison against `estimated_fidelity`
    without notebooks needing to know the two are the same measurement."""
    absolute_fidelity_error: float | None
    """`observed_fidelity - estimated_fidelity` - `None` whenever either
    side is unavailable (e.g. REJECTED trials, or no delivery evidence)."""
    relative_fidelity_error: float | None
    """`absolute_fidelity_error / estimated_fidelity` - `None` under the
    same conditions as `absolute_fidelity_error`, and also when
    `estimated_fidelity` is exactly 0."""
    duration_s: float
    attenuation_db_per_m: float | None
    distance_m: float | None
    coherence_time_s: float | None

    # --- outcome ---
    accepted: bool
    satisfied: bool | None
    recovered: bool | None
    final_status: str
    delivered_pairs: int | None
    excess_delivery_pairs: int | None
    """`max(0, delivered_pairs - min_delivered_pairs)` - `None` when
    `min_delivered_pairs` is `None` (see docs/intent_resource_semantics.md)."""
    delivery_ratio: float | None
    """`delivered_pairs / min_delivered_pairs` - `None` when
    `min_delivered_pairs` is `None`."""
    deliveries_per_reserved_slot: float | None
    """`delivered_pairs / reserved_memory_slots` - a RESOURCE-efficiency
    view (memory reuse), always computable whenever delivery evidence
    exists, independent of any declared delivery goal."""
    average_fidelity: float | None
    minimum_fidelity: float | None
    throughput_active_window: float | None
    throughput_delivery_interval: float | None
    first_pair_latency_s: float | None
    completion_time_s: float | None
    planning_time_s: float | None
    simulation_wall_time_s: float | None
    eg_attempts: int | None
    eg_success: int | None
    ep_attempts: int | None
    ep_success: int | None
    es_attempts: int | None
    es_success: int | None
    violations: str

    # --- failure (only set for records written from a caught exception) ---
    error_type: str | None
    error_message: str | None

    # --- provenance ---
    project_git_commit: str | None
    sequence_git_commit: str | None
    python_version: str
    timestamp: str

    @classmethod
    def fieldnames(cls) -> list[str]:
        """Column order for `trials.csv` - stable across writes/reads."""
        return [f.name for f in fields(cls)]
