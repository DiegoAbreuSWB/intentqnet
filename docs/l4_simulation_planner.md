# L4: simulation-in-the-loop planner

## What it does

For each candidate route, `planning.planners.l4_simulation.
run_internal_simulations` runs K real SeQUeNCe simulations - the exact
same `execution.sequence_executor.SequenceExecutor` every other planner
level's operational deployment eventually uses - on seeds derived from
`(intent.id, route, min_fidelity, reserved_memory_slots, duration_s, K)`,
never the trial's operational seed (`_derive_internal_seeds`, offset by
`INTERNAL_SEED_BASE_OFFSET = 500_000_000` to guarantee no collision with
this project's small operational seeds or reconciliation's own
`RECONCILIATION_SEED_OFFSET = 1_000_000`). Aggregates the K outcomes
(satisfaction rate, mean delivered pairs, fidelity/throughput
distributions) into a `PlannerSimulationSummary`, and admits the
candidate with the highest internally-simulated satisfaction rate that
clears `admission_threshold`.

## Why L4 is not the offline oracle

`experiments.baselines`' offline oracle re-simulates an ALREADY-REJECTED
intent retrospectively, as a post-hoc analysis tool, to check whether the
planner's rejection was correct - it is never a mechanism available at
decision time (docs/false_rejection_root_cause.md; the ICC 2027 manuscript
explicitly states this). L4 is different: it runs its K simulations
BEFORE the operational deployment, as part of planning itself, on its own
internal seeds - a genuinely deployable (if expensive) planning strategy,
not a retrospective check.

## Seed isolation (the mandatory invariant)

L4 must never read `PlanningContext.operational_seed` for its own
simulations. `tests/planning/planners/test_l4_simulation.py` verifies
this two ways: (1) `_derive_internal_seeds`'s signature never accepts an
operational seed at all, and (2) the derived seeds are always far outside
the range of realistic operational seeds (>= `INTERNAL_SEED_BASE_OFFSET`).

## Early stopping

Only stops early on a real statistical criterion: a Wilson confidence
interval (at `early_stopping_confidence`) on the running satisfaction
rate, stopping once its lower bound clears `early_stopping_acceptance_
threshold` (clearly satisfiable) or its upper bound falls below it
(clearly not) - never merely because the first few simulations happened
to agree (planner-study brief, section 7's explicit requirement).
Disabled (`early_stopping=False`) by default so P03 can measure the FULL
cost of K simulations before evaluating what early stopping saves.

## Cost

L4 is, by construction, the most expensive planner level in this study:
K real simulations per candidate route, at planning time, before the
operational trial even runs. On this project's small topologies, one
simulation takes roughly 5-9 seconds of wall time; K=10 against a single
candidate route (the only case this study's topologies present) costs
roughly 50-90 seconds of PLANNING time alone. P03 (M8) measures this
cost/accuracy tradeoff directly, at a necessarily reduced scale given the
wall-clock cost - see docs/planner_study_findings_checkpoint2.md for the
exact scope run and why.

## `parallelism` stays 1 by default

`sequence.utils.metrics` is a process-wide singleton
(docs/sequence_code_analysis.md, section 4.1) that every simulation
resets and reads from - running K internal simulations concurrently in
threads would corrupt each other's metrics collection. `parallelism > 1`
would require per-process isolation (e.g., a process pool, each with its
own Python interpreter and thus its own `metrics` singleton), which is out
of scope for this milestone and left as a documented limitation, not
silently unsafe.
