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
    requested_pairs: int
    requested_fidelity: float
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
    delivery_ratio: float | None
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
