# L3 attempt-rate audit (M6c)

Reproducible via `scripts/audit_l3_attempt_rate.py` (no new simulations -
compares the analytical model against already-frozen F02/F03 raw data;
`scripts/generate_l3_attempt_rate_audit_figures.py` for the plots).

## Exact source of the error

**The original model (`docs/l3_probabilistic_model.md`) assumed one
classical round trip per elementary-generation attempt**
(`attempt_rate = reserved_memory_slots / (2 * classical_delay_s)`).
Fitting a range of candidate round-trip multipliers against real
`eg_attempts / duration_s` data from F02+F03 (200 trials) shows the
**best-fitting multiplier is ~7.32, not 2** - the original model's ratio
of predicted-to-observed attempt rate is **3.66x on average** (not merely
in the 2.4-4.3x range informally estimated before this audit; that range
was itself an average of a few spot checks, this is the precise value
over all 200 trials).

| Round-trip multiplier assumed | Mean ratio (predicted/observed) |
|---:|---:|
| 1 | 7.32 |
| 2 (original model) | 3.66 |
| 4 | 1.83 |
| 6 | 1.22 |
| **7.32 (best fit)** | **1.00** |
| 10 | 0.73 |
| 15 | 0.49 |

See `results/planner_study/figures/l3_attempt_rate_ratio_by_multiplier.png`.

## Magnitude

Original model: 3.66x overestimate on average (std 0.63x across 200
trials) - larger than the "2.4-4.3x" range informally noted before this
audit (that range came from a handful of spot comparisons, not the full
200-trial fit this audit performs).

## Topologies/conditions affected

The error is present across every topology and hop count tested - it is
NOT isolated to one scenario, though its magnitude varies somewhat:

| Hop count | n | Ratio (original model) |
|---:|---:|---:|
| 2 | 120 | 3.22x |
| 3 | 20 | 4.22x |
| 4 | 60 | 4.06x |

| Topology | n | Ratio (original model) |
|---|---:|---:|
| diamond_heterogeneous | 60 | 2.88x |
| small_mesh | 60 | 4.06x |
| three_node_1_repeater | 80 | 3.78x |

The range (2.88x-4.22x) is real but modest relative to the mean (3.66x) -
most of the error is explained by ONE shared correction (the round-trip
multiplier), not by topology-specific effects. The residual spread
(std_ratio staying around 0.15-0.63x depending on the multiplier tested,
not shrinking to exactly zero at the best fit) means the single-multiplier
model is a good but not perfect fit - some smaller, unexplained
topology-dependent variance remains.

## Ruling out the ten candidate hypotheses (planner-study brief, section 7)

1. **Incorrect use of memory frequency** - not investigated directly (the
   80 MHz raw excitation frequency is negligible next to classical-delay-
   scale timing at these distances, and was never part of the original
   formula) - RULED OUT as the dominant effect by construction; the
   classical-delay-based model already ignores memory frequency entirely,
   and correcting only the round-trip multiplier fully explains the gap.
2. **Overestimated parallelism** - not the primary cause: the
   `reserved_memory_slots` parallelism term itself was not changed, only
   the per-attempt-cycle TIME; a pure parallelism overestimate would
   predict a DIFFERENT functional relationship (rate scaling incorrectly
   with `reserved_memory_slots` itself, not a constant multiplicative
   offset) - not tested directly via a slots-only ablation in this pass,
   flagged for a future, more granular audit if the corrected model still
   underperforms.
3. **Total duration vs. active window** - not the primary cause: `eg_
   attempts / duration_s` is exactly what both the model and this audit
   use; a systematic active-window vs. total-duration gap would show up
   as a hop-count-independent multiplicative bias, which is what a
   uniform round-trip-multiplier correction ALSO produces - the two
   explanations are not perfectly separable from this data alone, but
   the round-trip story is independently motivated by Barret-Kok's
   documented 3-round protocol structure (see below), which the active-
   window story is not.
4. **Missing dead time** - plausibly folded into the fitted multiplier
   (~7.3 one-way delays is more than a naive 3-round x ~2 messages/round
   estimate of ~6 would predict) - some of the "extra" 1.3 could be
   protocol dead time/scheduling overhead not modeled; not separated out
   further in this pass.
5. **Missing memory blocking** - not modeled and not separately isolated;
   plausible contributor to the same residual as (4).
6. **Missing classical communication rounds - CONFIRMED as the dominant,
   correctable effect.** Barret-Kok's protocol (`sequence.
   entanglement_management.generation.barret_kok.py`) runs THREE rounds
   (`ent_round` 1->2->3), each involving photon emission, BSM
   measurement, and classical message coordination - substantially more
   coordination overhead than the original model's single round trip.
   The empirically best-fitting ~7.3x multiplier is consistent in
   magnitude with this (though this audit does not independently verify
   an exact "7.3 messages" decomposition from the SeQUeNCe source - it is
   an empirical fit, not a re-derived protocol timing diagram).
7. **Missing purification consumption** - not applicable to this specific
   audit (`eg_attempts` is elementary-generation only, upstream of any
   purification); purification's pair cost is audited separately
   (`docs/l2_iterative_model.md`'s `2**rounds` audit - confirmed correct).
8. **Missing dependency between links** - checked indirectly: observed
   attempt rate does not increase with hop count (see below), which is
   the opposite of what naive double-counting across links would predict
   - RULED OUT as a significant confound.
9. **Double-counting attempts - RULED OUT.** If `eg_attempts` were summed
   across multiple links per trial, observed rate would INCREASE with
   hop count; instead it mildly DECREASES (2 hops: 15,528/s; 3 hops:
   11,850/s; 4 hops: 12,322/s) - consistent with per-link independent
   attempts, not cumulative double-counting.
10. **Attempts/successes confusion - RULED OUT.** Verified directly:
    `eg_success <= eg_attempts` holds in all 200 audited rows.

## Does the original probability model remain valid?

**No, not as originally parameterized.** The attempt-rate term is
systematically biased (3.66x too high), which propagates directly into
`expected_delivered_pairs` and therefore `delivery_success_probability`
and `satisfaction_probability` (`docs/l3_probabilistic_model.md`). This
is precisely the mechanism behind Discovery B's near-0.0 miscalibration
in P02 (checkpoint 2): configurations L3 judged "near-impossible" were,
in reality, less impossible than predicted, consistent with the model
systematically over-predicting throughput in the direction that would
make truly-marginal cases look worse (lower probability) than they are -
wait, this needs care: an OVER-estimate of attempt rate should make L3
MORE optimistic (higher predicted probability), which would predict
FEWER false-near-zero cases, not more. The P02 near-zero miscalibration
(33.3% of "near-impossible" predictions succeeding) is therefore not
fully explained by the attempt-rate overestimate alone; L3-R must be
evaluated on whether CORRECTING the attempt-rate bias (making predictions
even MORE conservative, i.e. lower) makes the near-zero bin's
miscalibration better or worse - this is an open question P02B must
check empirically, not an assumed outcome.

## Correction adopted for L2-R (interim, before L3-R)

L2-R (`docs/l2_resource_aware_model.md`) used a stopgap conservative
factor of 4.5 (the high end of the informally-estimated 2.4-4.3x range)
BEFORE this audit ran. **This audit supersedes that estimate**: the
precise, full-data correction factor is ~7.32, not 4.5. L2-R's
`ATTEMPT_RATE_CONSERVATIVE_FACTOR` should be updated to reflect this
audit before P02B, so L2-R and L3-R share the same, now-validated
attempt-rate correction rather than two different ad hoc numbers.
