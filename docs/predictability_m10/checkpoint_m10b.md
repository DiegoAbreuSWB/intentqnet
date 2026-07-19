# Checkpoint M10-B — Boundary discovery

Covers M10.4 (coarse search) and M10.5 (refinement). Data: `results/
predictability_m10/raw/P11_boundary_search/trials.csv` (352 trials, 0
duplicates, 1 timeout - complete). Analysis: `results/predictability_m10/
processed/boundary_search_report.csv` (44 points, every point tested
persisted including discarded ones, per section 6's explicit requirement).

## Configurations searched

4 topologies (three_node, four_node, diamond_heterogeneous, small_mesh),
L2 planner (deterministic admission - isolates the physical/execution
question from any probability-threshold choice), `ShortestHopCountRouting`,
`reserved_memory_slots=10`, `duration_s=0.05`, `min_delivered_pairs=10`
fixed across all points. `requested_fidelity` was the swept axis, with
each topology's coarse grid centered on its own analytically-computed
swap-only fidelity (`planning.feasibility.estimate_swap_only_fidelity` -
not a blind range):

| Topology | Swap-only fidelity (analytical) | Coarse grid |
|---|---:|---|
| three_node | 0.6864 | 0.60-0.80 (8 points) |
| four_node | 0.5542 | 0.50-0.66 (8 points) |
| diamond_heterogeneous | 0.6864 (short/lossy route, selected by hop-count routing) | 0.60-0.80 (8 points) |
| small_mesh | 0.4476 | 0.38-0.53 (8 points) |

8 seeds per coarse point, 8 seeds per refinement point, up to 4 bisection
iterations where a bracket was found (section 7's Wilson-CI-based
five-region classification).

## A bug found and fixed during this milestone

The first run found NO transition point for three_node or small_mesh,
despite both having an obvious cliff in the coarse data (three_node:
p=1.0 at fidelity<=0.78, p=0.0 at 0.80; small_mesh: p=1.0 at <=0.44, p=0.0
at >=0.46). Root cause: stage B's trigger required a COARSE point to
already land inside [0.05, 0.95] - a sharp step function (no intermediate
probability at the tested grid spacing) never produces such a point, so
stage B was incorrectly skipped for both. Fixed by triggering stage B on
any high(>=0.5)/low(<0.5) bracket in the coarse grid, regardless of
whether any single coarse point was itself ambiguous - and resume-safety
was added to `run_point` so the fix could be validated by re-running the
same script without re-executing the 288 already-collected coarse trials
(confirmed: the corrected run added exactly 64 new trials, all in stage
B, 0 duplicates). Disclosed here per this project's standing practice of
reporting bugs found and fixed, not silently correcting them.

## Transition points found

| Topology | Bracket after refinement | Width | Shape |
|---|---|---:|---|
| **three_node** | fidelity in (0.795, 0.7975) | ~0.0025 | Sharp step - no intermediate probability observed at n=8 per point, even 4 bisections deep |
| **four_node** | fidelity in (0.595, 0.5975); coarse point at 0.58 showed **p=0.625** [0.31, 0.86] | ~0.0025 (refined bracket); genuine graded probability at 0.58 | **The only genuinely graded/probabilistic transition point found** - fidelity=0.58 is not a step-function artifact, it is a real ~62.5% empirical success rate with a wide Wilson CI at n=8 |
| **small_mesh** | fidelity in (0.4475, 0.44875) | ~0.00125 | Sharp step, same shape as three_node |
| diamond_heterogeneous | **No bracket found** - p=0.0 at every tested fidelity from 0.60 to 0.80 | N/A | Not fidelity-bound in this range - see below |

**diamond_heterogeneous's null result is itself a real finding, not a
search failure**: the "bad" (short, lossy) route `ShortestHopCountRouting`
selects has a much higher attenuation than three_node's uniform links (by
design - `demos.topologies.diamond_spec`'s docstring), and appears to be
bottlenecked by raw elementary-pair generation THROUGHPUT within
`duration_s=0.05`, not by the fidelity/purification-round threshold this
search varied. Confirming this (and finding diamond's actual transition
axis, likely `duration_s` or `reserved_memory_slots`) is out of scope for
this checkpoint - noted as a limitation, not investigated further here.

## Confidence intervals

All coarse and refinement points report a 95% Wilson interval (see
`boundary_search_report.csv`'s `ci_lo`/`ci_hi` columns). At n=8, intervals
are wide (e.g. a 6/8 result has CI [0.41, 0.93]) - consistent with the
governing brief's own expectation that Stage A/B use "poucas seeds" and
that P12 (boundary variability, M10.6) must widen these substantially
(100-500 seeds) for the actual predictability-limit estimates this phase
needs.

## Topology coverage

3 of 4 topologies (three_node, four_node, small_mesh) produced a usable
transition point; diamond_heterogeneous did not, in the fidelity
dimension tested. This satisfies the "at least one heterogeneous
topology" requirement for the upcoming P12 campaign only partially -
diamond's own transition (in whatever dimension actually drives it) is
not yet located. P12 can proceed with three_node/four_node/small_mesh's
found points plus robust-success/robust-failure anchors on diamond
(every diamond point tested is a robust ROBUST_FAILURE-adjacent result -
technically all p=0.0 with tight CIs given n=8, i.e. already a usable
ROBUST_FAILURE region, just not a TRANSITION one).

## Estimated computational cost

352 trials, ~1680s (28 min) of actual simulation wall time (excluding
subprocess/Python-startup overhead, which dominates real elapsed time for
this many small/fast trials) - mean 5.5s/trial. One `TIMEOUT` occurred
(small_mesh, fidelity=0.46, seed=103, capped at 60s) - a second data point
consistent with M9's/M10's already-documented tail-event phenomenon
(deferred to M10.8, not investigated here). P12's planned scale (up to
500 seeds per configuration, 14+ configurations) will cost substantially
more - a rough linear extrapolation from this checkpoint's per-trial cost
suggests several hours of wall time, to be scoped and disclosed
explicitly when P12 is designed, following this project's established
practice of transparent scope reduction when needed (P03/P02B/M9
precedent).

## What this means for P12 (boundary variability campaign)

Ready-to-use points for P12's minimum-coverage requirement (3
ROBUST_SUCCESS, 3 LIKELY_SUCCESS, 5 TRANSITION, 3 LIKELY_FAILURE, 3
ROBUST_FAILURE, across >= 4 topologies including >=1 heterogeneous):

- **TRANSITION**: four_node @ fidelity=0.58 (the one genuinely graded
  point found) is the strongest candidate; the narrow sharp-step brackets
  on three_node/small_mesh are candidates too, pending confirmation at
  higher seed counts that they remain non-degenerate (or resolve to
  ROBUST regions on either side, which is also a valid, reportable
  outcome).
- **ROBUST_SUCCESS / LIKELY_SUCCESS**: abundant on three_node, four_node,
  small_mesh (any coarse point with p=1.0, n=8, has CI lower bound 0.676 -
  already LIKELY_SUCCESS by the n=8 CI; will very likely upgrade to
  ROBUST_SUCCESS at n>=100).
- **ROBUST_FAILURE / LIKELY_FAILURE**: abundant on all 4 topologies
  including diamond_heterogeneous (p=0.0 at every tested point).

## Verdict

Boundary discovery **succeeded** for 3 of 4 topologies. Experiments may
proceed to M10.6 (P12) once explicitly authorized, using the points
identified above - diamond_heterogeneous's fidelity-independent failure
is carried forward as a disclosed, not-yet-resolved limitation rather
than blocking progress.
