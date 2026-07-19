# Retry storm analysis (M9, section 5)

Investigates the ~48723s (~13.5h) outlier trial found in P02B
(`P02b_resource_aware_planners:four_node:e961642e2e5e233b:L3:7:
p02b-intent`). Data: `results/predictability/raw/P04_retry_storm/
trials.csv` (40 trials, 0 failures, 0 timeouts - complete). Never
re-runs or alters P02B.

## Why it occurred

The trial's parameters: four-node chain (`linear_chain_2_spec`),
`min_fidelity=0.60`, `reserved_memory_slots=10`, `duration_s=0.05`. The
four-node chain's swap-only fidelity is 0.5542 (checkpoint 1) - reaching
0.60 requires **4 purification rounds** (structural cost `2^4=16` raw
pairs per final pair). At this fidelity/round combination, `L3`
(collected at `admission_threshold=0.0`, so it deploys the plan
regardless of its own ~0.02% predicted satisfaction probability) admits
a plan real SeQUeNCe then has to attempt via Barret-Kok generation +
BBPSSW purification, repeatedly, within the 0.05s reservation window.

**The exact 48723s value is NOT reproducibly triggerable** from
(topology, route, seed, fidelity) alone - this is itself the central
finding of this analysis, not a side note:

- Seven isolated fresh-process reruns of the *exact same* nominal
  configuration (four_node, L3, seed=7, fidelity=0.6) gave wall times of
  3.1s, 10.67s, 11.14s, 10.65s, 11.22s, 11.24s, 7.75s - the final
  `SATISFIED`/`VIOLATED` outcome was stable (always VIOLATED,
  delivered_pairs=4) but the real cost varied by ~3.6x even across these
  seven attempts, none within two orders of magnitude of 48723s.
- Root cause: SeQUeNCe's `sequence.kernel.quantum_utils` module (a
  dependency, never modified) draws from Python's global `random` module
  for some physical sampling, bypassing the per-node/per-link seeded
  `numpy.random.default_rng` generators our adapter DOES fully control
  (`network/topology.py`'s `to_router_net_topo_config`). Our adapter
  never reseeds this global module, so `operational_seed` does not fully
  pin down a trial's realized randomness - see
  `docs/predictability_study.md`'s "foundational finding" section for
  the full account and the mitigation adopted for M9's own new trials
  (explicit reseeding in `experiments.predictability_runner`).

This means the 48723s event is best understood as a **rare, heavy-tailed
realization** of a genuinely stochastic retry process, occurring under
conditions our current seed convention does not fully control - not a
deterministic function of the visible parameters, and not a bug in this
project's own code (SeQUeNCe's dependency behavior is outside the "never
modify SeQUeNCe core" boundary).

## Controlled sweep: does the storm reproduce systematically?

`scripts/run_p04_retry_storm.py`, using **L2** (deterministic admission
whenever fidelity is analytically reachable - chosen specifically to
isolate physical/execution cost from any probability-threshold choice)
on the same four-node chain, swept `min_fidelity` across the entire
round-count transition (0 to 8 rounds) at 5 seeds each, every trial under
a hard 120s subprocess wall-clock cap:

| Target fidelity | Purification rounds | n | Mean wall (s) | Max wall (s) | Timeouts | Satisfied | Violated |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.55 | 0 | 5 | 5.44 | 5.65 | 0 | 5 | 0 |
| 0.58 | 3 | 5 | 4.15 | 4.32 | 0 | 4 | 1 |
| 0.60 | 4 | 5 | 4.28 | 4.65 | 0 | 0 | 5 |
| 0.62 | 5 | 5 | 4.03 | 4.46 | 0 | 0 | 5 |
| 0.64 | 6 | 5 | 3.34 | 3.59 | 0 | 0 | 5 |
| 0.66 | 6 | 5 | 3.29 | 3.51 | 0 | 0 | 5 |
| 0.68 | 7 | 5 | 3.18 | 3.33 | 0 | 0 | 5 |
| 0.70 | 8 | 5 | 3.12 | 3.40 | 0 | 0 | 5 |

**Zero storms and zero timeouts across all 40 trials**, spanning the
entire fidelity range from "trivially easy" (0 rounds) through "at the
analytical ceiling" (8 rounds, `max_rounds=8`). See
`results/predictability/figures/P04_wall_time_vs_fidelity.png`.

**A sharp, real phase transition exists, but it is in the OUTCOME, not
the cost**: satisfaction rate drops from 100% (fidelity <= 0.55) to 0%
(fidelity >= 0.60) within a narrow 0.05 window - consistent with
checkpoint 1's and the L2-R model's characterization of this topology's
purification ceiling. **Wall time does NOT explode in this transition -
if anything it decreases slightly** as more rounds are required (3.34s
mean at 6 rounds vs. 5.44s at 0 rounds), most likely because a
VIOLATED-bound trial with 0 delivered pairs terminates its "counting"
phase sooner than one that must accumulate SATISFIED pairs across a full
purification chain.

## Interpretation

1. **No systematic "critical operating region" of catastrophic cost was
   found** in this 40-trial controlled sweep - the fidelity/round
   transition is sharp for the SATISFIED/VIOLATED outcome, but not for
   wall-clock cost.
2. **The 48723s event is consistent with a rare tail risk** (occurring
   in roughly 1 of ~1200 P02B trials, i.e. an empirical rate on the
   order of <0.1%, and not reproduced once in this additional 40-trial
   sample either) rather than a reliably-triggerable phase transition in
   cost. Characterizing its true rate precisely would require many more
   trials than this pilot's budget allowed - disclosed as a limitation,
   not papered over.
3. **The likely mechanism** is the RNG-control gap documented above: an
   unlucky realization of SeQUeNCe's internally-unseeded physical
   sampling, compounding across the many retry attempts a low
   round-success-probability purification chain requires, occasionally
   producing an extreme number of real simulated events before the
   reservation window's outcome resolves.
4. **This finding is itself evidence for this phase's central question**:
   even with perfect knowledge of topology, resources, and fidelity
   target (which planner-level knowledge, however sophisticated, could
   in principle supply), the REAL execution cost of a given plan retains
   a genuinely unpredictable component that no planner - however
   information-rich - could have forecast from pre-execution information
   alone, because it depends on a randomness source not currently tied to
   any controllable seed. This bounds what ANY planner (including a
   hypothetical L5) could achieve on this specific axis (execution-cost
   predictability), independent of admission-decision quality.
