# M10.7 — L4 (Reference Planner) at the boundary (P13) summary

Data: `results/predictability_m10/raw/P13_l4_boundary_reference/trials.csv`
(16 trials, 0 duplicates, 1 timeout - complete). Reuses P12's already-
collected empirical data as the comparison ground truth (no re-collection).

## Two real bugs found and fixed while running this milestone

1. **Missing `topology_spec` in the M10 worker's `PlanningContext`.** L4
   needs `context.topology_spec` (the raw `NetworkTopologySpec`) to build
   its internal-simulation `SequenceAdapter` instances - L1-L3-R never
   read this field, so the gap was invisible until L4 was exercised for
   the first time in M10. Fixed in
   `scripts/run_predictability_m10_trial_worker.py` (a one-line addition,
   never touching L4's own frozen code).
2. **Planning itself was not exception-guarded.** L4's planning step runs
   REAL internal simulations, which can hit the exact same genuine
   SeQUeNCe protocol assertion P02B first found (BBPSSW's own
   `kept_memo.fidelity > 0.5` check) when a candidate route's fidelity is
   too low for purification to ever help - `small_mesh_transition`
   (fidelity=0.44875, just barely above its own swap-only fidelity of
   0.4476) hit this on every K value. `execute_predictability_m10_trial`
   only wrapped the OUTER deployment's `executor.run()` in a try/except;
   L1-L3-R's purely analytical planning never raises, so this gap was
   also invisible until L4's planning was exercised. Fixed by wrapping
   `policy.plan(...)` itself, recording `SIMULATION_ERROR` (same
   convention as the outer handler) - never modifies L4's frozen code.

## An apparent third "bug" that turned out to be a genuine, important finding

`diamond_transition` initially looked alarming: L4 predicted
`satisfaction_probability=1.0` at every K in {5,10,20,30}, while P12's
independent 100-seed sample of the identical (fidelity, duration_s) pair
found only **10% empirical success** - a huge, worrying miscalibration if
real. Before reporting it as such, it was investigated directly (not
assumed):

- Manually replaying L4's own derived internal seeds (e.g. 500852160,
  500852165, 500852170, 500852175) through the standard real-execution
  path, using the exact same no-purification plan L4 constructs
  internally: 1/4 satisfied (25%) - consistent with P12's ~10%, NOT with
  L4's reported 1.0.
- Calling `run_internal_simulations` DIRECTLY (bypassing the full
  `SimulationInTheLoopPlanner.plan()`) on the exact `['r1', 'bad', 'r3']`
  route with K=30: **`satisfaction_rate=0.267`** - again consistent with
  P12, NOT with the 1.0 the full planner reported for the SAME
  configuration.
- Checking which route `SimulationInTheLoopPlanner.plan()` actually
  SELECTED in P13's real trials: **`r1 -> good1 -> good2 -> r3`** - the
  longer, lower-attenuation "good" route, NOT the `r1 -> bad -> r3`
  shortest-hop route `ShortestHopCountRouting` mechanically forces every
  other planner in this family (L1, L2, L2-R, L3, L3-R, and hence P12's
  own empirical data) to use.

**This is not a bug or a miscalibration - it is L4 correctly recognizing,
via its own internal simulations of BOTH diamond candidate routes, that
the "good" route reliably succeeds (~100%) while the "bad" route the
routing-strategy-bound planner family is stuck with only succeeds
~10-27% of the time, and switching to it.** `diamond_spec`'s own
docstring already describes exactly this design intent (a "fast-but-
lossy direct route" vs. a "slower, near-lossless detour") - L4 is the
first planner level in this entire study to actually act on that
distinction at this specific fidelity/duration operating point, because
it evaluates real simulated outcomes per candidate rather than committing
to `ShortestHopCountRouting`'s hop-count-only preference before any
feasibility check.

**Corrected interpretation**: P12's `diamond_transition` empirical data
point (10% success) describes the "bad"-route plan specifically, not
"diamond at this configuration" in general - the true achievable
satisfaction rate (using the best AVAILABLE route) is close to 100%. L4's
predicted probability of 1.0 is calibrated correctly **for the route it
actually selected**, not miscalibrated relative to a route it did not
select.

## Results by configuration

| Configuration | K | Predicted P | Real outcome | Note |
|---|---:|---:|---|---|
| three_node_transition (now known ROBUST_FAILURE) | 5,10,20 | N/A (rejected) | REJECTED | L4's `PurifyUntilTarget` strategy only models a single purification round (mirrors what SeQUeNCe's default reservation mechanism does with no custom Rules) - correctly cannot reach fidelity=0.79625 (needs several rounds per M10.4/M10.5), so correctly rejects, consistent with the confirmed 0/100 real rate |
| three_node_transition | 30 | - | TIMEOUT (900s cap) | consistent with this project's known rare-tail-event risk near marginal purification regimes |
| **four_node_transition (the one genuine TRANSITION)** | 5 | 0.80 | SATISFIED | single route (linear chain) - a fair, same-plan comparison |
| | 10 | 0.50 | VIOLATED | |
| | 20 | 0.65 | SATISFIED | |
| | 30 | 0.70 | SATISFIED | predictions bracket P12's empirical 0.68 reasonably; no monotonic K-convergence pattern is visible at this small a set of K values, but all four are within a plausible range of the true rate |
| small_mesh_transition | 5,10,20,30 | N/A | SIMULATION_ERROR | structural: fidelity=0.44875 is barely above small_mesh's own swap-only fidelity (0.4476) - the same genuine "purification can't help below this margin" constraint P02B first found, now also surfacing inside L4's own internal simulations |
| diamond_transition | 5,10,20,30 | 1.0 (all K) | SATISFIED (all 4) | L4 switched to the "good" route - see above; not comparable to P12's "bad"-route empirical data |

## What this means for section 12's question

**Does L4 have a real advantage near the boundary?** Yes, but via a
different mechanism than originally framed: not primarily better
CALIBRATION of a fixed plan (the only clean same-plan test available,
four_node, shows L4's predictions in a reasonable but not obviously
superior range compared to the true 0.68), but **better ROUTE SELECTION**
when multiple candidates exist and the cheap, hop-count-only routing
strategy every analytical planner in this family is bound to picks the
wrong one. This is a genuinely different, and arguably more important,
type of advantage than the calibration question the brief posed - worth
carrying into the final synthesis (M10.9-M10.12) explicitly, not folded
silently into a generic "L4 predicts probabilities well" narrative.

## Cost

Planning time scaled with K roughly linearly, as expected (K internal
simulations dominate): four_node's K=5/10/20/30 took 28s/49s/97s/150s.
Diamond's (2 candidate routes, both fully simulated per K) took
75s/148s/294s/438s - consistent with ~2x four_node's per-K cost, matching
the 2-candidate-route explanation directly.
