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

## P02: threshold selection protocol (L3 admission threshold)

Seeds 0-9 = validation (choose the admission threshold here, by lowest
combined false-feasibility + false-rejection rate), seeds 10-19 = test
(report final metrics here, untouched until the threshold is fixed) -
`scripts/analyze_p02.py`. L3 is collected once with
`admission_threshold=0.0` (always deploys the best candidate whenever any
route is feasible with non-zero probability), so every trial's REAL
outcome is known regardless of what a stricter threshold would have
decided; a candidate threshold's counterfactual admission decision is
then computed post-hoc (admit using the real recorded outcome if
`predicted_satisfaction_probability >= threshold`, else REJECTED) - this
avoids needing four separate simulation campaigns for what is really a
decision rule applied to one recorded probability estimate.

## P03: disclosed scope reduction

The planner-study brief asks for L4's K in {5, 10, 20, 30} across
multiple parameter combinations. Each L4 planning call costs K+1 real
SeQUeNCe simulations (~5-9s each on this hardware) - K=30 alone costs
several minutes PER TRIAL. `scripts/run_p03_l4_cost.py` runs K in
{3, 5, 10} across 2 combinations (favorable, resource-marginal) x 10
seeds - a real, disclosed reduction given this session's wall-clock
budget, not a silent substitution. Extending to the full requested grid
is mechanical (edit `K_VALUES`/`COMBINATIONS` in that script) given more
wall-clock budget - see docs/planner_study_findings_checkpoint2.md for
the exact numbers this reduced run produced.
