# M9 conclusion audit (M10.11)

Classifies each M9 claim as SUPPORTED / PARTIALLY SUPPORTED / NOT YET
SUPPORTED / REFUTED, using everything M10.1-M10.10 established. The M9
report itself is not altered or deleted - this is a separate audit.

## 1. "Seed explains only 0.02% of `delivered_pairs` variance"

**SUPPORTED** (upgraded from "exploratory, unverified").

M9's original one-way eta-squared on P02B was legitimately flawed
(`reserved_memory_slots`/`duration_s` were perfectly collinear there) -
correctly flagged by the governing brief, not defended. M10.10 built a
purpose-designed, fully-crossed, BALANCED factorial (P15) specifically to
re-test this with an orthogonal multi-factor ANOVA (main effects and
interactions computed via the exact balanced-design sum-of-squares
partition, not an approximation). Result: seed's own marginal
contribution is **0.000%** (binary `satisfied` outcome, n=240, fully
balanced) and **0.043%** (`delivered_pairs`, n=70 SATISFIED-only
subsample). Both numbers are in the same negligible range as M9's
original 0.02% - two independent methods, one flawed and one rigorous,
converge on the same substantive conclusion.

**Qualification**: this holds for the parameter space actually tested
(two uniform, single-route linear-chain topologies at 6 topology-specific
fidelity/duration/memory combinations, L2-R/L3-R only). It is not proven
for diamond_heterogeneous or small_mesh (multi-candidate-route
topologies), nor for L1/L2/L3/L4.

## 2. "Error is mostly structural, not stochastic"

**SUPPORTED**, directly following from claim 1's controlled
re-verification: in P15's balanced ANOVA, `fidelity_level` (32%),
`duration_s` (21%), `scenario` (7.6%), and their interactions
(`fidelity_level:duration_s` 11.8%, `scenario:fidelity_level` 5.0%)
jointly explain the large majority of outcome variance, while seed
explains ~0%. "Structural" here means "attributable to the configuration
parameters this study varied," not a claim about physics in general.

## 3. "Fidelity was deterministic in the two evaluated regimes"

**SUPPORTED, and now shown to generalize further than M9 itself claimed.**
M9 correctly scoped this claim to "the two evaluated uniform-topology
regimes with fixed route and purification-round behavior" (favorable and
moderate-purification, three_node only, 200 seeds). M10.10's P15 data
independently confirms near-zero `average_fidelity` variance
(std ~1e-17, floating-point noise only) across a BROADER set: 2
topologies (three_node, four_node) x 3 fidelity/purification-round
regimes x 2 duration levels x 2 memory levels x 2 planners, 70 SATISFIED
trials total. The qualification that matters is unchanged from M9's own
careful wording, just wider: this holds for topologies with a single,
deterministic candidate route (both three_node and four_node qualify) -
it is explicitly NOT shown to hold for diamond_heterogeneous, where
M10.7 found the SELECTED ROUTE itself (not fidelity variance within a
fixed route) is what varies - a different kind of variability entirely,
driven by planner decision-making, not stochastic execution.

## 4. "Only delivered-pair count is stochastic"

**SUPPORTED**, same evidence as claim 3 (the two properties were tested
together in M9 and in this audit). The corollary from M10.10: even
`delivered_pairs`' own variance is overwhelmingly explained by design
parameters (fidelity/duration/memory/topology), not seed - so "stochastic"
here should be read as "the one quantity that DOES vary with seed," not
"a quantity whose variance is dominated by seed-driven randomness."

## 5. "L5 is not justified"

**SUPPORTED, more strongly than M9's own evidence alone established.**
M9 already found this from an information-level comparison with real
caveats (L4's near-perfect score came from only 2 easy combinations). M10
adds substantially more evidence pointing the same direction:

- M10.6 found that a small-sample (8-seed) search can be fooled into
  flagging a "transition" that resolves to firm ROBUST_FAILURE at n=100 in
  3 of 4 candidate points - reinforcing that this system's genuinely
  graded, learnable regions are narrower than they first appear.
- M10.7 found L4's real advantage at the one confirmed boundary
  (four_node) is modest (mean calibration error 0.0875 across K), and its
  more dramatic-looking advantage at diamond was ROUTE SELECTION, not
  calibration of a shared plan - a mechanism a hypothetical L5 trained on
  the CURRENT feature set (which does not include "try every route via
  internal simulation") would not obviously be able to replicate cheaply.
- M10.9-M10.10 reconfirm across a FOURTH independent design that L3-R
  adds zero decision-relevant value over L2-R (`planner_level` explains
  exactly 0.0% of variance in both `satisfied` and `delivered_pairs`) -
  the specific gap L5 would need to fill (extracting more value from
  available information than the current analytical family already does)
  keeps failing to materialize wherever it has been tested.

## 6. "Predictability Limits is the best next-paper direction"

**SUPPORTED, and strengthened.** M10 produced substantial additional
publishable material consistent with this framing, not competing with
it: the randomness-audit correction of M9's own claim (a genuine,
citable methodological finding about the pitfalls of assuming a
mechanism without dynamic verification), the small-sample-search
cautionary result (M10.6), the route-selection discovery (M10.7), and
the tail-event instrumentation's clean negative result for hypothesis 3
(M10.8) are all substantive contributions to a "predictability and
reproducibility limits" paper - none of them constitute a working,
validated learned planner, which is what a "Learned Intent Planning"
paper would require.

## Summary table

| Claim | M9 status | M10 status |
|---|---|---|
| Seed explains only 0.02% of variance | Exploratory (flawed method) | **SUPPORTED** (0.000%/0.043%, controlled ANOVA) |
| Error is mostly structural | Exploratory (flawed method) | **SUPPORTED** |
| Fidelity is deterministic (scoped) | Supported (2 regimes) | **SUPPORTED** (generalizes to 6 regimes, 2 topologies, still route-fixed) |
| Only delivered-pair count is stochastic | Supported (2 regimes) | **SUPPORTED** (same generalization) |
| L5 is not justified | Supported (limited evidence) | **SUPPORTED** (4 independent confirmations) |
| Predictability Limits is the best next paper | Supported | **SUPPORTED, strengthened** |

No M9 claim was REFUTED. One specific MECHANISM M9 proposed (the
`quantum_utils.random_state` explanation for observed wall-time variance)
was found NOT SUPPORTED by M10.1's dynamic audit and is corrected there,
separately from the six substantive claims above, which is why it is not
listed as a seventh row here - it was never one of the six headline
claims section 18 asked this audit to re-check, but is documented fully
in `docs/predictability_m10/randomness_audit.md`.
