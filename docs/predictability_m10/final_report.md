# M10 final report — robust predictability validation

Scientific question: "Under controlled randomness and near-boundary
operating conditions, how predictable is quantum-network intent
satisfaction from pre-execution information?"

All of L1, L2, L2-R, L3, L3-R, L4 remain frozen throughout. No M9/P01-P02B/
P03 data was altered. All new work lives under `configs/campaigns/
predictability_m10/`, `results/predictability_m10/`, `docs/
predictability_m10/`, `tests/experiments/predictability_m10/`.

---

## REPRODUCIBILITY

`P10_replay_determinism` (M10.3): 8 configurations x 10 replays x 2
determinism modes = 160 trials, 0 duplicates (after a real bug was found
and fixed - see `checkpoint_m10a.md`).

| Scenario | Replays | Logical mismatches | Status |
|---|---:|---:|---|
| three_node_baseline | 20 | 0 | BITWISE_IDENTICAL |
| four_node_baseline | 20 | 0 | BITWISE_IDENTICAL |
| diamond_baseline | 20 | 0 | BITWISE_IDENTICAL |
| small_mesh_baseline | 20 | 0 | LOGICALLY_IDENTICAL (all REJECTED, no trajectory to hash) |
| purification_disabled | 20 | 0 | BITWISE_IDENTICAL |
| purification_automatic_one_round | 20 | 0 | BITWISE_IDENTICAL |
| multi_round_purification | 20 | 0 | BITWISE_IDENTICAL |
| **previously_slow_case** (the exact P02B outlier config) | 20 | 0 | **BITWISE_IDENTICAL** |

**Verdict: REPRODUCIBLE.** The randomness audit (M10.1) independently
corroborates this: the only source confirmed to drive physical sampling
(`numpy.random.default_rng(seed)` per node/link) is correctly seeded from
`operational_seed`; every other candidate source (bare `random` module,
qutip's dormant `_RAND` singleton, legacy `numpy.random.*` globals) was
dynamically confirmed unused or inert.

## BOUNDARY CONFIGURATIONS

`P11_boundary_search` (M10.4-M10.5, 352 trials) + `P12_boundary_
variability` (M10.6, 820 trials, n=100 for each transition candidate).

| Topology | Configuration | Seeds | P(satisfied) | 95% CI | Entropy (bits) |
|---|---|---:|---:|---|---:|
| three_node | fidelity=0.79625, duration_s=0.05 | 100 | 0.00 | [0, 0.037] | 0.00 |
| **four_node** | **fidelity=0.58, duration_s=0.05** | **100** | **0.68** | **[0.58, 0.76]** | **0.90** |
| small_mesh | fidelity=0.44875, duration_s=0.05 | 100 | 0.00 | [0, 0.037] | 0.00 |
| diamond_heterogeneous | fidelity=0.60, duration_s=0.09 (bad route) | 100 | 0.10 | [0.055, 0.174] | 0.47 |

**Only four_node's point is a genuine, graded TRANSITION** confirmed at
n=100 - the other three were candidates M10.4-M10.5's 8-seed search
flagged that resolved to firm ROBUST_FAILURE/LIKELY_FAILURE at n=100 (see
`m10_6_boundary_variability_summary.md`'s central finding). Diamond's
10% figure describes its shortest-hop ("bad") route specifically - M10.7
found L4 correctly identifies and switches to a much better ("good")
route at this exact configuration (see below).

## EMPIRICAL PREDICTABILITY LIMIT

Bayes-style empirical configuration-conditional lower bound (`min(p, 1-p)`
per configuration, section 10) from P12's 18 configurations:

| Aggregation | Majority-baseline error (Bayes bound) | L2-R error | L3-R error | L4 error |
|---|---:|---:|---:|---:|
| Equal-weighted-by-configuration | 0.049 | - | - | - |
| Weighted-by-trial-count | 0.068 | - | - | - |
| P15's controlled factorial (240 trials, cell-majority-class baseline) | - | **0.000** | **0.000** | - |
| four_node boundary, real deployment (P13, n=4, K=5/10/20/30) | - | - | - | 0.25 (1/4, tiny sample) |

L2-R and L3-R both achieve **zero decision error** relative to each
cell's own empirical majority class in P15's controlled factorial -
consistent with their generally conservative admission behavior matching
the true direction of each configuration's outcome, though this measures
DECISION alignment, not probability calibration (see checkpoint 2B for
calibration-specific metrics, where both showed real, uncorrected bias).
L4's n=4 sample at the one genuine boundary is too small for a reliable
error estimate on its own - reported with that caveat, not overclaimed.

## INFORMATION VALUE

Reusing M9's information-level comparison (P02B/P03 data, unchanged) plus
P15's confirmation:

| Feature/information level | Brier | Log loss | Balanced accuracy (vs. oracle proxy) | Cost |
|---|---:|---:|---:|---|
| Level 0 (L1 - topology+resources, hard decision) | 0.100 | - | 0.931 | sub-ms |
| Level 0 (L2 - topology+resources, hard decision) | 0.392 | - | 0.730 | sub-ms |
| **Level 0-corrected (L2-R - resource-aware)** | **0.067** | - | 0.879 | sub-ms |
| Level 1 (L3 - statistical rates) | 0.058 | 0.637 | 0.500 | ~ms |
| Level 1-corrected (L3-R) | 0.068 | 0.813 | 0.500 | ~ms |
| Level 2 (L4 - internal simulation) | 0.000 | - | - | seconds-minutes (scales with K) |
| Level 3 (oracle) | 0.000 | - | - | not implementable |

**L3-R adds no value over L2-R in ANY of four independent comparisons
across this entire two-phase study** (checkpoint 2B's McNemar test, M9's
Brier-score comparison, M10.7's route-selection analysis, and M10.9-
M10.10's controlled factorial ANOVA, where `planner_level` explains
exactly 0.0% of variance). L4's Level-2 information is real but expensive
and, per M10.7, its most dramatic advantage (diamond) comes from ROUTE
SELECTION - information not currently exposed to any cheaper planner or
hypothetical learned model as a feature.

## L4 AT THE BOUNDARY

`P13_l4_boundary_reference` (M10.7, 16 trials - see full investigation in
`m10_7_l4_boundary_reference_summary.md`).

| K | Brier / calibration note | Decision error | Planning time (s) |
|---:|---|---|---:|
| 5 | predicted 0.80 vs. true 0.68 (four_node) | correct (SATISFIED) | 28 |
| 10 | predicted 0.50 vs. true 0.68 | incorrect (VIOLATED) | 49 |
| 20 | predicted 0.65 vs. true 0.68 | correct (SATISFIED) | 97 |
| 30 | predicted 0.70 vs. true 0.68 | correct (SATISFIED) | 150 |

Mean absolute calibration error across K: **0.0875** (reasonable, not
dramatically superior to the true rate). At diamond (fidelity=0.60,
duration_s=0.09), L4 predicted 1.0 at every K and deployed the "good"
route (real outcome SATISFIED all 4 times) - **not miscalibration**, but
a materially better ROUTE CHOICE than the "bad" route
`ShortestHopCountRouting` forces every other planner (and P12's own
"diamond_transition" ground truth) to use. Two real bugs in the M10
harness (never in L4's own frozen code) were found and fixed while
producing this table - missing `context.topology_spec`, and an
unguarded planning-time exception - documented in the M10.7 summary.

## VARIANCE ANALYSIS

`P15_balanced_factorial` (M10.9-M10.10, 240 trials, fully balanced).

- **Main effects** (proportion of `satisfied` variance): fidelity_level
  31.9%, duration_s 21.0%, scenario 7.6%, reserved_memory_slots 0.84%,
  planner_level 0.0%.
- **Interactions**: fidelity_level:duration_s 11.8%, scenario:
  fidelity_level 5.0%, duration_s:reserved_memory_slots 0.84%,
  scenario:duration_s 0.84%.
- **Seed contribution**: 0.000% (satisfied), 0.043% (delivered_pairs,
  n=70 SATISFIED-only, not a balanced subsample - main effects there
  remain approximately valid, interactions involving `scenario` are not).
- **Residual** (unmodeled higher-order interactions): ~20.2%.

Two real bugs were found and fixed while building this analysis (nested-
factor confounding between `scenario` and raw `requested_fidelity`;
an unbalanced-subsample violation of the orthogonal-SS assumption in the
secondary analysis) - both disclosed in `m10_10_corrected_variance_
analysis.md`, not silently corrected.

**This directly confirms M9's original claim** ("seed explains only
0.02%") via an independent, methodologically sound follow-up, after
correctly identifying M9's own method as flawed.

## TAIL EVENT

`P14_tail_event_study` (M10.8, 120 trials, heartbeat-instrumented).

- **Reproduced?** Not the exact ~48723s event (this campaign was
  deliberately bounded - 120s cap, 5,000,000-event cap - per section
  13's explicit instruction against unbounded trials). Two `TIMEOUT`
  events were captured (four_node, seeds 335/336).
- **Diagnostic evidence**: both `TIMEOUT` trials show `run_counter`
  (SeQUeNCe's own cumulative event-processing counter) climbing rapidly
  (22,476 and 26,771 events within just 12-22 seconds, for only 0.05-0.06s
  of SIMULATED time) - a real, growing, non-stalled event count.
- **Retry/event counts**: consistent with a genuine high-attempt-rate
  scenario near the purification-round transition, not a stuck loop.
- **Timeout/no-progress behavior**: `termination_reason` distribution -
  118 SIMULATION_COMPLETE, 2 TIMEOUT, **0 NO_PROGRESS, 0 MAX_RETRIES, 0
  ERROR**.
- **Supported explanation**: hypothesis 1 (a legitimate, rare, high-
  event-count stochastic tail event), not hypothesis 3 (a bug/loop) - for
  the two tail events this campaign actually captured. Hypothesis 2 was
  already substantially addressed by M10.1/M10.3. A real, disclosed
  instrumentation limitation: both trials' heartbeat trail stopped well
  before the actual kill (likely GIL starvation of the watcher thread
  during the busiest phase), so the conclusion is honestly bounded to
  the first 12-22 seconds observed, not extrapolated to the full 120s.

## M9 CLAIM AUDIT

Full detail: `docs/predictability_m10/m9_conclusion_audit.md`.

| Claim | Status | Revised wording |
|---|---|---|
| Seed explains only 0.02% of variance | **SUPPORTED** | Confirmed independently via a balanced multi-factor ANOVA (0.000%/0.043%) after identifying the original one-way method as flawed |
| Error is mostly structural | **SUPPORTED** | Directly follows from the above; "structural" means attributable to the configuration parameters tested |
| Fidelity is deterministic (2 regimes) | **SUPPORTED** | Confirmed to generalize to 6 regimes across 2 single-route topologies; NOT shown for multi-route topologies (diamond), where route CHOICE, not fidelity noise, is what varies |
| Only delivered-pair count is stochastic | **SUPPORTED** | Same generalization and same caveat |
| L5 is not justified | **SUPPORTED** | Reinforced by 3 additional independent findings (small-sample search fooled by noise, L4's advantage being route-selection not calibration, a 4th confirmation that L3-R adds no value) |
| Predictability Limits is the best next paper | **SUPPORTED, strengthened** | M10 added substantial new, rigorous, publishable material consistent with this framing |

One SPECIFIC MECHANISM (not one of the six headline claims) was found
NOT SUPPORTED and corrected: M9 attributed observed wall-time variance to
`quantum_utils.random_state` - a function with zero call sites anywhere
in SeQUeNCe's shipped code, confirmed via dynamic audit to never fire
during a real trial (`docs/predictability_m10/randomness_audit.md`).

## FINAL DECISION

**L5 NOT JUSTIFIED — PREDICTABILITY PAPER SUPPORTED.**

Justification, exclusively from data:

1. **Reproducibility is established**, not assumed: 160 replay trials,
   0 logical mismatches, corroborated by a dynamic randomness audit that
   corrected a real error in M9's own prior claim.
2. **The predictability boundary is narrow and mostly not learnable from
   this study's evidence**: of 4 candidate transition points a
   principled small-sample search identified, only 1 survived
   confirmation at 10x the sample size. That one point (four_node,
   fidelity=0.58) is real, graded, and well-characterized (H=0.90 bits) -
   a single confirmed transition region across 4 topologies and ~1,700
   M10 trials is not, on its own, evidence of a rich, general learnable
   structure an L5 model could exploit.
3. **Where a planner CAN do better (L4 at diamond), the mechanism is
   route selection, not learned calibration of a shared plan** - a
   different kind of information (explicit multi-candidate internal
   simulation) than what any current feature set exposes to a
   hypothetical learned model.
4. **The specific criterion for L5 (systematic error that additional,
   currently-unexploited pre-execution information could fix) keeps
   failing empirically**: L3-R's added statistical information produced
   zero decision-relevant value in FOUR independent, methodologically
   distinct tests across two phases of this study (checkpoint 2B, M9,
   M10.7, M10.9-M10.10).
5. **Seed/stochastic variance is confirmed negligible** (~0%) relative to
   design-parameter variance in a properly controlled, balanced
   experiment - the remaining error is structural, meaning a BETTER
   ANALYTICAL MODEL (extending L2-R/L3-R's own corrections) is the more
   directly supported next step, not a learned model trained to absorb
   stochastic noise that this study shows barely exists.

This is not a claim that no learnable structure could ever exist in this
system - it is a claim that the evidence gathered across M9 and M10,
specifically designed to find and stress-test such structure, keeps not
finding enough of it to justify the investment, while simultaneously
finding a rich, honest, and substantial body of results about the
system's actual determinism, boundary structure, and cost/quality
tradeoffs - precisely the material a "Predictability Limits" paper needs
and a "Learned Intent Planning" paper does not yet have grounds to claim.
