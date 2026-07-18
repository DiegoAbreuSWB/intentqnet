# L3-R: resource-aware probabilistic planner

## Relationship to L3-original

**L3-original (`planning.planners.l3_probabilistic.ProbabilisticPlanner`,
`planner_level="L3"`) is preserved byte-for-byte, unmodified.** Its P02
results (`docs/planner_study_findings_checkpoint2.md`, Discovery B) remain
valid as a description of that exact model's behavior and are never
retroactively altered. L3-R is a separate, new planner level
(`planner_level="L3-R"`, `planner_name="probabilistic_resource_aware"`,
`planning.planners.l3_resource_aware.ProbabilisticResourceAwarePlanner`).

## What L3-R changes relative to L3-original

Exactly two things, each independently attributable:

1. **Deterministic gates reused from L2-R, not re-derived.** If L2-R's
   `estimate_resource_aware_plan` finds the plan structurally impossible
   (`memory_feasible=False`, i.e. `INSUFFICIENT_PEAK_MEMORY`) or its
   analytical purification-cost model saturated (`model_limit_hit`, i.e.
   `MODEL_LIMIT_REACHED`), L3-R short-circuits to
   `satisfaction_probability=0.0` immediately. These are structural facts,
   not probabilities to estimate - feeding a saturated or physically
   impossible structural estimate into a Poisson layer would produce a
   number with no meaning.
2. **The attempt-rate correction from the M6c audit.** L3-original's
   `attempt_rate = reserved_memory_slots / (2 * classical_delay_s)` is
   replaced by L2-R's `estimated_generation_rate` (the same naive formula,
   divided by `ATTEMPT_RATE_CONSERVATIVE_FACTOR=7.5` -
   `docs/l3_attempt_rate_audit.md` found the naive formula overestimates
   real attempt rate by ~3.66x on average, best-fit correction ~7.32x).
   L2-R and L3-R share this one constant rather than each tuning an
   independent one.

Everything else - the Poisson delivered-pairs approximation, the
Dur-Briegel-based effective purification pair cost, the 0/1 fidelity-
reachability reuse of L2's deterministic estimate, the independence
assumption between fidelity-success and delivery-success - is carried
over from L3-original UNCHANGED. This is a deliberate choice: introducing
a new stochastic model (binomial/negative-binomial/renewal/Monte-Carlo)
AND correcting the attempt-rate bias in the same pass would make it
impossible to attribute any change in P02B's results to one cause or the
other. `test_l3r_expected_delivered_pairs_matches_l3_original_corrected_
by_the_audited_factor` (`tests/planning/planners/test_l3_resource_aware.py`)
verifies the ratio between L3-R's and L3-original's
`expected_delivered_pairs` equals `ATTEMPT_RATE_CONSERVATIVE_FACTOR`
exactly (up to floating point), confirming this is the ONLY change.

## Why the Poisson family was kept (chosen by validated behavior, not complexity)

The planner-study brief allows analytical approximation, binomial/
negative-binomial approximation, renewal approximation, or a lightweight
Monte Carlo sampler, "chosen by validated behavior, not complexity." At
this stage there is no evidence the Poisson family itself is the wrong
choice - P02's Discovery B diagnosed the near-zero-bin miscalibration as
consistent with an attempt-rate input error, not a distributional-family
error (over/under-dispersion was never measured against real delivered-
pairs counts). Replacing the distribution before checking whether
correcting the input alone fixes the problem would risk fixing the wrong
thing. If P02B still shows a distributional mismatch (e.g. delivered-pair
counts are visibly over- or under-dispersed relative to what the Poisson
model with the corrected mean predicts), that is the trigger to try a
binomial/negative-binomial family next - not assumed necessary now.

## What is still NOT fixed, measured, or validated by L3-R

- **Independence between fidelity-success and delivery-success** is still
  assumed when computing `satisfaction_probability = fidelity_success_
  probability * delivery_success_probability` - carried over unchanged
  from L3-original. Not measured here. P02B's paired-trial design must
  check the actual joint outcome correlation (planner-study brief section
  9's explicit requirement) - this module does not attempt to.
- **Whether the attempt-rate correction improves or worsens the near-
  zero-bin miscalibration is an open, unresolved empirical question.**
  `docs/l3_attempt_rate_audit.md`'s closing section explicitly declines to
  predict a direction: correcting attempt rate downward makes L3-R MORE
  conservative (lower predicted probabilities generally), which is the
  opposite of what would naively explain P02's under-prediction near zero.
  P02B's calibration-by-region analysis (five bins: p<0.1, 0.1-0.3,
  0.3-0.7, 0.7-0.9, p>=0.9) is what answers this, not this document.
- **`fidelity_success_probability` remains a deterministic 0/1 reuse** of
  L2-R's `fidelity_feasible` flag - no independent fidelity-uncertainty
  model is introduced by L3-R.
- **The ~13-63% residual, topology-dependent variance** the audit found
  unexplained by a single round-trip-multiplier constant is still present
  in L3-R's generation-rate estimate - `ATTEMPT_RATE_CONSERVATIVE_FACTOR`
  is one shared constant, not a per-topology-fitted correction.

## Fields

Reuses `ProbabilisticPlanEstimate` (`planning.planners.models`) unchanged,
with one addition: `estimated_completion_time_s` (previously always
`None` since L3-original never computed it; L3-R populates it from
L2-R's `estimated_final_pair_rate` when the plan is feasible, `None`
otherwise - `None` for L3-original by construction, verified by
`test_l3_original_estimate_unaffected_by_l3r_module_existing`).
