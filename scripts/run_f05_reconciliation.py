"""Fase J10 final campaign F05 (reconciliation at scale) - ad-hoc script,
not run_programmatic_campaign/CampaignRunner (see
docs/results_provenance.md). 5 scenario classes x 20 seeds, with
per-episode delivered_pairs/fidelity/route/reserved_memory_slots/
duration_s captured for both episodes (added Fase K2, to support the
before-after reconciliation figure - see
scripts/generate_final_figures.py's figure_reconciliation()).
"""
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd

from sequence.utils import metrics

from ibqn.assurance.evaluator import evaluate_intent
from ibqn.assurance.reconciliation import reconcile
from ibqn.assurance.reconciliation_policy import apply_reconciliation_decision, decide_reconciliation_action
from ibqn.assurance.telemetry import collect_intent_evidence
from ibqn.assurance.violations import classify_violations
from ibqn.demos.intents import diamond_intent, simple_intent
from ibqn.demos.topologies import diamond_spec, three_node_spec
from ibqn.execution.sequence_executor import SequenceExecutor
from ibqn.intent.models import IntentStatus, SuccessCondition
from ibqn.intent.repository import IntentRepository
from ibqn.network.capabilities import NetworkCapabilities
from ibqn.network.sequence_adapter import SequenceAdapter
from ibqn.planning.planner import IntentPlanner
from ibqn.planning.routing import ShortestHopCountRouting

SEEDS = list(range(20))
RECONCILIATION_SEED_OFFSET = 1_000_000


def evidence_summary(intent):
    """delivered_pairs count + average_fidelity, straight from raw
    IntentEvidence - available regardless of which success_conditions
    the intent declares (unlike evaluation.condition_results, which only
    has entries for metrics some cases don't check, e.g. duration/slot
    cases only declare a delivered_pairs condition, never fidelity)."""
    evidence = collect_intent_evidence(intent)
    delivered_pairs = len(evidence.delivered_pairs)
    average_fidelity = (
        sum(p.fidelity for p in evidence.delivered_pairs) / delivered_pairs if delivered_pairs > 0 else None
    )
    return delivered_pairs, average_fidelity


def run_episode_1(topology_spec, intent, seed):
    metrics.configure()  # process-wide singleton, must reset before every independent run
    capabilities = NetworkCapabilities(topology_spec)
    planner = IntentPlanner(capabilities, routing_strategy=ShortestHopCountRouting())
    plan = planner.plan(intent)
    if not plan.feasible:
        return None, None, None
    repository = IntentRepository()
    adapter = SequenceAdapter(topology_spec, seed=seed)
    executor = SequenceExecutor(adapter, repository)
    executor.deploy(intent, plan)
    t0 = time.perf_counter()
    executor.run()
    sim_s = time.perf_counter() - t0
    if repository.get(intent.id).lifecycle.status != IntentStatus.ACTIVE:
        return None, None, None
    evidence = collect_intent_evidence(intent)
    evaluation = evaluate_intent(intent, evidence)
    final_status = IntentStatus.SATISFIED if evaluation.satisfied else IntentStatus.VIOLATED
    repository.transition(intent.id, final_status, "; ".join(evaluation.violations) or "satisfied", sim_time=0.0)
    return repository, plan, evaluation


def run_scenario_case(case_name, topology_spec, intent, seed, *, duration_multiplier=2.0, slot_multiplier=2.0):
    ep1_slots = intent.requirements.reserved_memory_slots
    ep1_duration = intent.requirements.duration_s

    repository, plan, evaluation = run_episode_1(topology_spec, intent, seed)
    if repository is None:
        return {
            "case": case_name, "seed": seed, "initial_status": "REJECTED_OR_FAILED", "action": None,
            "reconciliation_attempted": False, "recovered": None, "additional_wall_time_s": None, "episodes": 1,
            "episode1_route": None, "episode1_delivered_pairs": None, "episode1_average_fidelity": None,
            "episode1_reserved_memory_slots": ep1_slots, "episode1_duration_s": ep1_duration,
            "episode2_route": None, "episode2_delivered_pairs": None, "episode2_average_fidelity": None,
            "episode2_reserved_memory_slots": None, "episode2_duration_s": None,
        }

    ep1_delivered, ep1_fidelity = evidence_summary(intent)
    ep1_route = "->".join(plan.route) if plan.route else None
    status = repository.get(intent.id).lifecycle.status
    base_row = {
        "case": case_name, "seed": seed,
        "episode1_route": ep1_route, "episode1_delivered_pairs": ep1_delivered, "episode1_average_fidelity": ep1_fidelity,
        "episode1_reserved_memory_slots": ep1_slots, "episode1_duration_s": ep1_duration,
    }

    if status != IntentStatus.VIOLATED:
        return {
            **base_row, "initial_status": status.value, "action": None,
            "reconciliation_attempted": False, "recovered": None, "additional_wall_time_s": None, "episodes": 1,
            "episode2_route": None, "episode2_delivered_pairs": None, "episode2_average_fidelity": None,
            "episode2_reserved_memory_slots": None, "episode2_duration_s": None,
        }

    violations = classify_violations(evaluation)
    capabilities = NetworkCapabilities(topology_spec)
    decision = decide_reconciliation_action(
        violations, capabilities=capabilities, source=intent.endpoints.source, destination=intent.endpoints.destination,
        current_route=plan.route, current_reserved_memory_slots=intent.requirements.reserved_memory_slots,
        min_fidelity=intent.requirements.min_fidelity, allow_purification=intent.policy.allow_purification,
    )
    if decision.action == "no_action":
        return {
            **base_row, "initial_status": "VIOLATED", "action": decision.action,
            "reconciliation_attempted": False, "recovered": None, "additional_wall_time_s": None, "episodes": 1,
            "episode2_route": None, "episode2_delivered_pairs": None, "episode2_average_fidelity": None,
            "episode2_reserved_memory_slots": None, "episode2_duration_s": None,
        }

    adjusted_intent = apply_reconciliation_decision(intent, decision, duration_multiplier=duration_multiplier, slot_multiplier=slot_multiplier)
    t0 = time.perf_counter()
    result = reconcile(
        intent, topology_spec, repository, evaluation, seed=seed + RECONCILIATION_SEED_OFFSET,
        routing_strategy=decision.recommended_routing_strategy or ShortestHopCountRouting(),
        intent_override=adjusted_intent if adjusted_intent != intent else None,
    )
    additional_wall_time_s = time.perf_counter() - t0
    recovered = result.final_status == IntentStatus.SATISFIED

    working_intent = adjusted_intent if adjusted_intent != intent else intent
    ep2_delivered, ep2_fidelity = evidence_summary(working_intent)
    ep2_route = "->".join(result.new_plan.route) if result.new_plan and result.new_plan.route else None

    return {
        **base_row, "initial_status": "VIOLATED", "action": decision.action,
        "reconciliation_attempted": True, "recovered": recovered, "additional_wall_time_s": additional_wall_time_s, "episodes": 2,
        "episode2_route": ep2_route, "episode2_delivered_pairs": ep2_delivered, "episode2_average_fidelity": ep2_fidelity,
        "episode2_reserved_memory_slots": working_intent.requirements.reserved_memory_slots,
        "episode2_duration_s": working_intent.requirements.duration_s,
    }


rows = []

# Case A: recoverable by route change (diamond, ShortestHopCountRouting picks 'bad')
diamond = diamond_spec()
diamond_int = diamond_intent(requested_pairs=10, min_fidelity=0.6)
for seed in SEEDS:
    rows.append(run_scenario_case("route_change_recoverable", diamond, diamond_int, seed))

# Case B: recoverable by duration increase (three_node, short window)
dur_spec = three_node_spec(attenuation_db_per_m=0.01, stop_time_s=0.3)
dur_intent = simple_intent(
    intent_id="f05-dur", source="a", destination="b", min_fidelity=0.6, requested_pairs=10,
    min_delivered_pairs=30, start_time=0.01, duration=0.03,
    success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=30)],
)
for seed in SEEDS:
    rows.append(run_scenario_case("duration_increase_recoverable", dur_spec, dur_intent, seed))

# Case C: recoverable by slot increase (three_node, few slots)
slot_spec = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.3, repeater_memories=40, end_memories=20)
slot_intent = simple_intent(
    intent_id="f05-slot", source="a", destination="b", min_fidelity=0.6, requested_pairs=2,
    min_delivered_pairs=30, start_time=0.01, duration=0.02,
    success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=30)],
)
for seed in SEEDS:
    rows.append(run_scenario_case("slot_increase_recoverable", slot_spec, slot_intent, seed))

# Case D: irrecoverable by physical fidelity ceiling (three_node, min_fidelity above what even purification reaches)
ceiling_spec = three_node_spec(attenuation_db_per_m=1e-5, stop_time_s=0.2)
ceiling_intent = simple_intent(
    intent_id="f05-ceiling", source="a", destination="b", min_fidelity=0.9, requested_pairs=10,
    min_delivered_pairs=10, start_time=0.01, duration=0.1,
)
for seed in SEEDS:
    rows.append(run_scenario_case("fidelity_ceiling_unrecoverable", ceiling_spec, ceiling_intent, seed))

# Case E: attempted duration increase that is NOT enough (severe loss) - genuinely unrecoverable in practice
severe_spec = three_node_spec(attenuation_db_per_m=0.03, stop_time_s=0.3)
severe_intent = simple_intent(
    intent_id="f05-severe", source="a", destination="b", min_fidelity=0.6, requested_pairs=10,
    min_delivered_pairs=60, start_time=0.01, duration=0.03,
    success_conditions=[SuccessCondition(metric="delivered_pairs", operator=">=", expected=60)],
)
for seed in SEEDS:
    rows.append(run_scenario_case("severe_loss_attempt", severe_spec, severe_intent, seed, duration_multiplier=2.0))

df = pd.DataFrame(rows)
out_dir = PROJECT_ROOT / "results" / "raw" / "F05_reconciliation"
out_dir.mkdir(parents=True, exist_ok=True)
df.to_csv(out_dir / "trials.csv", index=False)
print(df.groupby(["case", "action"], dropna=False)["recovered"].agg(["count", "mean"]))
print()
print(df[["case", "seed", "episode1_delivered_pairs", "episode2_delivered_pairs"]].head(10).to_string())
print("wrote", len(df), "rows")
print("DONE")
