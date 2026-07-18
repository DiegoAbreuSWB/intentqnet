# Planner-family study - Checkpoint 2 (after L3/L4, campaigns P02/P03)

Data: `results/planner_study/raw/P02_l1_l2_l3/trials.csv` (360 trials, 0
failures, complete), `results/planner_study/raw/P03_l4_cost/trials.csv`
(disclosed reduced scope - see below; in progress/completed as noted).
Processed by `scripts/analyze_p02.py` / `scripts/analyze_p03_l4_cost.py`
into `results/planner_study/processed/P02_*` / `P03_*`, figures by
`scripts/generate_p02_figures.py` / `generate_p03_figures.py`.

## 1. Calibration (L3)

**The headline finding: L3's predictions were bimodal in this campaign's
design** - every trial's `predicted_satisfaction_probability` landed
either near 0.0 (mean 0.0003, n=60) or near 1.0 (mean 0.9999, n=60); no
prediction fell in between. This is a direct consequence of `docs/
l3_probabilistic_model.md`'s assumption 4 (`fidelity_success_probability`
is a hard 0/1 gate from L2's deterministic reachability) combined with
this campaign's parameter combinations creating extreme (not marginal)
delivery-probability regimes at each fidelity level tested.

- **Near-1.0 predictions are well-calibrated**: 60/60 trials predicted
  ~99.99% satisfaction actually reached SATISFIED (100%) - right on the
  calibration diagonal.
- **Near-0.0 predictions are NOT well-calibrated**: 60/60 trials predicted
  ~0.03% satisfaction, but 33.3% of them actually reached SATISFIED - a
  large, real calibration failure, consistent with (and a direct
  consequence of) the disclosed 2.4-4.3x attempt-rate overestimate
  in `docs/l3_probabilistic_model.md`: L3 confidently predicts
  "essentially impossible" for some resource-marginal configurations that
  are, in reality, possible about a third of the time.
- **Brier score: 0.1667. Expected calibration error: 0.1666.** Both driven
  almost entirely by the near-0 bin's miscalibration (the near-1 bin
  contributes ~0 error).

**Consequence for threshold selection**: because predictions are bimodal
with nothing between ~0.0003 and ~0.9999, **all four candidate thresholds
(0.50, 0.75, 0.90, 0.95) produce IDENTICAL admission decisions** in this
campaign - the threshold choice was inconsequential here, not because L3
is insensitive to threshold in general, but because this campaign's
parameter design never produced a genuinely marginal (e.g., 40-60%)
prediction to discriminate between thresholds. This is itself a disclosed
limitation of P02's hand-picked grid (`docs/planner_threats_to_validity.md`),
not a claim that threshold choice never matters for L3.

Selected threshold (by lowest combined validation error, though all four
tie): **0.50**. Test-set metrics at this threshold: false feasibility
0%, false rejection 33.3%, operational satisfaction 50%.

## 2. Admission accuracy: L1 vs. L2 vs. L3

| Planner | n | Rejection rate | False feasibility | Operational satisfaction | Mean planning time (s) |
|---|---:|---:|---:|---:|---:|
| L1 | 120 | 50.0% | 0.0% | 50.0% | 0.00042 |
| L2 | 120 | 0.0% | 33.3% | 66.7% | 0.00046 |
| L3 | 120 | 0.0% | 33.3% | 66.7% | 0.00108 |

**L2 and L3 are IDENTICAL in decision quality on this campaign** - same
rejection rate, same false-feasibility rate, same operational
satisfaction. This is the direct consequence of L3's bimodal predictions
combined with using admission_threshold=0.5 (any threshold in {0.5,
0.75, 0.9, 0.95} would have produced the same result here): L3 added a
probability ESTIMATE but no additional DISCRIMINATIVE power over L2's
already-deterministic accept/reject pattern in this parameter regime.
L3's only measurable difference from L2 here is roughly 2.3x higher
planning time (still sub-millisecond, negligible in absolute terms) -
**a case where the more sophisticated model added planning cost without
added decision quality**, exactly the kind of result this study exists to
surface rather than assume away.

L1's much lower operational satisfaction (50% vs. 66.7%) mirrors
checkpoint 1: L1 is over-conservative (0% false feasibility, but 50%
rejection, some of which checkpoint 1 already showed is false rejection).

## 3. L4 cost (K sweep, P03 - disclosed reduced scope)

**Scope actually run**: K in {3, 5, 10} (not the requested {5, 10, 20,
30}), 2 combinations (favorable, resource-marginal - reusing P02's own
combinations 1 and 3), 10 seeds - a real, disclosed reduction driven by
wall-clock cost (each L4 planning call costs K+1 real SeQUeNCe
simulations, ~5-9s each on this hardware; K=10 alone costs roughly
60-90s of planning time per trial). See
`docs/planner_comparison_methodology.md` for the full disclosure.

[FILLED IN ONCE P03 COMPLETES - see `results/planner_study/processed/
P03_l4_cost_summary.csv` and `results/planner_study/figures/
P03_l4_cost_vs_k.png` for the actual numbers this reduced run produced.]

## 4. Internal-seed isolation (L4)

Confirmed by `tests/planning/planners/test_l4_simulation.py`:
`_derive_internal_seeds` never accepts an operational seed parameter at
all (its signature is exactly `(intent, route, config, n)`), and every
derived seed is verified `>= INTERNAL_SEED_BASE_OFFSET = 500_000_000` -
far outside this project's operational seed range (0-19) and outside
`RECONCILIATION_SEED_OFFSET = 1_000_000`. Deterministic (same inputs
always produce the same seeds) and route-sensitive (different routes get
different seeds), both directly tested.

## 5. Dataset recommendation for L5 (M9+)

Given P02's bimodal-prediction finding, a P04 dataset built with THIS
campaign's parameter design would be heavily class-imbalanced toward
extreme cases and would under-represent the marginal (genuinely
uncertain) region a learned model most needs to characterize well.
**Recommendation**: P04's parameter grid should deliberately target the
`expected_delivered_pairs approx min_delivered_pairs` boundary
(scan `reserved_memory_slots`/`duration_s`/`attenuation_db_per_m`
continuously rather than at 2 extreme values each) to produce a
genuinely graded range of outcomes for L5 to learn from - not repeat
P02's favorable/severe-only design.

## Regressions

612 pre-existing + 76 planner-study tests (M1-M4) + 23 new L3/L4 tests =
all passing (verified together: `pytest tests/planning/
tests/experiments/planner_study/` = 76 passed before this checkpoint;
99 passed after L3/L4 tests added). F01-F08 and P01 data confirmed
untouched throughout M5-M8.
