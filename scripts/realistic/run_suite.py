"""The calibrated ("realistic") campaign suite - one entry point.

Every campaign runs under two hardware conditions (docs/parameter_calibration.md):
`literature` (platform siv_2024, every parameter demonstrated) and
`theoretical_ops` (same hardware, ideal gates/measurement, so BBPSSW
purification behaves as in theory).

  python scripts/realistic/run_suite.py <campaign> [--seeds N] [--workers N] [--out DIR]

Campaigns (replacing the legacy F0x/P0x/P1x set; results under results/realistic/):
  r01  architecture baselines (native / static / IBQN +- assurance +- reconciliation / oracle)
  r02  routing strategies (diamond, mesh)
  r03  purification policies (never / once / until_target with 1-round and iterative estimates)
  r04  planner evolution (L1, L2, L2-R, L3, L3-R, L2-RB, L3-RB)
  r04b simulation-in-the-loop planner (L4) on a reduced grid
  r05  offline oracle on r04's rejected intents (false-rejection rate)
  r06  reconciliation (route change / duration / slots / unrecoverable cases)
  r07  orchestration overhead
  r08  resource semantics (reserved slots vs. duration)
  r09  multi-intent (non-conflicting / contention / sequential)
  all  everything, in dependency order

Campaigns resume: completed jobs found in the output files are skipped.
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.demos.environment import collect_environment_info  # noqa: E402
from ibqn.experiments.programmatic_campaign import run_programmatic_campaign  # noqa: E402
from ibqn.experiments.realistic_suite import (  # noqa: E402
    BASELINE_CONDITIONS,
    HARDWARE,
    OVERHEAD_CONDITIONS,
    build_intent,
    build_topology,
    run_baseline_job,
    run_jobs_to_csv,
    run_multi_intent_job,
    run_oracle_job,
    run_overhead_job,
    run_planner_case_job,
    run_reconciliation_job,
)

DEFAULT_OUT = PROJECT_ROOT / "results" / "realistic"
HARDWARE_CONDITIONS = list(HARDWARE)

ENDPOINTS = {
    "chain1": ("a", "b"), "chain2": ("a", "b"), "chain3": ("a", "b"),
    # mesh: a 3-hop pair with three equal-length candidate routes. The opposite corner (a0 -> b3, 4 hops)
    # is out of reach of the literature hardware: three swaps leave F = 0.509, the separability threshold.
    "diamond": ("r1", "r3"), "mesh": ("a0", "b2"),
}


def combo(min_fidelity, slots, duration, pairs, regime, allow_purification=True) -> dict:
    return dict(min_fidelity=min_fidelity, reserved_memory_slots=slots, duration_s=duration,
                min_delivered_pairs=pairs, allow_purification=allow_purification, regime=regime)


# Fidelity reference points behind the grids (ibqn.physics, raw link 0.86):
#   literature (g=0.937, m=0.995): swap x1 0.709, x2 0.595, x3 0.509; one BBPSSW round does not help.
#   theoretical ops (g=m=1):      swap x1 0.746, x2 0.654, x3 0.578;
#                                 chain1 purified 0.784 / 0.823 / 0.860 (1/2/3 rounds),
#                                 chain2 purified 0.683 / 0.717 / 0.753.
PLANNER_GRID = {
    "chain1": [
        combo(0.60, 4, 0.3, 10, "generous"),
        combo(0.66, 4, 0.3, 10, "generous"),
        combo(0.66, 4, 0.3, 10, "generous_no_purification", allow_purification=False),
        combo(0.60, 2, 0.1, 10, "marginal_resources"),
        combo(0.70, 4, 0.3, 10, "marginal_fidelity"),
        combo(0.76, 4, 0.3, 10, "purification_1_round"),
        combo(0.80, 4, 0.3, 10, "purification_2_rounds"),
        # two rounds are affordable for a small delivery goal: the regime where a one-round
        # estimate (L1) rejects an intent the network can actually satisfy
        combo(0.80, 4, 0.3, 3, "purification_2_rounds_small_goal"),
    ],
    "chain2": [
        combo(0.50, 4, 0.3, 10, "generous"),
        combo(0.56, 4, 0.3, 10, "generous"),
        combo(0.56, 4, 0.3, 10, "generous_no_purification", allow_purification=False),
        combo(0.50, 2, 0.1, 10, "marginal_resources"),
        combo(0.58, 4, 0.3, 10, "marginal_fidelity"),
        combo(0.67, 4, 0.3, 10, "purification_1_round"),
        combo(0.70, 4, 0.3, 10, "purification_2_rounds"),
    ],
    "diamond": [
        combo(0.55, 4, 0.3, 10, "generous"),
        combo(0.65, 4, 0.3, 10, "marginal_fidelity"),
        combo(0.65, 4, 0.3, 1, "generous_small_goal"),
    ],
    "mesh": [  # 3 hops, same physics as chain2 but with route diversity
        combo(0.50, 4, 0.3, 10, "generous"),
        combo(0.50, 2, 0.1, 10, "marginal_resources"),
        combo(0.58, 4, 0.3, 10, "marginal_fidelity"),
        combo(0.67, 4, 0.3, 10, "purification_1_round"),
    ],
}
PLANNERS = ["L1", "L2", "L2-R", "L3", "L3-R", "L2-RB", "L3-RB"]
ORACLE_PLANNERS = ["L1", "L2", "L2-R", "L2-RB"]  # the L3 family is collected at admission threshold 0 and never rejects

L4_GRID = {"chain1": [PLANNER_GRID["chain1"][0], PLANNER_GRID["chain1"][3], PLANNER_GRID["chain1"][4]]}


def _commits() -> dict:
    env = collect_environment_info()
    return dict(project_commit=env.project_commit, sequence_commit=env.sequence_commit)


def _combo_without_regime(c: dict) -> dict:
    return {k: v for k, v in c.items() if k != "regime"}


# --------------------------------------------------------------------------
def r04_planners(args, *, campaign="R04_planner_evolution", grid=PLANNER_GRID, planners=PLANNERS, l4_simulations=None):
    commits = _commits()
    jobs = []
    # one job per case (topology, hardware, intent, seed) running every planner level: levels that
    # choose the same route and purification mode share one simulation
    for hardware, (topology, combos) in itertools.product(HARDWARE_CONDITIONS, grid.items()):
        source, destination = ENDPOINTS[topology]
        for c, seed in itertools.product(combos, range(args.seeds)):
            job = dict(campaign=campaign, topology=topology, hardware=hardware, planner_levels=list(planners), seed=seed,
                       regime=c["regime"], combo=_combo_without_regime(c), source=source, destination=destination, **commits)
            if l4_simulations is not None:
                job["l4_simulations"] = l4_simulations
            jobs.append(job)
    out = args.out / "planner_study" / campaign / "trials.csv"
    frame = run_jobs_to_csv(
        jobs, run_planner_case_job, out, workers=args.workers,
        key=lambda j: f"{j['topology']}@{j['hardware']}|{json.dumps(j['combo'], sort_keys=True)}|{j['regime']}|"
                      f"{'+'.join(j['planner_levels'])}|{j['seed']}",
        describe=lambda j, rows: f"{j['topology']}@{j['hardware']} F={j['combo']['min_fidelity']} {j['regime']} seed={j['seed']} -> "
                                 + " ".join(f"{r['planner_level']}:{r['final_status'][:3]}" for r in rows),
    )
    print(frame.groupby(["hardware", "topology", "planner_level"])["final_status"].value_counts().unstack(fill_value=0).to_string())


def r04b_l4(args):
    r04_planners(args, campaign="R04b_simulation_planner", grid=L4_GRID, planners=["L4"], l4_simulations=3)


def r05_oracle(args):
    source_csv = args.out / "planner_study" / "R04_planner_evolution" / "trials.csv"
    trials = pd.read_csv(source_csv)
    rejected = trials[(trials["final_status"] == "REJECTED") & (trials["planner_level"].isin(ORACLE_PLANNERS))]
    # The oracle's verdict depends only on (topology, hardware, intent, seed), not on which planner
    # rejected it - simulate each distinct case once and join the verdict back to every planner row.
    case_columns = ["topology", "hardware", "requested_fidelity", "reserved_memory_slots", "duration_s",
                    "min_delivered_pairs", "allow_purification", "regime", "seed"]
    cases = rejected[case_columns].drop_duplicates()
    jobs = []
    for case in cases.to_dict("records"):
        source, destination = ENDPOINTS[case["topology"]]
        jobs.append(dict(
            trial_id="|".join(str(case[c]) for c in case_columns), planner_level="any", topology=case["topology"],
            hardware=case["hardware"], seed=int(case["seed"]), regime=case["regime"], source=source, destination=destination,
            combo=dict(min_fidelity=float(case["requested_fidelity"]), reserved_memory_slots=int(case["reserved_memory_slots"]),
                       duration_s=float(case["duration_s"]), min_delivered_pairs=int(case["min_delivered_pairs"]),
                       allow_purification=bool(case["allow_purification"])),
        ))
    out_dir = args.out / "oracle" / "R05_oracle_by_planner"
    verdicts = run_jobs_to_csv(
        jobs, run_oracle_job, out_dir / "oracle_cases.csv", workers=args.workers, key=lambda j: j["trial_id"],
        describe=lambda j, r: f"{j['topology']}@{j['hardware']} F={j['combo']['min_fidelity']} seed={j['seed']} -> "
                              f"tested={r['oracle_tested']} satisfiable={r['oracle_satisfiable']}",
    )
    verdicts = verdicts.rename(columns={"requested_fidelity": "requested_fidelity"})
    join_columns = ["topology", "hardware", "requested_fidelity", "reserved_memory_slots", "duration_s",
                    "min_delivered_pairs", "allow_purification", "seed"]
    by_planner = rejected[["trial_id", "planner_level", "planner_name", "rejection_reason", *case_columns]].merge(
        verdicts[join_columns + ["oracle_tested", "oracle_satisfiable", "oracle_route", "oracle_delivered_pairs",
                                 "oracle_average_fidelity", "oracle_notes"]],
        on=join_columns, how="left",
    )
    by_planner.to_csv(out_dir / "oracle_by_planner.csv", index=False)
    summary = by_planner.groupby(["hardware", "planner_level"]).agg(
        rejected=("trial_id", "count"), tested=("oracle_tested", "sum"),
        satisfiable=("oracle_satisfiable", lambda s: int(s.fillna(False).astype(bool).sum())),
    )
    summary["false_rejection_rate"] = summary["satisfiable"] / summary["tested"].where(summary["tested"] > 0)
    print(summary.to_string())


# --------------------------------------------------------------------------
def _programmatic(args, campaign, scenarios):
    """`scenarios`: list of (topology, hardware-independent kwargs dict with
    keys combo, check_fidelity, grid, max_duration, [topology_kwargs])."""
    for hardware in HARDWARE_CONDITIONS:
        for topology, spec in scenarios:
            source, destination = ENDPOINTS[topology]
            base_topology = build_topology(topology, hardware, duration_s=spec["max_duration"], **spec.get("topology_kwargs", {}))
            intent = build_intent(f"{campaign.lower()}-{topology}", source, destination, spec["combo"],
                                  check_fidelity=spec.get("check_fidelity", False))
            summary = run_programmatic_campaign(
                campaign_name=campaign, scenario_name=f"{topology}@{hardware}", base_topology=base_topology,
                base_intents=[intent], parameter_grid=spec["grid"], seeds=list(range(args.seeds)),
                output_directory=args.out, workers=args.workers,
            )
            print(f"{campaign} {topology}@{hardware}: completed={summary.completed_trials} skipped={summary.skipped_trials} "
                  f"failed={summary.failed_trials} in {summary.duration_s:.0f}s", flush=True)
    return pd.read_csv(args.out / "raw" / campaign / "trials.csv")


def r02_routing(args):
    strategies = ["shortest_hop_count", "least_loss", "highest_fidelity"]
    frame = _programmatic(args, "R02_routing", [
        ("diamond", dict(combo=_combo_without_regime(combo(0.55, 4, 0.3, 10, "")), max_duration=0.3,
                         grid={"routing_strategy": strategies})),
        ("mesh", dict(combo=_combo_without_regime(combo(0.50, 4, 0.3, 10, "")), max_duration=0.3,
                      grid={"routing_strategy": strategies})),
    ])
    print(frame.groupby(["scenario", "routing_strategy"]).agg(
        route=("route", lambda s: s.mode().iat[0] if len(s.mode()) else None), satisfied=("satisfied", "mean"),
        delivered=("delivered_pairs", "mean"), fidelity=("average_fidelity", "mean"), estimated=("estimated_fidelity", "mean"),
    ).round(4).to_string())


def r03_purification(args):
    policies = ["disabled", "once", "automatic", "iterative_analytical"]
    frame = _programmatic(args, "R03_purification", [
        ("chain1", dict(combo=_combo_without_regime(combo(0.60, 4, 0.3, 10, "")), max_duration=0.3,
                        grid={"min_fidelity": [0.60, 0.66, 0.70, 0.72, 0.76, 0.80, 0.84], "purification_policy": policies})),
        ("chain2", dict(combo=_combo_without_regime(combo(0.50, 4, 0.3, 10, "")), max_duration=0.3,
                        grid={"min_fidelity": [0.50, 0.56, 0.58, 0.62, 0.67, 0.70, 0.74], "purification_policy": policies})),
    ])
    table = frame.groupby(["scenario", "requested_fidelity", "purification_policy"]).agg(
        status=("final_status", lambda s: "/".join(f"{k}:{v}" for k, v in s.value_counts().items())),
        delivered=("delivered_pairs", "mean"), fidelity=("average_fidelity", "mean"), estimated=("estimated_fidelity", "mean"),
        ep_ok=("ep_success", "mean"), ep_att=("ep_attempts", "mean"),
    ).round(4)
    print(table.to_string())


def r08_resource_semantics(args):
    frame = _programmatic(args, "R08_resource_semantics", [
        ("chain1", dict(combo=_combo_without_regime(combo(0.60, 4, 0.3, 20, "")), max_duration=0.3,
                        grid={"reserved_memory_slots": [2, 4], "duration_s": [0.15, 0.3]})),
    ])
    print(frame.groupby(["scenario", "reserved_memory_slots", "duration_s"]).agg(
        satisfied=("satisfied", "mean"), delivered=("delivered_pairs", "mean"), ratio=("delivery_ratio", "mean"),
    ).round(3).to_string())


# --------------------------------------------------------------------------
RECONCILIATION_CASES = [
    # (case, topology, combo, extra job fields)
    ("route_change_recoverable", "diamond", combo(0.55, 4, 0.3, 10, ""), {}),
    ("duration_increase_recoverable", "chain1", combo(0.60, 4, 0.15, 30, ""), {}),
    ("slot_increase_recoverable", "chain1", combo(0.60, 2, 0.3, 30, ""), {}),
    # target just under the literature swap output (0.709): pairs that idle lose the margin, so the
    # literature hardware delivers ~20 and violates a 30-pair goal that ideal operations (0.746) meet
    ("decoherence_margin", "chain1", combo(0.705, 4, 0.3, 30, ""), {}),
    ("severe_loss_attempt", "chain1", combo(0.60, 4, 0.15, 30, ""), {"topology_kwargs": {"link_m": 10_000.0}}),
    ("fidelity_ceiling_unrecoverable", "chain1", combo(0.90, 4, 0.3, 10, ""), {}),
]


def r06_reconciliation(args):
    jobs = []
    for hardware, (case, topology, c, extra), seed in itertools.product(HARDWARE_CONDITIONS, RECONCILIATION_CASES, range(args.seeds)):
        source, destination = ENDPOINTS[topology]
        jobs.append(dict(case=case, topology=topology, hardware=hardware, seed=seed, combo=_combo_without_regime(c),
                         source=source, destination=destination, **extra))
    frame = run_jobs_to_csv(
        jobs, run_reconciliation_job, args.out / "reconciliation" / "R06_reconciliation" / "trials.csv", workers=args.workers,
        key=lambda j: f"{j['case']}|{j['hardware']}|{j['seed']}",
        describe=lambda j, r: f"{j['case']}@{j['hardware']} seed={j['seed']} -> {r['initial_status']} action={r['action']} "
                              f"recovered={r['recovered']} ({r['episode1_delivered_pairs']} -> {r['episode2_delivered_pairs']})",
    )
    print(frame.groupby(["hardware", "case"]).agg(
        initial=("initial_status", lambda s: "/".join(f"{k}:{v}" for k, v in s.value_counts().items())),
        action=("action", lambda s: "/".join(f"{k}:{v}" for k, v in s.value_counts(dropna=False).items())),
        attempted=("reconciliation_attempted", "sum"), recovered=("recovered", lambda s: int(s.fillna(False).astype(bool).sum())),
        ep1=("episode1_delivered_pairs", "mean"), ep2=("episode2_delivered_pairs", "mean"),
    ).round(2).to_string())


def _condition_jobs(args, conditions, topology, c):
    source, destination = ENDPOINTS[topology]
    commits = _commits()
    return [
        dict(condition=condition, topology=topology, hardware=hardware, seed=seed, combo=_combo_without_regime(c),
             source=source, destination=destination, **commits)
        for hardware, condition, seed in itertools.product(HARDWARE_CONDITIONS, conditions, range(args.seeds))
    ]


def r01_baselines(args):
    jobs = _condition_jobs(args, BASELINE_CONDITIONS, "diamond", combo(0.55, 4, 0.3, 10, ""))
    frame = run_jobs_to_csv(
        jobs, run_baseline_job, args.out / "baselines" / "R01_architecture_baselines" / "trials.csv", workers=args.workers,
        key=lambda j: f"{j['condition']}|{j['hardware']}|{j['seed']}",
        describe=lambda j, r: f"{j['condition']}@{j['hardware']} seed={j['seed']} -> accepted={r['accepted']} "
                              f"satisfied={r['satisfied']} delivered={r['delivered_pairs']}",
    )
    print(frame.groupby(["hardware", "condition"]).agg(
        accepted=("accepted", "mean"), satisfied=("satisfied", lambda s: s.dropna().astype(float).mean() if s.notna().any() else None),
        delivered=("delivered_pairs", "mean"), fidelity=("average_fidelity", "mean"), episodes=("episodes", "mean"),
    ).round(3).to_string())


def r07_overhead(args):
    # Timing campaign: few workers so wall-clock measurements are not distorted by CPU contention, and a
    # single-route topology so every condition simulates the same reservation (on the diamond the
    # conditions pick different routes and their simulation times are not comparable).
    workers = min(args.workers, 4)
    jobs = _condition_jobs(args, OVERHEAD_CONDITIONS, "chain1", combo(0.60, 4, 0.3, 10, ""))
    frame = run_jobs_to_csv(
        jobs, run_overhead_job, args.out / "overhead" / "R07_overhead" / "trials.csv", workers=workers,
        key=lambda j: f"{j['condition']}|{j['hardware']}|{j['seed']}",
        describe=lambda j, r: f"{j['condition']}@{j['hardware']} seed={j['seed']} total={r['total_trial_wall_time_s']:.2f}s "
                              f"overhead={r['orchestration_overhead_ratio']}",
    )
    print(frame.groupby(["hardware", "condition"])[
        ["planning_wall_time_s", "simulation_wall_time_s", "total_trial_wall_time_s", "orchestration_overhead_ratio", "planning_overhead_ratio"]
    ].mean().to_string())


def _multi_intent_spec(role, source, destination, min_fidelity, slots, pairs, duration):
    return dict(group_role=role, source=source, destination=destination, min_fidelity=min_fidelity,
                reserved_memory_slots=slots, min_delivered_pairs=pairs, duration_s=duration)


MULTI_INTENT_SCENARIOS = [
    # two intents on disjoint rows of the mesh, one shared timeline
    dict(scenario="C1_non_conflicting", topology="mesh", sequential=False, intents=[
        _multi_intent_spec("A", "a0", "a3", 0.50, 3, 5, 0.3), _multi_intent_spec("B", "b0", "b3", 0.50, 3, 5, 0.3)]),
    # both intents need 2*3 memories at `center`, which only has 6: the second reservation is refused by RSVP
    dict(scenario="C2_resource_contention", topology="star", sequential=False,
         topology_kwargs={"center_memories": 6, "leaf_memories": 4}, intents=[
        _multi_intent_spec("A", "leaf1", "leaf2", 0.60, 3, 5, 0.3), _multi_intent_spec("B", "leaf3", "leaf4", 0.60, 3, 5, 0.3)]),
    # same intents and topology, one episode each: admission does not depend on submission order
    dict(scenario="C3_sequential_admission", topology="star", sequential=True,
         topology_kwargs={"center_memories": 6, "leaf_memories": 4}, intents=[
        _multi_intent_spec("A", "leaf1", "leaf2", 0.60, 3, 5, 0.3), _multi_intent_spec("B", "leaf3", "leaf4", 0.60, 3, 5, 0.3)]),
]


def r09_multi_intent(args):
    out_dir = args.out / "multi_intent" / "R09_multi_intent"
    jobs = [
        dict(scenario_spec, hardware=hardware, planner_level=level, seed=seed)
        for hardware, scenario_spec, level, seed in itertools.product(
            HARDWARE_CONDITIONS, MULTI_INTENT_SCENARIOS, ["L1", "L2-RB"], range(args.seeds))
    ]
    # each mesh job holds two reservations on one timeline: cap the pool so the campaign fits in memory
    jobs_frame = run_jobs_to_csv(
        jobs, run_multi_intent_job, out_dir / "jobs.csv", workers=min(args.workers, 6),
        key=lambda j: f"{j['scenario']}|{j['hardware']}|{j['planner_level']}|{j['seed']}",
        describe=lambda j, g: f"{j['scenario']}@{j['hardware']} {j['planner_level']} seed={j['seed']}: admitted={g['admitted']}/"
                              f"{g['intents_submitted']} satisfied={g['satisfied']} violated={g['violated']} failed={g['failed']}",
    )
    groups = jobs_frame.drop(columns=["intent_rows_json", "job_key"])
    groups.to_csv(out_dir / "groups.csv", index=False)
    intents = pd.DataFrame([row for encoded in jobs_frame["intent_rows_json"] for row in json.loads(encoded)])
    intents.to_csv(out_dir / "intents.csv", index=False)
    print(groups.groupby(["hardware", "scenario", "planner_level"])[["intents_submitted", "admitted", "satisfied", "violated", "failed"]].sum().to_string())
    print(intents.groupby(["hardware", "scenario", "planner_level", "group_role"]).agg(
        status=("final_status", lambda s: "/".join(f"{k}:{v}" for k, v in s.value_counts().items())),
        delivered=("delivered_pairs", "mean"), fidelity=("average_fidelity", "mean"),
    ).round(4).to_string())


CAMPAIGNS = {
    "r01": r01_baselines, "r02": r02_routing, "r03": r03_purification, "r04": r04_planners, "r04b": r04b_l4,
    "r05": r05_oracle, "r06": r06_reconciliation, "r07": r07_overhead, "r08": r08_resource_semantics,
    "r09": r09_multi_intent,
}
DEFAULT_SEEDS = {"r01": 20, "r02": 20, "r03": 20, "r04": 10, "r04b": 10, "r05": 0, "r06": 20, "r07": 20, "r08": 20, "r09": 10}
ALL_ORDER = ["r02", "r03", "r08", "r04", "r04b", "r05", "r06", "r09", "r01", "r07"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("campaign", choices=[*CAMPAIGNS, "all"])
    parser.add_argument("--seeds", type=int, default=None, help="number of seeds (default: per-campaign)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    names = ALL_ORDER if args.campaign == "all" else [args.campaign]
    requested_seeds = args.seeds
    for name in names:
        args.seeds = requested_seeds if requested_seeds is not None else DEFAULT_SEEDS[name]
        t0 = time.perf_counter()
        print(f"\n===== {name} (seeds={args.seeds}, workers={args.workers}, out={args.out}) =====", flush=True)
        CAMPAIGNS[name](args)
        print(f"===== {name} done in {time.perf_counter() - t0:.0f}s =====", flush=True)


if __name__ == "__main__":
    main()
