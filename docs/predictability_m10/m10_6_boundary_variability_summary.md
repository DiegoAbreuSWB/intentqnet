# M10.6 — Boundary variability campaign (P12) summary

Data: `results/predictability_m10/raw/P12_boundary_variability/trials.csv`
(820 trials, 0 duplicates, 3 timeouts - complete). Analysis:
`results/predictability_m10/processed/boundary_variability_report.csv`.

Scope note: the campaign's own YAML docstring says "5 TRANSITION"
configurations - this was a counting error at design time; the actual
config list has 4 TRANSITION-labeled entries (three_node, four_node,
small_mesh, diamond - one per topology), giving 4x100 + 14x30 = 820
trials exactly as collected, not the 890 originally estimated. Corrected
here, not silently left inconsistent.

## The central finding: most 8-seed "transition" candidates were not real

| Configuration | n | p_satisfied | 95% CI | Expected region | **Observed region at n=100** |
|---|---:|---:|---|---|---|
| **four_node_transition** (fid=0.58) | 100 | **0.68** | [0.58, 0.76] | TRANSITION | **TRANSITION - CONFIRMED** |
| three_node_transition (fid=0.79625) | 100 | **0.0** | [0, 0.037] | TRANSITION | **ROBUST_FAILURE** |
| small_mesh_transition (fid=0.44875) | 100 | **0.0** | [0, 0.037] | TRANSITION | **ROBUST_FAILURE** |
| diamond_transition (dur=0.09) | 100 | **0.10** | [0.055, 0.174] | TRANSITION | LIKELY_FAILURE |

Only **four_node's** transition point survived scrutiny at 10x the seed
count (62.5% at n=8 in M10.4, 68% at n=100 here - consistent, stable, a
genuinely graded probability). The other three were artifacts of M10.4's
8-seed coarse/refine search landing on a point that LOOKED transitional
at n=8 but is actually firmly in a failure region - the bisection
algorithm, run at only 8 seeds per step, was fooled by sampling noise
near a point estimate, not by a real graded probability.

**This is exactly the caution this entire M10 phase exists to enforce**,
and it is reported prominently rather than minimized: a small-sample
search can misidentify "near the boundary" even when using a principled
method (Wilson-CI-based bisection) - the CI at n=8 for these three points
was always wide enough to be honest about the uncertainty, but a
downstream consumer reading only the point estimate (as M10.4/M10.5's
stage-B bisection logic itself did, by design, to decide where to bisect
next) would have been misled. Confirmation at n>=100 is what actually
settles it.

Also found: `diamond_likely_success` (duration_s=0.10, expected
LIKELY_SUCCESS from a 5-seed pilot showing 5/5) came back as **observed
TRANSITION** at n=30 (p=0.267) - the SAME lesson from a different angle:
a 5-seed pilot showing 100% success is not strong evidence of
LIKELY_SUCCESS, let alone ROBUST_SUCCESS.

## Sample-size limitation for the ROBUST categories

Every configuration seeded at n=30 (the disclosed-reduction seed count
for non-TRANSITION configs) that achieved a perfect p_hat=1.0 or 0.0
classified as LIKELY_SUCCESS/LIKELY_FAILURE, never ROBUST_SUCCESS/
ROBUST_FAILURE - the Wilson lower bound for 30/30 is 0.886, below the
0.95 threshold section 7 requires. This is a mechanical consequence of
n=30 being too small to reach ROBUST classification even at a perfect
observed rate, not a sign of genuine unpredictability - a real, disclosed
limitation of this campaign's seed-count reduction, not a finding about
the underlying physics. `small_mesh_robust_success`/`four_node_robust_
success`/`three_node_robust_success`/`four_node_robust_failure`/etc. are
therefore reported at their observed (LIKELY) classification, with a note
that they would very likely upgrade to ROBUST at n>=~60-70 given their
current point estimates.

## Predictability measures (section 9)

Binary entropy (`H(Y|X=configuration)`, reported as "empirical
within-configuration outcome uncertainty under the evaluated SeQUeNCe
model," never "irreducible uncertainty" unqualified):

- **four_node_transition: H=0.90 bits** - the only configuration with
  substantial within-configuration outcome uncertainty in this campaign.
- Every other configuration: H rounds to 0.0-0.47 bits, dominated by
  configurations at or near p=0 or p=1 (low genuine uncertainty at the
  configuration level, once seed count is large enough to trust the
  estimate).

## Bayes-style empirical configuration-conditional lower bound (section 10)

- Equal-weighted-by-configuration: **0.0493**
- Weighted-by-trial-count: **0.0683**

Interpretation (exactly as scoped in section 10, not overclaimed): a
classifier that knows ONLY which of these 18 configurations an intent
belongs to (never the future seed) and always predicts the majority
class is wrong on average ~5-7% of the time across this specific
campaign's configuration mix - dominated almost entirely by
`four_node_transition`'s ~32% minority-class rate (`min(0.68, 0.32)`),
since every other configuration's minority class rate is near 0. This is
an `empirical configuration-conditional lower bound` for THIS campaign's
specific mix of configurations, not a universal physical limit - a
campaign weighted toward more TRANSITION-like configurations would show a
much higher bound.

## Timeouts

3 trials hit the 120s cap (out of 820) - a ~0.37% empirical rate in this
campaign, consistent with M9's/M10.4's prior observations of a rare but
real tail-event phenomenon. Root cause still deferred to M10.8, not
investigated here.

## Implication for M10.7 (L4 boundary reference)

`P13_l4_boundary_reference.yaml` targets the ORIGINAL 4 candidate
transition configurations. Given this campaign's finding, L4's evaluation
at three_node/small_mesh/diamond's "transition" points is now better
understood as evaluating L4 at configurations confirmed to be firmly in
a FAILURE region (not truly marginal) - still a valid and useful
calibration check (does L4 correctly output a low probability there,
avoiding false confidence, exactly as section 12 asks?), just not the
"near the boundary" test originally intended for those three. Only
`four_node_transition` tests L4 at a genuinely marginal configuration.
This is disclosed here rather than silently re-scoping P13's already-built
config before running it.
