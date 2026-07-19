# Predictability limits of quantum intent planning - final report (M9)

Answers the five questions posed at the start of this phase
(`docs/predictability_study.md`), using: the RNG-determinism finding, the
retry-storm controlled sweep (`docs/retry_storm_analysis.md`, P04, 40/40
trials complete), the information-level comparison (sections 3-4, reusing
frozen P02B/P03 data), the variance decomposition (section 7, reusing
frozen P02B data), and the intrinsic-variability campaign (section 1,
P02_variance - **152/200 trials complete** at time of writing: the
"favorable" intent fully done (100/100), "moderate_purification" 52/100
and still running in the background; reported transparently as partial
on the second intent, not withheld pending completion, since it is a
supporting data point, not the pivot of this report's verdict, and both
intents already show a consistent, stable pattern - see section 3).

The entire planner family (L1, L2, L2-R, L3, L3-R, L4) remains frozen
throughout, per this phase's standing constraint. L4 is treated
throughout as the **Reference Planner**, not "the best planner" (section
8) - a high-information comparison point, not a deployment
recommendation (its own cost profile, documented in P03/checkpoint 2B,
is unchanged and still the reason it isn't simply adopted outright).

---

## 1. Is there enough pre-execution information to correctly predict an intent's outcome?

**Partially, and unevenly across information levels.** The information-
level comparison (reusing P02B for levels 0-1, P03 for level 2):

| Information level | Planner(s) | Brier score | n | Caveat |
|---|---|---:|---:|---|
| 0 (topology + resources) | L1 | 0.100 | 240 | hard decision, no probability |
| 0 (topology + resources) | L2 | 0.392 | 240 | hard decision, no probability |
| **0 (topology + resources, corrected)** | **L2-R** | **0.067** | 240 | hard decision, no probability |
| 1 (statistical rates) | L3 | 0.058 | 240 | probability output |
| 1 (statistical rates, corrected) | L3-R | 0.068 | 240 | probability output |
| 2 (full simulated state, internal batch) | L4 (Reference) | 0.000 | 60 | only 2 easy/favorable combos tested |
| 3 (oracle) | - | 0.000 | - | not implementable, theoretical anchor |

Two things stand out. First, **L2-R (level 0, resource-corrected) already
matches L3/L3-R (level 1, statistical)** - going from raw topology/
resource knowledge to a properly resource-AWARE analytical model closes
almost the entire gap to the probabilistic family in this study; adding
statistical/probabilistic information on top of that correction added
essentially nothing (L3-R is marginally worse than L2-R, not better).
Second, **L4's perfect score is not yet trustworthy as a general
result** - it comes from only 60 trials across 2 deliberately easy/
favorable combinations (P03's disclosed reduced scope), not from the
marginal/adversarial regimes where the analytical family's biases are
largest. **Conclusion: there IS enough pre-execution information to
predict MOST outcomes reasonably well once the resource model is
corrected (L2-R), but the specific remaining error (documented in
checkpoint 2B: L2-R's ~4x delivery underprediction, L3-R's ~2.5x
overprediction, both planners' persistent bimodal calibration) is not
resolved by any information level tested at full statistical
confidence.**

## 2. How much of the observed error is caused by planner limitations?

**Most of it, per the variance decomposition.** Reusing P02B's frozen
data (`delivered_pairs` as response, one-way eta-squared per factor -
`scripts/analyze_predictability_limits.py::analyze_variance_decomposition`):

| Factor | Eta-squared (variance explained) |
|---|---:|
| `reserved_memory_slots` / `duration_s` (perfectly collinear by design) | 0.384 |
| `requested_fidelity` | 0.316 |
| `scenario` (topology) | 0.305 |
| `planner_level` | 0.182 |
| **`seed` (pure stochastic variation)** | **0.0002** |

`planner_level` alone explains **18.2%** of the variance in delivered
pairs - a substantial, planner-attributable effect, consistent with
checkpoint 2B's finding that different planner levels produce
systematically different (and differently biased) delivery predictions
and admission decisions. This is the error component a better planner
(analytical or learned) COULD in principle reduce.

The intrinsic-variability campaign (P02_variance, 152/200 trials
complete) corroborates this from a second angle: **both tested intents
show P(satisfied) = 1.0 across every seed sampled so far** - the
"favorable" intent (min_fidelity=0.60, 0 purification rounds) at 100/100
seeds, and "moderate_purification" (min_fidelity=0.72, 1 purification
round - checkpoint 1's own well-characterized case) at 52/100 seeds so
far. Seed variation changed the exact `delivered_pairs` COUNT (std ≈
5.4 for the moderate-purification intent, ≈ 10.1 for the favorable one)
but never the qualitative SATISFIED/VIOLATED/REJECTED outcome, in either
regime, in this sample.

## 3. How much of the observed error comes from the simulated network's inherent variability?

**Very little, at least for `delivered_pairs` in this campaign's design.**
`seed` explains **0.02%** of the variance - three orders of magnitude
below every design-parameter factor. The intrinsic-variability campaign
(152/200 trials complete across two intents, see section 2 above)
corroborates this directly: **P(satisfied) = 1.0 across every seed
sampled so far, in BOTH tested regimes** (a 0-round-purification
"favorable" case, complete at 100/100 seeds, and a 1-round
"moderate_purification" case, 52/100 seeds so far) - the qualitative
outcome never flipped due to seed alone, only the exact delivered-pair
count varied. **The dominant source of "error" in this study is
structural/parametric (which topology, which fidelity target, which
resource regime, which planner), not aleatoric seed-to-seed noise** - an
important, if perhaps counterintuitive, finding: this system is
*more* predictable in the pure-stochastic sense than the planner
family's own admission/delivery errors would suggest.

**One qualification, not to be glossed over**: the retry-storm
investigation found a real, if rare, exception - `operational_seed` does
NOT fully control determinism (SeQUeNCe's `quantum_utils` module draws
from Python's uncontrolled global `random` state - see
`docs/retry_storm_analysis.md`). This means a small residual of what
looks like "seed variance" is actually uncontrolled-RNG variance, not
strictly physical randomness properly tied to a reproducible seed. Its
measured contribution (eta-squared 0.0002) is still small, but its
EXISTENCE - and the fact that it produced a genuine ~48723s outlier at
least once - is itself evidence of a real, if narrow, irreducible-in-
practice cost/outcome variability that no planner, however well-informed,
could have forecast from pre-execution information given the current
codebase.

## 4. Is there an upper limit to predictability, even with a perfect planner?

**Yes, bounded below by the RNG-control gap, and empirically small
elsewhere.** Even a hypothetical perfect planner (equivalent to the
theoretical Level-3 oracle) could not predict the EXACT wall-clock cost
or, in rare cases, the precise physical outcome of a marginal-fidelity
purification-heavy plan, because SeQUeNCe's own dependency code (never
modified here) does not tie all of its physical sampling to a
reproducible seed. Outside of that specific execution-cost axis, the
variance-decomposition and partial intrinsic-variability results suggest
the SATISFACTION outcome itself is close to fully determined by
observable pre-execution parameters (topology, fidelity, resources) in
the regimes tested so far - i.e., the "irreducible" component of
predictability is empirically SMALL for delivery-outcome prediction, but
NON-ZERO and occasionally severe for execution-cost prediction (the
retry-storm tail).

## 5. Is it worth developing a machine-learning-based planner (L5)?

Checked against the three-part criterion the governing brief specifies:

1. **Does systematic, predictable error still exist?** Yes - checkpoint
   2B's own findings (L2-R's ~4x delivery underprediction, L3-R's ~2.5x
   overprediction, persistent bimodal calibration with empty probability
   regions) and this phase's variance decomposition (`planner_level`
   explains 18.2% of delivered-pairs variance) both confirm real,
   planner-attributable, non-random error remains.
2. **Does pre-execution information exist that could reduce it?**
   **Only weakly evidenced, and with an important caveat.** The
   information-level comparison shows diminishing, not increasing,
   returns beyond L2-R: L3/L3-R (adding statistical information) achieved
   essentially the SAME Brier score as L2-R (which uses no statistical
   information at all, only a corrected resource model) - meaning within
   this study, the achievable gain from "more information" (short of full
   internal simulation) appears to already be captured by L2-R's
   analytical correction, not by anything a learned model would
   naturally add on top of the SAME feature set. L4's near-perfect score
   is suggestive but comes from a small, easy sample (n=60, 2
   combinations) - not strong enough evidence that a genuinely
   exploitable information gap exists in the harder, marginal regimes
   where the analytical family's errors are largest.
3. **Is that information currently unexploited by existing planners?**
   Partially - L4's internal-simulation signal is real and unexploited
   by L1-L3-R, but exploiting it CHEAPLY (the entire point of an L5
   that would be worth building) is unproven: this study did not show
   that L4-quality predictions are achievable from Level-0/1 FEATURES
   alone (which is what a learned model would need) - only that running
   an expensive internal simulation (L4's own approach) achieves it.

**Verdict: L5 NOT SCIENTIFICALLY JUSTIFIED YET.**

The evidence gathered in this phase does not meet the bar the brief
itself set. Criterion 1 is met, but criteria 2 and 3 are not convincingly
established: the marginal value of additional information beyond L2-R's
already-implemented resource correction appears small in every regime
where it could be directly measured (L3/L3-R vs. L2-R), and the one
information level that clearly outperforms (L4) does so via expensive
simulation, not via features a learned model could cheaply reproduce -
whether such reproduction is even possible was not tested here (it would
require training a model against L4/oracle outcomes using only Level-0/1
features on a much larger, better-balanced dataset than currently
exists, which checkpoint 2B's own checklist already found unmet: severe
delivery-prediction bias, mostly-empty calibration regions).

This is not a rejection of learned planning as a concept - it is a
finding that **this project has not yet produced the evidence needed to
justify starting it**, and per section 18's "don't force conclusions"
principle, that is reported as the honest, acceptable outcome of a
rigorous predictability study, not a failure to find a positive result.

## Should the next article focus on Learned Intent Planning or Predictability Limits?

**B) Predictability Limits of Quantum Intent Planning.**

Justification: the concrete, defensible, evidence-backed contributions
of this entire study (M1-M9) are (a) the progressive planner-family
comparison and its honest failure modes (L1's over-rejection, L2's
resource-blindness, L2-R's/L3-R's partial-but-incomplete corrections),
(b) the discovery that a supposedly "seed-controlled" quantum network
simulator has a real, undocumented determinism gap with measurable
consequences (the retry storm), and (c) the variance decomposition
showing planner-attributable error dominates over stochastic noise in
this system - a genuinely interesting, publishable scientific claim about
the LIMITS of analytical planning and the boundaries of what any planner
(learned or not) can achieve given the network's actual variability
profile. A "Learned Intent Planning" article would require a working,
validated L5 this phase explicitly found insufficient grounds to build -
writing that article now would overclaim relative to the evidence.
"Predictability Limits" is the paper this project's actual data supports.

## What would change this verdict

Per the brief's own criteria, restart the L5 evaluation if: (a) a larger,
harder-regime L4 sample shows its accuracy advantage persists outside
easy/favorable combinations (this phase only tested 2 such combinations),
or (b) a future analytical correction to L2-R/L3-R's remaining
delivery-prediction bias fails where a learned feature combination
succeeds on held-out data - neither has been demonstrated yet.
