# Planner comparison methodology (P01 scope)

This document covers ONLY the methodology P01 (M4, checkpoint 1) actually
uses to compare L1 and L2. The full L1-L5 comparison methodology (paired
statistical tests across every level, Holm correction, effect sizes,
regret scores) is planned for P09 and will get its own, broader version of
this document once more than two planner levels exist to compare - see
`docs/planner_threats_to_validity.md` for why applying that full apparatus
to a two-level comparison would be premature.

## Design

Same-seed, same-topology, same-intent paired comparison: for a given
`(topology, min_fidelity, seed)` cell, the exact same physical trial
(elementary-generation draws, everything downstream of the random seed)
is run once under L1 (`purification_policy=automatic`) and once under L2
(`purification_policy=iterative_analytical`) - the ONLY thing that differs
between the two rows is which purification strategy the planner used.
This isolates the planner-level effect from any other source of variation.

## Metrics computed (`scripts/analyze_p01_l1_l2.py`)

1. **Per-cell summary** (`per_cell_summary`): satisfaction rate, rejection
   rate, mean absolute fidelity-estimation error, mean planning wall time
   - grouped by `(topology, planner_level, min_fidelity)`.
2. **False-rejection resolution rate** (`false_rejections_eliminated`): for
   every `(min_fidelity, seed)` cell where L1's `final_status ==
   "REJECTED"`, what fraction of the matching L2 cell (same seed) reached
   `"SATISFIED"`? This is a direct, paired, same-seed check - not an
   oracle re-simulation - and is the P01-specific operationalization of
   "did increasing planner fidelity fix the false rejection".
3. **Overall rejection rate** (`P01_l1_l2_overall_summary.json`): aggregated
   across all cells, per topology and level - the headline numbers for
   the checkpoint-1 report.

## What this methodology deliberately does NOT do (yet)

- No paired t-test/Wilcoxon/Holm correction - only rates and counts.
  Two conditions (L1, L2) with dramatically different rejection patterns
  by design (that is the entire point of P01) make a significance test
  largely uninformative at this stage; the effect P01 demonstrates is
  visible directly in the rates without needing an inferential test to
  establish it.
- No regret/utility scoring (planner-study brief section 25) - regret
  requires a defined utility function balancing satisfaction, delivery,
  fidelity, and cost, which is introduced at P11 once more planner levels
  exist to meaningfully rank.
- No cost-accuracy Pareto frontier (P11) - only two points (L1, L2) do not
  make a frontier.

These are scope limits appropriate to a two-level, single-milestone
checkpoint, not omissions - see `docs/planner_study_findings_checkpoint1.md`
for what IS concluded from this data.
