# Planner-family study - Checkpoint 1 (after L2, campaign P01)

Data: `results/planner_study/raw/P01_l1_l2_purification_{three_node,four_node}/
trials.csv` (320 trials each, 640 total, 0 failures), processed by
`scripts/analyze_p01_l1_l2.py` into
`results/planner_study/processed/P01_l1_l2_*.csv`, figures by
`scripts/generate_p01_figures.py` into `results/planner_study/figures/`.
Both campaigns ran to completion with **zero errors** (`errors.jsonl`
absent from four-node's output, empty for three-node).

## 1. False rejection: L1 vs. L2

| Topology | L1 overall rejection rate | L2 overall rejection rate |
|---|---:|---:|
| Three-node chain | 62.5% (5/8 thresholds, 100/160 trials) | **0%** (0/160 trials) |
| Four-node chain | 100% (8/8 thresholds, 160/160 trials) | 50% (80/160 trials) |

**Three-node chain: full resolution.** At every threshold L1 rejects
(`min_fidelity` 0.73-0.75), L2 reaches SATISFIED in **100% of paired,
same-seed trials** (20/20 at each of the 5 thresholds - see
`P01_l1_l2_false_rejection_resolution.csv`). This is the exact topology
and threshold range where the ICC 2027 manuscript's 100%-false-rejection
finding (240/240 oracle-tested rejections confirmed satisfiable,
`docs/false_rejection_root_cause.md`) was established - P01 is a direct,
on-topology confirmation that modeling iterative purification (not just
one round) closes that gap in practice, not only in the oracle's
retrospective analysis.

**Four-node chain: no resolution, a different failure mode instead.**
L2's resolution rate among L1's rejections is **0%** at every threshold
(`P01_l1_l2_false_rejection_resolution.csv`). L2 does stop REJECTING at
`min_fidelity` 0.65-0.73 (down from L1's 100%), but every one of those
newly-accepted trials comes back **VIOLATED**, not SATISFIED - see
section 3.

## 2. Fidelity-estimation error

Where a fidelity estimate exists (SATISFIED/VIOLATED trials with
`delivered_pairs > 0`), L2's estimate is **effectively exact**: mean
absolute error 2.22e-17 on the three-node chain (floating-point zero) and
0 or -0.029 on the four-node chain's two lowest thresholds where any pairs
were delivered at all. This is expected, not a coincidence: both
`three_node_1_repeater` and `linear_chain_2_repeaters` are uniform-fidelity
topologies with a single swap path, so `ConservativeMinEstimator`'s
per-hop model combined with repeated `BBPSSWCircuit.improved_fidelity`
application matches SeQUeNCe's real purification fidelity update exactly
- L2 does not need to guess at variance the real simulator doesn't have
here. This is a favorable case for the analytical model, not evidence it
generalizes to heterogeneous topologies (untested here - see
`docs/planner_threats_to_validity.md`).

## 3. Rounds estimated and the four-node chain's real cost

L2's `IterativeAnalyticalPurification` (default `max_rounds=8`,
`max_pair_cost=None`, unbounded) reaches:

- Three-node chain: 2 rounds resolve the entire 0.73-0.75 range
  (swap-only fidelity 0.686375 -> round 1 = 0.7202522 -> round 2 =
  0.7572267, comfortably above 0.75).
- Four-node chain: swap-only fidelity is much lower (0.5542478, more
  swap-degradation factors), so more rounds are needed for the same
  targets - 6 rounds reach only 0.6653 (min_fidelity 0.65), and even 8
  rounds (the cap) reach only ~0.7315, short of `min_fidelity` >= 0.735,
  which is why L2 still REJECTS there (matching the observed 50% overall
  four-node rejection rate: 4 of 8 thresholds, 0.735-0.75).

At `min_fidelity` 0.65-0.73 on the four-node chain, L2 accepts (does not
reject) but the real trial delivers **0-1 pairs** against the intent's
`min_delivered_pairs=10` goal, hence VIOLATED. Root cause:
`cumulative_pair_cost` grows as `2^rounds` (up to 64 pairs at round 6),
and `IterativeAnalyticalPurification` never checks this projected cost
against the intent's actual `reserved_memory_slots`/`duration_s` - the
`max_pair_cost` constructor parameter exists precisely to bound this, but
P01 ran with the class default (unbounded), which is itself the honest
default behavior worth reporting: **an unconstrained iterative
purification estimate can accept plans the real reservation's resources
cannot actually sustain.**

## 4. Planning cost

Planning wall time is sub-millisecond for both L1 and L2 on both
topologies (0.0006-0.0010 s mean per trial, `P01_l1_l2_comparison.csv`) -
no meaningfully higher analytical planning cost from iterating the
purification formula up to 8 times versus L1's single application, at
this topology scale. This is expected: `BBPSSWCircuit.improved_fidelity`
is a closed-form scalar formula, and even 8 iterations of it are
negligible next to the actual SeQUeNCe simulation's wall time (which
`planning_wall_time_s` does not include - see
`experiments.runner.execute_trial`'s separate `simulation_wall_time_s`
field). L2's real cost is not in planning time; it is in the
resource/delivery mismatch described in section 3.

## 5. Regressions

612/612 pre-existing tests confirmed passing before this study began
(`docs/planner_study_baseline.md`); 53 new tests added
(`tests/planning/planners/`, `tests/experiments/planner_study/`), all
passing; the one production-code change to existing files
(`experiments/sweeps.py`'s `PURIFICATION_POLICIES` dict gaining one
additive entry) was re-verified against the full existing suite
(347 `-m unit` tests, then the complete 612-test suite) with zero
regressions. `results/raw/F0*`/`results/processed/F0*` confirmed
byte-identical (`git status` clean, `scripts/audit_final_results.py`
unchanged PASS/WARN pattern) throughout.

## 6. Conclusion: the cause of the 240 false negatives, and what L2 does about it

The ICC 2027 manuscript's central finding - a 100% false-rejection rate
among 240 oracle-tested rejections on `three_node_1_repeater` - is caused
by L1's one-analytical-round purification ceiling
(`docs/false_rejection_root_cause.md`), not topology heterogeneity (the
topology is uniform). **P01 confirms this causal account directly**: on
the exact same topology, replacing the one-round estimate with an
iterative one (L2) eliminates 100% of the false rejections in the
densified threshold range, with an essentially exact fidelity estimate.

This does NOT mean "L2 is simply better than L1" as a general claim. On a
second, structurally similar but lower-starting-fidelity topology
(four-node chain, also the exact topology of the manuscript's
"fully-rejected, never oracle-tested" secondary finding), L2 eliminates
rejections at the cost of introducing a NEW failure mode (VIOLATED via
pair-cost/resource mismatch) that L1 never exhibits, because L1's pair
cost is trivially bounded (at most 2, one round) while L2's is not
resource-aware by default. **The honest, checkpoint-1-level conclusion
is: increasing planner fidelity from L1 to L2 fixes the specific,
diagnosed cause of the manuscript's false-rejection finding on the
topology where it was diagnosed, but is not a universal improvement - it
trades one planner limitation for a different, topology-dependent one,
exactly the kind of result this study exists to measure rather than
assume.**

## Next steps (pending review, not yet started)

- Bound `max_pair_cost` to the intent's actual `reserved_memory_slots` in
  a follow-up P01 variant, to check whether a resource-aware L2 avoids
  the four-node VIOLATED outcome (by rejecting those cells instead,
  which would at least match L1's honesty about infeasibility, or by
  finding a genuinely deliverable plan).
- L3 (probabilistic) is the natural next milestone per the mandated order
  (M5-M6) - not started, per the explicit instruction not to implement
  L3/L4/L5 before this checkpoint.
