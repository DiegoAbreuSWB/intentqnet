# Planner-family study: threats to validity

Scoped to what M1-M4 (L1/L2, campaign P01) actually claims. Will be
extended as L3-L5/hybrid and P02-P12 are added - never backfilled to
claim more than the milestone in question actually measured.

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
