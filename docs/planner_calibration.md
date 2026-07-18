# Planner calibration (L3, checkpoint 2)

## Metrics computed (`scripts/analyze_p02.py`)

- **Brier score**: mean squared error between `predicted_satisfaction_
  probability` and the actual binary outcome (SATISFIED=1, else 0), over
  every L3 trial with a defined prediction. Lower is better; 0 is perfect,
  0.25 is what a constant `p=0.5` predictor scores against a 50/50 outcome
  split.
- **Calibration curve**: L3 trials binned by predicted probability (5
  bins over [0,1]); each bin's mean predicted probability plotted against
  its actual satisfaction rate. A well-calibrated model's points fall on
  the `y = x` diagonal.
- **Expected calibration error (ECE)**: the bin-size-weighted mean
  absolute gap between predicted and actual rate across all bins - a
  single-number summary of the calibration curve.
- **False feasibility / false rejection** (per candidate admission
  threshold): see `docs/planner_comparison_methodology.md`'s
  counterfactual-threshold protocol - computed post-hoc from one L3
  campaign run (`admission_threshold=0.0` at data-collection time), not
  four separate simulation passes.

## Threshold selection (never from the test set)

Candidate thresholds {0.50, 0.75, 0.90, 0.95} are each scored on
VALIDATION seeds only (0-9); the threshold with the lowest combined
false-feasibility + false-rejection rate is selected; final metrics are
then reported on TEST seeds (10-19), untouched until the threshold is
fixed. This directly implements the planner-study brief's explicit
"não escolher o threshold final a partir do conjunto de teste" /
"calibrar apenas no conjunto de validação" requirement, even though L3's
underlying probability model is analytical (not learned) - the THRESHOLD
choice is still a decision made from data, so the same discipline applies.

## What "good calibration" would and would not show

A low Brier score / low ECE would mean: when L3 says "70% chance of
satisfaction," roughly 70% of such trials really are satisfied - useful
for setting an admission threshold with predictable behavior. It would
NOT mean the underlying physical model (Poisson delivered-pairs,
independent-hop raw-pair probability, etc. - see
`docs/l3_probabilistic_model.md`) is individually accurate; a
miscalibrated component can still produce well-calibrated PROBABILITIES
if errors happen to cancel in a way that preserves rank-ordering and
scale on the SPECIFIC parameter ranges tested. `docs/l3_probabilistic_model.md`
already discloses one such known gap (the attempt-rate model over-predicts
by 2.4-4.3x on F02 data) - P02's calibration numbers should be read
alongside that disclosure, not as an independent confirmation the whole
model is physically exact.

## Results

See `docs/planner_study_findings_checkpoint2.md` for the actual P02
numbers produced by this session's run.
