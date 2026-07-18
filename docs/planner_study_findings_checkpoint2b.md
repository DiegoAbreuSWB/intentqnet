# Planner-family study - Checkpoint 2B (resource-aware planner correction)

Corrective phase after checkpoint 2 (M6b-M6e): L2-R, the L3 attempt-rate
audit, L3-R, and P02B. Data: `results/planner_study/raw/P02b_resource_aware_planners/trials.csv`
(1200 trials, 0 duplicates, 0 unexpected failures - 80 trials recorded
as the new, disclosed `SIMULATION_ERROR` status, see M6e's commit
message), processed by `scripts/analyze_p02b.py` into
`results/planner_study/processed/P02b_*`, figures by
`scripts/generate_p02b_figures.py`.

Governing instruction, honored throughout: **do not force conclusions**.
Several results below are genuinely disappointing relative to what the
corrective work hoped to achieve, and are reported as such.

---

## A. P01 recap (L1 vs. L2, three-node, four-node)

Unchanged from checkpoint 1 (`docs/planner_study_findings_checkpoint1.md`),
carried forward as background, not re-run:

| Topology | L1 rejection rate | L2 rejection rate | L2's real cost |
|---|---:|---:|---|
| Three-node chain | 62.5% | 0% | None observed - full resolution, exact fidelity estimate |
| Four-node chain | 100% | 50% | Remaining "accepted" trials VIOLATE (0-1 delivered pairs vs. `min_delivered_pairs=10`) |

This is Discovery A's origin: L2 fixes the one-round fidelity ceiling but
has no resource model, so on the four-node chain it converts REJECTED
into VIOLATED rather than into a genuine SATISFIED.

## B. L2-R (resource model, effect on false feasibility/rejection)

Definition and resource model: `docs/l2_resource_aware_model.md`. Three
explicitly separate resources (peak simultaneous memory occupancy,
cumulative raw-pair consumption via the audited `2**rounds` formula,
generation capacity within the reservation window), five specific
rejection reasons, and a conservative attempt-rate correction
(`ATTEMPT_RATE_CONSERVATIVE_FACTOR=7.5`, from the M6c audit).

**P02B result (n=240 per planner, paired across 4 topologies x 6
combinations x 10 seeds):**

| Planner | Rejection rate | False feasibility rate | Operational satisfaction | Rejected-but-oracle-satisfiable |
|---|---:|---:|---:|---:|
| L1 | 62.5% | 60.0% | 15.0% | 0.0% |
| L2 | 33.3% | 77.5% | 15.0% | 0.0% |
| **L2-R** | **79.2%** | **0.0%** | **20.8%** | **8.4%** |

L2-R **eliminates false feasibility entirely** in this campaign (0% vs.
L2's 77.5%, vs. L1's 60.0%) - the core problem it was built to fix. This
comes at a real, disclosed cost: L2-R's rejection rate (79.2%) is far
higher than L1's or L2's, and 8.4% of its rejections were, per the
oracle proxy, actually satisfiable by some other planner in the family -
a genuine, non-zero false-rejection cost, not a free win. L2-R also
**severely underpredicts delivered pairs** where it does admit a plan
(mean predicted/observed ratio **0.25**, i.e. it predicts roughly a
quarter of what was actually delivered, MAE 172.6 pairs, 100%
underprediction rate) - the conservative correction that removed false
feasibility is conservative enough to make L2-R's own delivery estimate
unreliable as a quantitative forecast, useful only as a
feasible/infeasible gate at this stage.

**Conclusion for L2-R**: it converts checkpoint 1's specific four-node
failure mode (accept-then-VIOLATE) into a much more conservative
accept/reject boundary that never falsely admits in this campaign, but
does so by being quantitatively wrong about capacity (by a factor of
~4x) in the safe direction. This is not the same as "L2-R is correct" -
see Discovery-A-continued in section F.

## C. L3 attempt-rate audit (cause, magnitude, validity)

Full report: `docs/l3_attempt_rate_audit.md` (also summarized in the
mid-study intermediate report already delivered). Exact source: the
original model assumed a 1-round-trip attempt cycle
(`attempt_rate = reserved_memory_slots / (2 * classical_delay_s)`);
fitting against 200 frozen F02+F03 trials found the best-fitting
round-trip multiplier is **~7.32**, not 2 - a **3.66x average
overestimate**, present across every topology and hop count tested
(2.88x-4.22x range), most consistent with Barret-Kok's real 3-round
classical-coordination protocol needing more overhead than the original
model assumed. **The original probability model does not remain valid as
parameterized** - the attempt-rate bias propagates directly into
`expected_delivered_pairs`, `delivery_success_probability`, and
`satisfaction_probability`. Whether correcting it would improve or worsen
Discovery B's near-zero miscalibration was explicitly left open by the
audit - **section D answers this empirically.**

## D. L3-R (calibration, threshold sensitivity, delivery prediction, cost)

Definition: `docs/l3_resource_aware_model.md`. Reuses L3-original's
Poisson approximation family and L2-R's deterministic gates, with the
attempt-rate term corrected by the same `ATTEMPT_RATE_CONSERVATIVE_FACTOR=7.5`
audited in M6c - the only change relative to L3-original, verified by a
regression test to be exactly attributable (`expected_delivered_pairs`
scales by exactly 1/7.5).

**Delivery-pairs prediction (n=200 each, simulated trials only):**

| Planner | MAE | Mean predicted/observed ratio | Underprediction rate |
|---|---:|---:|---:|
| L3-original | 85.8 | **18.9x** (severe overprediction) | 28.5% |
| **L3-R** | **46.4** | **2.5x** (still overpredicts, far less severely) | 58.5% |

The attempt-rate correction **did fix the delivery-prediction magnitude
problem** - L3-R's overprediction ratio (2.5x) is almost exactly
L3-original's (18.9x) divided by the audited correction factor (7.5),
confirming the change is doing exactly what it was designed to do,
nothing else.

**Calibration by region (the actual test of whether this helped):**

| Planner | Brier score | Expected calibration error | p<0.1 empirical rate | p>=0.9 empirical rate |
|---|---:|---:|---:|---:|
| L3-original | **0.0575** | **0.0541** | 5.6% (n=180) | 93.3% (n=60) |
| **L3-R** | **0.0684** | **0.0751** | 8.4% (n=190) | 100.0% (n=40) |

**The attempt-rate correction did NOT improve overall calibration in
this campaign - Brier score and ECE both got slightly WORSE, and the
near-zero bin's miscalibration got slightly WORSE too (5.6% -> 8.4%
empirical success at predicted probabilities near 0), not better.** This
directly answers the open question the M6c audit deliberately left
unresolved, and answers it in the less convenient direction: making the
model more conservative (lower attempt rate -> lower predicted
probabilities generally) did not fix the cases where "near-impossible"
predictions still sometimes succeed - if anything, pushing predictions
further toward zero gave those same successful outcomes even less
credit. **This is a real, disclosed negative result for the specific
correction tried, not evidence the underlying audit was wrong** - the
audit's attempt-rate fit itself is not in question (it is a clean fit to
real F02/F03 data); what this shows is that attempt-rate bias is not the
(or not the only) cause of the near-zero miscalibration. A residual,
unidentified source of near-zero overconfidence remains.

Three of five calibration regions (0.1-0.3, 0.3-0.7, 0.7-0.9 for
L3-original; 0.1-0.3, 0.3-0.7 for L3-R) are **empty** - both planners
remain overwhelmingly bimodal even under P02B's graded parameter design,
though L3-R does place a small amount of mass (10/240 trials) into the
previously-always-empty 0.7-0.9 region.

**Threshold sensitivity:** L3-original still produces **identical**
admission decisions at every one of the four candidate thresholds
(0.50/0.75/0.90/0.95) - still fully saturated. L3-R produces **2**
distinct admission rates across the same four thresholds (a change
between 0.75 and 0.90) - a small, real improvement in threshold
sensitivity, but still far from the smooth response a well-calibrated
graded probability would produce.

**Cost:** L3-R's simulation-execution outcomes are dramatically less
volatile than L3-original's: L3-original's mean real simulation wall
time is 205.5s, driven almost entirely by **one four-node outlier trial
that took ~48723s (~13.5 hours)**, evidently a real BBPSSW retry storm
triggered by an overoptimistic admission (median is 0.53s - the mean is
not representative). L3-R's mean (2.37s) and median (0.55s) are close
together - no comparable outlier was observed, consistent with L3-R's
more conservative admissions avoiding the plans that trigger this
failure mode. Planning cost itself (not simulation) is sub-millisecond
for both (~2ms), a negligible difference.

**McNemar paired comparison:** in the subset of paired trials where both
planners have a defined `satisfied` outcome, L2-R, L3-original, and L3-R
are **statistically indistinguishable from each other** (all three
pairwise comparisons: b=0, c=0, p=1.0) - in this campaign, the
probabilistic layer (L3/L3-R) never produced a different ADMIT/REJECT
decision than L2-R's deterministic gates did, in the cases where a
direct comparison was possible. L1 and L2 are also statistically
identical to each other (b=0, c=0, p=1.0), but all of L2-R/L3/L3-R differ
significantly from L1/L2 (p<1e-5 in every case, always in L2-R/L3/L3-R's
favor - c>0, b=0).

## E. L4 reference (quality/cost, not re-simulated)

Reused from checkpoint 2 / P03 (`results/planner_study/raw/P03_l4_cost/`,
60 trials, disclosed reduced scope K in {3,5,10}, 2 combinations, 10
seeds, three-node chain only) - **not re-run for P02B**, per section 10's
conditional-inclusion guidance.

| Scenario | K | Satisfaction rate | False feasibility | Mean planning wall time (s) |
|---|---:|---:|---:|---:|
| Favorable | 3-10 | 100% | 0% | 28.7-122.7 |
| Resource-marginal | 3-10 | 100% | 0% | 0.7-2.4 |

L4 achieved 100% satisfaction and 0% false feasibility on both scenarios
tested, including the resource-marginal case where P02's L2/L3 showed a
33.3% false-feasibility rate. Read as a **higher-fidelity, higher-cost
baseline, not a counterfactual oracle** - it uses independent internal
seeds (verified, `>= INTERNAL_SEED_BASE_OFFSET=500_000_000`), never the
operational seed. Its cost is bounded and predictable (scales with K and
simulated duration), unlike L3-original's catastrophic-outlier risk
observed in section D.

## F. Recommendation

**Is L2-R sufficient?** Not on its own as a quantitative planner - it
successfully eliminates false feasibility in this campaign (its stated
goal), but its own delivered-pairs estimate is off by a factor of ~4x
(underprediction), and it carries a real false-rejection cost (8.4% of
its rejections were satisfiable). It is a reliable feasible/infeasible
GATE, not yet a reliable quantitative forecaster.

**Does L3-R add value over L2-R?** Limited, and less than hoped. L3-R's
probability estimates carry no admission-decision information beyond
what L2-R's deterministic gates already produce in this campaign
(McNemar: statistically identical decisions), its delivery-magnitude
prediction is better than L3-original's but still biased 2.5x, and its
overall calibration did not improve (and slightly worsened) relative to
L3-original. Its one clear, real advantage over L3-original is
avoiding the catastrophic-cost outlier risk (section D) - a genuine,
if narrower, value than "better calibrated probabilities."

**Is L4 necessary as a fallback?** On present evidence, yes for cases the
analytical family (L1/L2/L2-R/L3/L3-R) marks as uncertain or marginal:
it is the only planner level in this study with a clean, positive
decision-quality record (0% false feasibility, 100% satisfaction) at a
real but bounded, predictable cost - unlike L3-original's uncontrolled
worst case.

**Is the L5 dataset already reliable? NOT YET (see the blocking checklist
below) - the delivered-pairs prediction structural error (checklist item
5) and the still-largely-bimodal calibration with three empty regions
(checklist items 7/8) are not resolved by this corrective phase.**

---

## Blocking checklist (planner-study brief section 14)

| # | Item | Status |
|---:|---|---|
| 1 | Attempt-rate audit concluded | ✅ Done (M6c) |
| 2 | L2-R implemented | ✅ Done (M6b) |
| 3 | L3-R implemented or formally discarded | ✅ Implemented (M6d) |
| 4 | P02B concluded | ✅ Done (M6e) |
| 5 | Delivered-pairs prediction has no severe structural error | ❌ **Not met** - L2-R underpredicts ~4x, L3-R overpredicts ~2.5x; both are severe by any reasonable bar |
| 6 | Targets/features semantically consistent | ⏸ Not assessed - no dataset design work has started |
| 7 | Marginal topologies produce non-trivial probabilities | ❌ **Not met** - still overwhelmingly bimodal (only 10/240 L3-R trials land outside the two extreme bins) |
| 8 | Calibration bins have sufficient coverage | ❌ **Not met** - 2 of 5 regions remain empty for L3-R, 3 of 5 for L3-original |
| 9 | Training labels don't depend on defective campaigns | ⏸ Not assessed - no dataset built yet |
| 10 | Checkpoint 2B approved | ⏸ Pending (this document) |

## Implementation status

| Component | Status | Commit |
|---|---|---|
| L1 (conservative_one_round) | Preserved, unmodified | (pre-existing) |
| L2 (iterative_analytical) | Preserved, unmodified since checkpoint 1 | `b40a855` |
| L2-R (iterative_resource_aware) | Implemented, tested (13 tests) | `9e93372` |
| L3-original (probabilistic) | Preserved, unmodified since P02 | (M5) |
| L3 attempt-rate audit | Complete | `e9c64ff` |
| L3-R (probabilistic_resource_aware) | Implemented, tested (13 tests) | `d602352` |
| P02B campaign + analysis | Complete, 1200/1200 trials | `c69082e` |
| Checkpoint 2B | This document | (current commit) |

## Main findings (summary)

1. L2-R eliminates false feasibility in this campaign but at the cost of
   a much higher rejection rate and a ~4x delivered-pairs underprediction.
2. The L3 attempt-rate bias is real, precisely measured (~3.66x average,
   best-fit multiplier ~7.32), and correcting it (L3-R) fixed the
   delivery-prediction MAGNITUDE but did not improve, and slightly
   worsened, overall calibration - the near-zero miscalibration has
   another, still-unidentified cause.
3. L2-R, L3-original, and L3-R produce statistically identical admission
   decisions in this campaign (McNemar) - the probabilistic layer adds
   no decision-relevant information beyond L2-R's deterministic gates
   here, only (mixed-quality) probability/magnitude estimates.
4. L3-original carries a real, disclosed catastrophic-cost tail risk (one
   trial: ~13.5 hours of real simulation) that L3-R's more conservative
   admissions avoided in this campaign - a genuine, narrower benefit of
   the correction.
5. L4 remains the only planner level with a clean positive decision-
   quality record in this study, at a real but bounded and predictable
   cost.
6. No planner dominates every axis - exactly the honest, mixed frontier
   the governing brief anticipated as an acceptable outcome, not a result
   to be forced into a single "best planner" conclusion.

## Readiness verdict

**NOT READY** for L5/dataset construction (M9+).

Technical justification: checklist items 5, 7, and 8 are not met. The
delivered-pairs prediction error is not merely imprecise but severely
biased in opposite directions across the two resource-aware planners
(L2-R underpredicts ~4x, L3-R overpredicts ~2.5x) - a dataset built on
either as a feature source would carry that bias directly into any
learned model. Calibration remains overwhelmingly bimodal with multiple
empty probability regions, meaning a learned model trained on this
family's outputs would see almost no genuinely marginal examples to
learn from - precisely the class-imbalance risk flagged as a concern
since checkpoint 2's dataset-recommendation section. Per section 18
("don't force conclusions"), this NOT READY verdict is itself an
acceptable, honest outcome of the corrective phase, not a failure of the
work performed - the corrective phase's job was to test whether L2-R/L3-R
resolved these specific problems, and it did so rigorously, finding a
partial (L2-R's false-feasibility fix, L3-R's magnitude fix) but
incomplete (delivery-bias, calibration) resolution.

**Recommended next step (not started, pending user direction): a further
diagnostic pass on the still-unidentified source of near-zero
overconfidence** (independent of the attempt-rate bias, per section D)
before any dataset construction begins - this is a new, narrower
investigation, not a repeat of the M6c audit.
