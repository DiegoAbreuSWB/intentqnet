# Planner-family study: threats to validity

Scoped to what has actually been run at each point in this document's
history (M1-M4/P01, extended below for M5-M8/P02-P03) - never backfilled
to claim more than the milestone in question actually measured.

## Internal validity

- **Simulator-derived labels**: every `final_status`/`satisfied`/
  `observed_fidelity` value P01 uses comes from a real SeQUeNCe execution
  (`experiments.runner.execute_trial`, unmodified), never computed
  independently - consistent with the project's standing constraint (see
  `docs/architecture.md`).
- **L2's `IterativeAnalyticalPurification` is a fresh object per candidate
  route per `plan()` call** (`l2_iterative.IterativeAnalyticalPlanner.plan`) -
  a correlated-configuration risk would arise if a single instance's
  `last_estimate` were read after evaluating more than one route; this is
  explicitly avoided (see the class docstring) and covered by
  `tests/planning/planners/test_l2_iterative.py`.
- **Same seed, same topology, same intent, only the purification policy
  differs** between L1 and L2 rows in a P01 trial - the paired comparison
  in `scripts/analyze_p01_l1_l2.py::false_rejections_eliminated` relies on
  this, and it holds because both policies are swept as sibling values of
  the same `purification_policy` sweep parameter over the identical base
  scenario/intent/seed grid (`configs/campaigns/planner_study/P01_*.yaml`).
- **No hyperparameter tuning at this milestone**: L2's `max_rounds=8` and
  `max_pair_cost=None` are fixed defaults, not tuned against P01's own
  results - a sensitivity sweep over `max_rounds` is left to a later
  milestone if warranted, not silently tuned to make L2 look better here.

## Construct validity

- **"False rejection eliminated by L2"** is defined here as a DIRECT,
  paired same-seed comparison (L1 REJECTED, L2 reached SATISFIED) - not a
  re-derivation of the ICC manuscript's oracle-based false-rejection-rate
  definition (`results/processed/F04_planner_vs_operation/gap_metrics.json`).
  Both are valid, complementary constructs; P01's is arguably a stronger
  claim for the specific L1-vs-L2 question, since L2's own real execution
  IS the ground-truth check, not a separate oracle re-simulation. Do not
  conflate the two false-rejection numbers when reporting.
- **"Planning cost"** (`planning_wall_time_s` / `TrialRecord.planning_time_s`)
  measures wall-clock time for one `plan()` call on this specific hardware/
  process - it is a relative comparison between L1 and L2 in the same run,
  not an absolute claim about production planning latency.

## External validity

- Two topologies only (three-node, four-node chain), uniform physical
  parameters, matching F03 exactly by design - conclusions here are
  scoped to "the topology/threshold range where the ICC manuscript's
  false-rejection finding was demonstrated," not a claim that L2 resolves
  false rejections in general topologies or fidelity ranges (P02+ broadens
  this).
- SeQUeNCe-specific: as with the rest of this project, no claim is made
  about physical hardware.

## Statistical validity

- P01 at checkpoint 1 reports per-cell rates and paired same-seed
  resolution rates over n=20 seeds - it does NOT yet apply the full
  paired-test/Holm-correction/effect-size machinery
  `experiments.statistical_analysis` provides for F01-F08 (planner-study
  brief section 24); that level of statistical rigor is planned for P09
  (the full L1-L5 comparison), once more than two conditions exist to
  correct across. Reporting only rates/counts at checkpoint 1 is a
  deliberate, disclosed scope limit, not an oversight.

## M5-M8 additions (L3, L4, P02, P03)

### Internal validity

- **L3's probability model has a known, disclosed calibration gap**: the
  attempt-rate assumption over-predicts by roughly 2.4-4.3x against real
  F02 campaign data (`docs/l3_probabilistic_model.md`). This constant was
  deliberately NOT tuned to close that gap before P02 measured it - doing
  so would be circular (fitting the model to the data used to validate
  it). P02's Brier score/ECE numbers should be read WITH this disclosed
  gap in mind, not as an independent, surprising discovery.
- **L3's `fidelity_success_probability` is 0/1, reusing L2's deterministic
  reachability**, not an independently-derived probability (see
  `docs/l3_probabilistic_model.md`, assumption 4) - if P02's calibration
  numbers look good, part of the credit belongs to L2's already-validated
  (checkpoint 1) fidelity estimate, not to a novel L3 contribution on the
  fidelity axis specifically.
- **L4's internal simulation seeds are hash-derived from (intent id,
  route, requirements, K)**, verified far outside the range of realistic
  operational seeds and verified deterministic
  (`tests/planning/planners/test_l4_simulation.py`) - never the
  operational seed.
- **P02's admission-threshold sweep is computed post-hoc from ONE
  campaign run** (`admission_threshold=0.0` at collection time), not four
  separate simulation passes - valid because the recorded outcome at
  threshold=0 already reflects what deployment would have produced; a
  stricter threshold only changes whether that recorded outcome is used
  or replaced with REJECTED, never a different simulated outcome.
- **P03's K sweep uses only 2 of the 6 combinations tested in P02**, and
  only K in {3,5,10} rather than the requested {5,10,20,30} - a real,
  disclosed reduction driven by wall-clock cost (each L4 planning call
  costs K+1 real simulations), not a silent substitution. See
  `docs/planner_comparison_methodology.md`.

### External validity

- P02/P03 still use only the three-node chain (not the four-node chain
  that exposed L2's resource-mismatch failure mode at checkpoint 1) -
  whether L3/L4 handle that failure mode any better is untested here.
- P02's 6 hand-picked parameter combinations are NOT a factorial design
  and were chosen specifically to span favorable/marginal/severe delivery
  conditions (deliberately, to stress L3's calibration) - they are not a
  representative sample of "typical" configurations, so aggregate rates
  across all 6 should not be read as "expected real-world performance."

### Statistical validity

- P02's threshold selection uses a simple lowest-combined-error rule on
  10 validation seeds per combination - not a formal hyperparameter
  search with cross-validation folds; with only 6 combinations x 10
  validation seeds, this is a modest sample for choosing among 4
  candidate thresholds, and the selected threshold's stability across a
  different validation split is not verified here.
