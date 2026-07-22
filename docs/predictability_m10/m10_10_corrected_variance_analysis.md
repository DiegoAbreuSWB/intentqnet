# M10.10 — Corrected variance and information-value analysis (P15)

Data: `results/predictability_m10/raw/P15_balanced_factorial/trials.csv`
(240 trials, 0 duplicates, 1 timeout - complete). Analysis:
`scripts/analyze_p15_variance_decomposition.py`.

## Why M9's original claim needed re-checking

M9 computed a ONE-WAY eta-squared on P02B's data and reported "`seed`
explains only 0.02% of `delivered_pairs` variance." Section 15 of the
governing brief correctly flagged this as exploratory: P02B's
`reserved_memory_slots` and `duration_s` were perfectly collinear (paired
into a single "regime" factor), so separate one-way eta-squared values
computed there do not correctly attribute shared variance between
correlated factors, and cannot be trusted as a real decomposition.

## What P15 fixes

A fully-crossed, BALANCED factorial (2 topologies x 3 fidelity levels x 2
duration_s levels x 2 reserved_memory_slots levels x 2 planners, same 5
seeds - 400-404 - in every cell) lets every main effect and interaction
be computed via the standard balanced-design sum-of-squares partition,
which is EXACT (not approximate) for a balanced design: main-effect and
interaction sums of squares computed this way are orthogonal by
construction - unlike M9's separate one-way values, they correctly
attribute shared variance and (for a fully-modeled set of terms) sum to
the total.

**A real bug was found and fixed while building this analysis**: the
first version grouped by the raw `requested_fidelity` COLUMN instead of
the abstract `fidelity_level` (low/medium/high) LABEL - since each
topology uses different, non-overlapping raw fidelity values (three_node:
0.65/0.72/0.78; four_node: 0.53/0.58/0.63), `requested_fidelity` is
actually NESTED within `scenario`, not crossed with it. Grouping by the
raw value double-counted the same variance under two different factor
names, producing a mathematically impossible NEGATIVE interaction sum of
squares - a useful diagnostic in itself (a negative interaction SS in a
supposedly-balanced design is a hard signal that the design is not
actually balanced/crossed the way it was assumed to be). Fixed by mapping
back to the abstract `fidelity_level` label via the campaign's own YAML
config.

A second, similar issue was found (and explicitly flagged rather than
hidden) in the SECONDARY analysis: restricting to `delivered_pairs` on
only the 70 SATISFIED trials (the only rows where `delivered_pairs` is
defined at all) breaks the balanced-design assumption, since different
cells have different admission rates and therefore different SATISFIED
counts. `analyze_p15_variance_decomposition.py::is_balanced` checks this
explicitly and attaches a `caveat` field to any resulting negative
interaction term rather than silently reporting it as if it were valid.

## Primary result: variance decomposition of `satisfied` (0/1), n=240 (fully balanced)

| Term | Proportion of total variance |
|---|---:|
| `fidelity_level` | 31.9% |
| `duration_s` | 21.0% |
| residual (unmodeled higher-order interactions + seed) | 20.2% |
| `fidelity_level:duration_s` | 11.8% |
| `scenario` (topology) | 7.6% |
| `scenario:fidelity_level` | 5.0% |
| `reserved_memory_slots` | 0.84% |
| `duration_s:reserved_memory_slots` | 0.84% |
| `scenario:duration_s` | 0.84% |
| `planner_level` (L2-R vs. L3-R) | **0.0%** |

**Seed-only contribution (marginalized over every other factor): 0.000%.**

## Secondary result: variance decomposition of `delivered_pairs`, n=70 (SATISFIED only - NOT balanced, main effects only reliable)

| Term | Proportion of total variance |
|---|---:|
| `fidelity_level` | 26.7% |
| `reserved_memory_slots` | 20.0% |
| `duration_s:reserved_memory_slots` | 18.3% |
| `duration_s` | 13.8% |
| `fidelity_level:duration_s` | 13.5% |
| `scenario` | 12.9% |
| residual | 10.3% |
| `planner_level` | 0.0% |
| `scenario:fidelity_level`, `scenario:duration_s` | negative - **unreliable, disregarded** (unbalanced subsample, see above) |

**Seed-only contribution: 0.043%.**

## Direct comparison to M9's claim

| Claim | M9 (one-way eta-squared, P02B, exploratory) | M10.10 (balanced multi-factor ANOVA, P15) |
|---|---:|---:|
| Seed contribution to `delivered_pairs` variance | 0.02% | **0.043%** |
| Seed contribution to `satisfied`/outcome variance | not computed | **0.000%** |

**M9's substantive claim is CONFIRMED, not merely repeated**: two
independent analyses (a flawed exploratory one-way analysis on P02B, and
a rigorous, orthogonal, balanced multi-factor ANOVA on a purpose-built
factorial campaign) converge on the same conclusion - seed contributes a
negligible, near-zero share of outcome variance compared to design/
parameter factors (fidelity, duration, topology, and their interactions).
The METHODOLOGY M9 used was legitimately flawed (correctly flagged in
section 15); the CONCLUSION it produced holds up under a proper
re-analysis. This upgrades that specific M9 claim from "exploratory,
unverified" to "SUPPORTED by a controlled follow-up" - see
`m9_conclusion_audit.md` (M10.11) for the formal per-claim classification.

## What the residual actually is

Adding `fidelity_level:duration_s` and `scenario:duration_s` to the
originally-reported two interactions reduced the primary analysis's
residual from 32.8% to 20.2% - most of what looked like unexplained
variance is real, computable 2-way interaction effects this analysis
simply had not yet included, not hidden seed variance (already shown
separately to be ~0%). The remaining ~20% residual most likely reflects
3-way-and-higher interactions this pass did not compute (a
"computationally viable subset," per section 16's own framing, not an
exhaustive saturated model) - not disclosed as a gap because it doesn't
matter for the study's central question, but because completeness is
part of this project's own reporting standard.

## Information-value note (section 11): L2-R vs. L3-R

`planner_level` explains **exactly 0.0%** of variance in BOTH the primary
(`satisfied`) and secondary (`delivered_pairs`) decompositions - L2-R and
L3-R produced statistically indistinguishable outcomes across all 240
trials in this controlled factorial design. This is the THIRD independent
confirmation of the same pattern found in checkpoint 2B (McNemar test)
and M9's information-level comparison (near-identical Brier scores): **L3-R's
added statistical/probabilistic information layer provides no additional
explanatory or decision-relevant value over L2-R's resource-aware
analytical correction, in every controlled comparison this entire study
has run.** This is not a new finding - it is a fourth, independently-
collected data point supporting an already-well-established one.
