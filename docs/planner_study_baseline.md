# Planner-family study: frozen baseline (M1)

Recorded before any L2-L5 implementation work, per the planner-study
brief's explicit freeze requirement. Everything below is the state this
study builds on top of, never rewrites.

## Frozen architecture

Commit `cd46233073dd699a2079f554f754feb3dd5c4e4b` (tag
`ibqn-planner-study-baseline-v1`) - the ICC 2027 manuscript commit.
SeQUeNCe commit `1f2680a5b9065e708a7497adc53a95b108029b98` (unchanged).

The IBQN architecture itself (intent lifecycle, assurance,
episode-based reconciliation, SeQUeNCe adapter) is not touched by this
study - see `docs/core_contribution_statement.md` and
`article/provenance.md` for what it already established. This study adds a
**pluggable planner family** underneath the existing `IntentPlanner`
integration point (`experiments.runner.execute_trial` calls
`planning.planner.IntentPlanner.plan()`, which stays the code path every
F01-F08 result and the ICC manuscript's claims are traced to).

## The current (L1) planner, exactly as it exists today

`planning.planner.IntentPlanner`, composed from:

- `planning.routing.{ShortestHopCountRouting,LeastLossRouting,HighestFidelityRouting}` -
  candidate route generation.
- `planning.fidelity_estimation.{ConservativeMinEstimator,SequenceConsistentEstimator}` -
  hop-fidelity model.
- `planning.purification.PurifyUntilTarget` - **exactly one** analytical
  purification round (`BBPSSWCircuit.improved_fidelity` applied once),
  never more, regardless of how close the one-round result is to the
  target.
- `planning.resource_allocation.build_reservations` - memory feasibility.

This study's new `planning.planners.ConservativeOneRoundPlanner` (L1) is a
thin wrapper around this exact object (composition, not reimplementation)
- see `docs/planner_levels.md`.

## Reusable campaigns (never modified by this study)

F01-F08 (`results/raw/F0{1,2,3,5,6,7,8}_*`, `results/processed/F0{1,2,3,4,5,7,8}_*`)
stay exactly as they are. This study's new campaigns live under
`results/planner_study/` (a sibling directory, never nested inside
`results/raw` or `results/processed`) and `configs/campaigns/planner_study/`.

The F03 three-node/four-node chain topologies are reused (not copied) by
reference: `configs/campaigns/planner_study/P01_*.yaml` point at the
exact same physical parameters (`raw_fidelity=0.85`,
`swapping_degradation=0.95`, `attenuation_db_per_m=1e-5`,
`distance_m=1000`) as F03's `three_node_1_repeater`/`linear_chain_2_repeaters`
scenarios, so any behavioral difference P01 finds is attributable to the
planner change alone, not a topology difference.

## Known limitations this study inherits (must remain reproducible)

- **False rejection rate: 1.0** (100%) - all 240 oracle-tested planner
  rejections in the F03 densified range (`three_node_1_repeater`,
  `min_fidelity` 0.70-0.75) were confirmed satisfiable by the offline
  oracle (`results/processed/F04_planner_vs_operation/gap_metrics.json`,
  `docs/false_rejection_root_cause.md`). Root cause: L1's one-round
  purification ceiling (0.7202522030749277) is a hard, deterministic cutoff.
- **False feasibility rate: 0.15** (15%) - `FEASIBLE_BUT_VIOLATED` trials
  out of all trials where the planner said feasible (same gap_metrics.json).
- **Operational success rate: 0.2833** (28.3%) of all 600 F02+F03 trials
  reach SATISFIED.
- **Fidelity prediction error: 0.0219** mean absolute error across all
  600 F02+F03 trials with a defined estimate (same source); per-estimator
  breakdown (F07): `conservative_min` mean abs. error ≈0.073 (max
  ≈0.083), `sequence_consistent` ≈0 (both from
  `results/raw/F07_estimators/trials.csv`).
- **Orchestration overhead**: below 0.31% of trial wall time on average
  across conditions (native SeQUeNCe / static provisioning / IBQN
  instrumented), outlier close to 0.49% (`results/raw/F06_overhead/trials.csv`,
  `article/icc2027_ibqn/main.tex` Sec. VI-E). This study's new planner
  levels are expected to change PLANNING cost (`planning_wall_time_s`),
  never this orchestration-overhead baseline, which is architecture-level,
  not planner-level.

These five numbers are the baseline P01 (and later P02-P12) results are
compared against - any claim that a new planner level "improves" on L1
must be measured relative to them, on the same topologies, never on a
cherry-picked subset.

## Test suite

612/612 tests confirmed passing as of the ICC manuscript freeze
(`article/provenance.md`, `article/test_results_at_freeze.txt`) - 408
non-notebook + 204 notebook tests, the latter's apparent 41 failures in a
16h49m full run traced to Windows `nbclient` kernel-lifecycle exhaustion
over an unusually long sequential run, not a real regression (confirmed
by an isolated 204/204 rerun). This study adds new tests under
`tests/planning/planners/` (and, from M9 onward, `tests/planning/learning/`,
`tests/experiments/planner_study/`) - it does not modify any existing test.

## What "frozen" means operationally for this study

1. `results/raw/F0*`, `results/processed/F0*` - read-only, referenced but
   never written to.
2. `article/` (the ICC 2027 manuscript, already submitted-ready) - not
   touched unless `docs/icc_article_impact_assessment.md` (M18) explicitly
   recommends and the user approves a change.
3. `src/ibqn/planning/{planner,feasibility,fidelity_estimation,purification,
   routing,resource_allocation,swapping}.py` - the existing classes are
   composed (imported, instantiated, passed as strategies), never edited,
   with one narrow exception: `experiments/sweeps.py`'s
   `PURIFICATION_POLICIES` dict gained one new, additive entry
   (`"iterative_analytical"`) so L2 can run through the existing
   `CampaignRunner`/YAML pipeline unchanged - see `docs/planner_levels.md`
   for why this is additive, not a behavior change to `"disabled"`/`"automatic"`.
