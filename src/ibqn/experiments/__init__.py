from .scenarios import Scenario
from .runner import CampaignRunner, CampaignRunSummary, IntentRunResult, ScenarioResult, execute_trial, run_scenario
from .seeds import seeds_for_trials
from .campaigns import CampaignSpec, ExecutionOptions, load_campaign_file
from .records import TrialIdentity, TrialRecord
from .sweeps import (
    SWEEP_PARAMETERS,
    SweepParameter,
    TrialParameters,
    apply_parameters,
    compute_parameter_hash,
    expand_parameter_grid,
    resolve_fidelity_estimator,
    resolve_purification_policy,
    resolve_routing_strategy,
)
from .validation import ValidationIssue, validate_trials
from .aggregation import aggregate_records, align_paired_trials
from .status import CampaignStatus, compute_campaign_status
from .export import save_figure, save_table
from .baselines import (
    BaselineResult,
    run_native_sequence_baseline,
    run_offline_oracle_baseline,
    run_static_provisioning_baseline,
)
from .topology_catalog import linear_chain_spec, near_equivalent_paths_spec, small_mesh_spec
from .reconciliation_metrics import compute_reconciliation_metrics
from .overhead import TrialTiming, run_instrumented_trial
from .planner_operation_matrix import (
    EXECUTION_FAILED,
    FEASIBLE_AND_SATISFIED,
    FEASIBLE_BUT_VIOLATED,
    INFEASIBLE_AND_REJECTED,
    INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE,
    build_matrix,
    classify_trials,
    compute_gap_metrics,
    upgrade_rejected_with_oracle,
)

__all__ = [
    "Scenario",
    "IntentRunResult",
    "ScenarioResult",
    "run_scenario",
    "CampaignRunner",
    "CampaignRunSummary",
    "execute_trial",
    "seeds_for_trials",
    "CampaignSpec",
    "ExecutionOptions",
    "load_campaign_file",
    "TrialIdentity",
    "TrialRecord",
    "SWEEP_PARAMETERS",
    "SweepParameter",
    "TrialParameters",
    "apply_parameters",
    "compute_parameter_hash",
    "expand_parameter_grid",
    "resolve_routing_strategy",
    "resolve_purification_policy",
    "resolve_fidelity_estimator",
    "ValidationIssue",
    "validate_trials",
    "aggregate_records",
    "align_paired_trials",
    "CampaignStatus",
    "compute_campaign_status",
    "save_figure",
    "save_table",
    "BaselineResult",
    "run_native_sequence_baseline",
    "run_static_provisioning_baseline",
    "run_offline_oracle_baseline",
    "linear_chain_spec",
    "small_mesh_spec",
    "near_equivalent_paths_spec",
    "FEASIBLE_AND_SATISFIED",
    "FEASIBLE_BUT_VIOLATED",
    "INFEASIBLE_AND_REJECTED",
    "INFEASIBLE_BUT_POTENTIALLY_SATISFIABLE",
    "EXECUTION_FAILED",
    "classify_trials",
    "upgrade_rejected_with_oracle",
    "build_matrix",
    "compute_gap_metrics",
    "compute_reconciliation_metrics",
    "TrialTiming",
    "run_instrumented_trial",
]
