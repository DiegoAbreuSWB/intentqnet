# Planner-family study - Checkpoint 2 (after L3/L4, campaigns P02/P03)

Data: `results/planner_study/raw/P02_l1_l2_l3/trials.csv` (360 trials, 0
failures, complete), `results/planner_study/raw/P03_l4_cost/trials.csv`
(60 trials, 0 failures, 0 duplicates, complete - disclosed reduced scope,
see section 3). Processed by `scripts/analyze_p02.py` /
`scripts/analyze_p03_l4_cost.py` into `results/planner_study/processed/
P02_*` / `P03_*`, figures by `scripts/generate_p02_figures.py` /
`generate_p03_figures.py`.

This checkpoint separates three distinct discoveries, each with its own
honest framing - not a single "L3 and L4 are done" summary.

## Discovery A - limitation of fidelity-only iterative planning (L2)

L2 resolves the one-round purification ceiling (checkpoint 1's central
finding) completely on the three-node chain. But L2 estimates fidelity
reachability only - it has no model of operational pair cost, generation
capacity within the reservation window, or simultaneous memory occupancy.
On the four-node chain, this let L2 accept intents whose fidelity target
is theoretically reachable while the requested delivery
(`min_delivered_pairs`) is operationally infeasible within the window -
accepted, then VIOLATED at execution time. **This is a real, structural
gap in L2, not a parameter-tuning issue.** L2-R (section on M6b, below)
addresses it directly.

## Discovery B - limitation of the current probabilistic model (L3)

L3 did not improve decision quality over L2 in the P02 regime evaluated:
its predicted satisfaction probabilities saturated near 0.0 or 1.0 with
nothing in between, so every candidate admission threshold (0.50, 0.75,
0.90, 0.95) produced identical decisions, and L3 matched L2's
accept/reject pattern exactly while costing ~2.3x more planning time.
Near p=0.0, L3 was **overconfident**: 33.3% of predicted-near-impossible
trials actually succeeded. **This is a limitation of the current
attempt-rate model, not evidence that probabilistic planning is
inherently unhelpful** - the audit below traces the exact source, and
L3-R (built on L2-R's corrected resource model) tests whether a corrected
version adds real value.

## Discovery C - cost of simulation-informed planning (L4)

L4 must be read as a higher-fidelity, higher-cost baseline - **not a
counterfactual oracle**. It uses internal simulation seeds independent of
the operational seed (verified: `_derive_internal_seeds` never accepts an
operational seed, and every derived seed is `>= 500_000_000`, far outside
this project's seed range). In P03's reduced-scope run, L4 achieved
100% satisfaction across all K in {3,5,10} and both scenarios tested,
including the resource-marginal configuration where L2/L3 showed a 33.3%
false-feasibility rate in P02 - real evidence that simulation-informed
decisions can be more accurate than the analytical planners tested so
far, at a wall-clock cost that scales with K (see section 3).

---

## 1. L3 calibration (P02, n=360, complete)

**The headline finding: L3's predictions were bimodal in this campaign's
design** - every trial's `predicted_satisfaction_probability` landed
either near 0.0 (mean 0.0003, n=60) or near 1.0 (mean 0.9999, n=60); no
prediction fell in between. This is a direct consequence of
`docs/l3_probabilistic_model.md`'s assumption 4
(`fidelity_success_probability` is a hard 0/1 gate from L2's deterministic
reachability) combined with this campaign's parameter combinations
creating extreme (not marginal) delivery-probability regimes at each
fidelity level tested.

- **Near-1.0 predictions are well-calibrated**: 60/60 trials predicted
  ~99.99% satisfaction actually reached SATISFIED (100%) - right on the
  calibration diagonal.
- **Near-0.0 predictions are NOT well-calibrated**: 60/60 trials predicted
  ~0.03% satisfaction, but 33.3% of them actually reached SATISFIED -
  L3 was confidently wrong about "essentially impossible" a third of the
  time.
- **Brier score: 0.1667. Expected calibration error: 0.1666.** Both driven
  almost entirely by the near-0 bin's miscalibration (the near-1 bin
  contributes ~0 error).
- A campaign this bimodal cannot be called "well calibrated" from the
  near-1.0 result alone - see section 5 (calibration by region) in
  `docs/planner_calibration.md` for why aggregate metrics alone would
  have hidden this.

**Consequence for threshold selection**: all four candidate thresholds
(0.50, 0.75, 0.90, 0.95) produced IDENTICAL admission decisions in this
campaign - not because L3 is threshold-insensitive in general, but
because this campaign's parameter design never produced a genuinely
marginal (e.g., 40-60%) prediction to discriminate between thresholds.
Selected threshold (lowest combined validation error, though all four
tie): **0.50**. Test-set metrics: false feasibility 0%, false rejection
33.3%, operational satisfaction 50%.

## 2. Admission accuracy: L1 vs. L2 vs. L3 (P02, n=360)

| Planner | n | Rejection rate | False feasibility | Operational satisfaction | Mean planning time (s) |
|---|---:|---:|---:|---:|---:|
| L1 | 120 | 50.0% | 0.0% | 50.0% | 0.00042 |
| L2 | 120 | 0.0% | 33.3% | 66.7% | 0.00046 |
| L3 | 120 | 0.0% | 33.3% | 66.7% | 0.00108 |

**L2 and L3 are identical in decision quality on this campaign.** L3
added a probability estimate but no additional discriminative power over
L2's already-deterministic accept/reject pattern in this regime, at
~2.3x the planning cost (still sub-millisecond in absolute terms).

L1's lower operational satisfaction (50% vs. 66.7%) mirrors checkpoint 1:
L1 is over-conservative (0% false feasibility, but 50% rejection - some
of which checkpoint 1 already showed is false rejection).

## 3. L4 cost (P03, n=60, complete - disclosed reduced scope)

**Scope actually run**: K in {3, 5, 10} (not the requested {5, 10, 20,
30}), 2 combinations (favorable, resource-marginal - reusing P02's own
combinations 1 and 3), 10 seeds, three-node chain only - a real,
disclosed reduction driven by wall-clock cost, documented in
`docs/planner_comparison_methodology.md`. Validated: 60/60 trials, 0
duplicates, 0 failures.

| Scenario | K | n | Satisfaction rate | Rejection rate | Mean planning wall time (s) |
|---|---:|---:|---:|---:|---:|
| Favorable | 3 | 10 | 100% | 0% | 28.71 |
| Favorable | 5 | 10 | 100% | 0% | 77.31 |
| Favorable | 10 | 10 | 100% | 0% | 122.68 |
| Resource-marginal | 3 | 10 | 100% | 0% | 0.73 |
| Resource-marginal | 5 | 10 | 100% | 0% | 1.19 |
| Resource-marginal | 10 | 10 | 100% | 0% | 2.42 |

**Admission accuracy**: 100% satisfaction, 0% false feasibility, 0% false
rejection at every K tested, on both scenarios - including
resource-marginal, where L2/L3 showed 33.3% false feasibility in P02.
This is a real, notable result: L4's internally-simulated decision
correctly avoided every false-positive admission this reduced sample
encountered, at a real cost.

**Stability across K**: satisfaction rate is flat at 100% across K=3,
5, 10 in both scenarios (Panel B, `P03_l4_cost_vs_k.png`) - in this
specific reduced sample, K=3 was already sufficient to reach the same
decision as K=10. This should NOT be read as "K=3 is always enough" -
the sample (10 seeds, 2 combinations) is too small to establish that
generally; it is read as "no evidence K>3 was needed for THESE
combinations," a narrower and more honest claim.

**Cost scales with K, and with the simulated duration itself**: planning
wall time grows from ~29s (K=3) to ~123s (K=10) on the favorable
scenario (`duration_s=0.1`) but only ~0.7s to ~2.4s on the
resource-marginal scenario (`duration_s=0.01`) - confirming that L4's
wall-clock cost is driven by both K and how much simulated time each
internal run has to process, not K alone.

**Confidence interval / early stopping**: `early_stopping=False` for
this run (measuring the full K cost deliberately, per
`docs/l4_simulation_planner.md`) - no early-stopping data to report here;
`tests/planning/planners/test_l4_simulation.py::test_l4_early_stopping_can_stop_before_the_full_k`
confirms the Wilson-CI stopping criterion works correctly in isolation.

**Difference from the offline oracle**: not computed in this reduced
run - `experiments.baselines`' offline oracle re-simulation was not
invoked here; comparing L4's admission decisions against the oracle's
retrospective satisfiability check is left for P02B (section 10 of the
governing brief) if wall-clock budget allows.

## 4. Internal-seed isolation (L4)

Confirmed by `tests/planning/planners/test_l4_simulation.py`:
`_derive_internal_seeds` never accepts an operational seed parameter at
all (its signature is exactly `(intent, route, config, n)`), and every
derived seed is verified `>= INTERNAL_SEED_BASE_OFFSET = 500_000_000` -
far outside this project's operational seed range (0-19) and outside
`RECONCILIATION_SEED_OFFSET = 1_000_000`. Deterministic (same inputs
always produce the same seeds) and route-sensitive (different routes get
different seeds), both directly tested.

## 5. Dataset recommendation for L5 (deferred - not started)

Given P02's bimodal-prediction finding, a dataset built with P02's
parameter design would be heavily class-imbalanced toward extreme cases
and would under-represent the marginal region a learned model most needs.
This recommendation is carried forward into the corrective phase
(L2-R/L3-R/P02B) below, rather than acted on directly - **no dataset
construction or L5 work has started**, per the explicit gate before
section 14 of the governing brief.

## Regressions

612 pre-existing tests (F01-F08/architecture) + 87 planner-study tests
(37 L1/L2/base + 14 L3 + 9 L4 + 16 P01 campaign-config + 11 P02 analysis)
all passing (`pytest tests/planning/ tests/experiments/planner_study/` =
87 passed). F01-F08 and P01 data confirmed untouched throughout M5-M8.

---

**This checkpoint is followed by a corrective phase (M6b-M6e: L2-R, an
L3 attempt-rate audit, L3-R, and P02B) before any L5/dataset work begins
- see `docs/planner_study_findings_checkpoint2b.md` once that phase
completes.**
