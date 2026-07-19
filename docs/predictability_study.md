# Predictability limits of quantum intent planning (M9)

## Scope and standing constraints

This phase begins after Checkpoint 2B's **NOT READY** verdict
(`docs/planner_study_findings_checkpoint2b.md`). The entire planner
family (L1, L2, L2-R, L3, L3-R, L4) is now **frozen** - no algorithm,
threshold, or prior campaign result (P01, P02, P02B, P03) is modified in
this phase. Every M9 experiment writes to new directories
(`results/predictability/`) under new manifests
(`configs/campaigns/predictability/`).

Central question (reframed from "which planner is best" to "how much of
the remaining error is even reducible"):

> How much of the observed planning error is caused by planner
> limitations, and how much is inherent to the simulated network's own
> stochastic variability - and does that leave room for a
> learning-based planner (L5) to add value?

## Foundational finding: `operational_seed` does not fully control determinism

Before running any new campaign, investigating the P02B outlier trial
(`P02b_resource_aware_planners:four_node:e961642e2e5e233b:L3:7:
p02b-intent` - `requested_fidelity=0.60`, four-node chain,
`reserved_memory_slots=10`, `duration_s=0.05`, `purification_rounds_
estimate=4`, real `simulation_wall_time_s=48723.04` / ~13.5h) surfaced a
result that materially shapes this whole phase's methodology.

**Attempting to reproduce that exact trial (same topology, route, seed,
intent) in isolated fresh processes never reproduced anything close to
48723s** - seven separate reruns gave wall times of 3.1s, 10.67s, 11.14s,
10.65s, 11.22s, 11.24s, 7.75s (with `random.seed()` explicitly forced to
a fixed value in three of those, which did not remove the variance
either). The `final_status`/`delivered_pairs` outcome was stable
(VIOLATED, 4 pairs) across all these reruns - only the real wall-clock
cost varied.

**Root cause**: `SequenceAdapter`/`NetworkTopologySpec.
to_router_net_topo_config` deterministically seed each node's and each
link's own `numpy.random.default_rng` generator from `operational_seed`
(`seed + index`, verified in `network/topology.py`) - this part IS fully
reproducible. But SeQUeNCe's `sequence.kernel.quantum_utils` module (a
third-party dependency, never modified here) draws from Python's
**global** `random` module directly (`random.random()`/`random.uniform()`
at module level) for some physical sampling, instead of going through an
entity's `get_generator()`. Our adapter never reseeds this global module,
so:

- In a **fresh process**, Python's global `random` module auto-seeds
  from OS entropy on first use - different every run, regardless of
  `operational_seed`.
- In a **long-running campaign process** (P01-P02B all ran hundreds to
  thousands of trials sequentially in one process), this global state
  keeps advancing across every prior trial, in whatever order they ran -
  so trial *N*'s outcome can depend on trials *1..N-1*, not just its own
  declared seed.

**This is a genuine, previously undocumented limitation of the
planner-family study's reproducibility** (P01-P02B's results are not
retroactively altered or invalidated by this - they are real, valid
observations of what actually happened; this caveat affects how
precisely any ONE of their trials could be reproduced on demand, not
whether the aggregate statistics reported are real).

**Mitigation adopted for M9 only** (`experiments/predictability_runner.
execute_predictability_trial`): Python's global `random` module is
explicitly reseeded (`random.seed(operational_seed + RNG_RESEED_OFFSET)`)
immediately before every M9 trial - a composition-layer call to
SeQUeNCe's own public API from our code, not a modification of SeQUeNCe's
source. This does not achieve perfect determinism (informal testing
still showed some residual wall-time variance even with this reseed -
plausibly from other unseeded draws, or from genuine event-order
sensitivity to sub-microsecond timing elsewhere), but is a real
improvement over no reseeding at all, and is documented rather than
silently assumed to have fully solved the problem.

**Implication for this phase's scientific question**: some of what looks
like "intrinsic network variability" driven by `operational_seed` is, in
the current codebase, actually variability from an UNCONTROLLED source
(the global `random` leak) that is not conceptually different from
aleatoric physical randomness for the purposes of this study (both are
"not knowable/controllable before execution" from the planner's point of
view) - but it does mean `operational_seed` is a narrower knob than its
name implies, and this is disclosed rather than glossed over.

## Safety infrastructure: mandatory per-trial wall-clock cap

Every M9 trial is deliberately probing regions the planner family's own
checkpoint 2B flagged as risky (marginal fidelity/purification regimes).
Given the demonstrated ~48723s real-world outlier, **no M9 trial ever
runs uncapped**:

- `scripts/run_predictability_trial_worker.py` runs exactly one trial and
  exits (used only as a subprocess target, never imported).
- `scripts/predictability_common.run_trial_with_timeout` invokes it via
  `subprocess.run(..., timeout=timeout_s)` - a hard, OS-level wall-clock
  cap (Python's discrete-event loop cannot be cooperatively interrupted,
  and Windows has no `signal.alarm`, so a subprocess is the only reliable
  mechanism).
- A trial that exceeds the cap is recorded with `final_status="TIMEOUT"`,
  `timed_out=True`, and `simulation_wall_time_s=timeout_s` - an explicit
  **censored** value (a lower bound on the true time, never treated as
  the actual completion time in any statistic).

This was validated directly: a deliberately tight 1.5s cap on a ~4s-real
trial correctly produced `TIMEOUT`/`timed_out=True` at ~1.5s wall time,
and a normal 8-30s cap on the same configurations let them complete
normally.

## Campaigns

| Config | Section | Status |
|---|---|---|
| `P04_retry_storm.yaml` | 5 - retry storm | **Complete** (40/40 trials, 0 timeouts, 0 storms reproduced - see `docs/retry_storm_analysis.md`) |
| `P02_variance.yaml` | 1 - intrinsic variability | **Complete** (200/200 trials, 0 duplicates, 0 timeouts; disclosed reduction from 100/250/500 to 100 seeds x 2 intents) |
| `P01_predictability.yaml` | 6 - critical regions | Config written; not executed this pass - P04's own fidelity sweep already characterizes the sharp satisfaction/violation transition on four_node (`docs/retry_storm_analysis.md`), judged sufficient signal for this phase's verdict without the additional distance-axis trials |
| `analyze_predictability_limits.py` (sections 3/4/7) | information levels, variance decomposition | **Complete** - reuses existing frozen P02B/P03 data, no new simulation (`results/predictability/processed/information_level_comparison.csv`, `variance_decomposition.csv`) |

Final synthesis: `docs/predictability_final_report.md` (sections 8-10) -
verdict: **L5 NOT SCIENTIFICALLY JUSTIFIED YET**.

## L4 reframing (section 8)

L4 is no longer described as "the best planner" - it is the **Reference
Planner**: a policy that approximates a many-internal-simulations
decision rule, used as the highest-information comparison point every
other planner level is measured against, not a deployment recommendation
in its own right (its own cost profile, documented in P03/checkpoint 2B,
remains the reason it isn't simply adopted outright).

## Remaining sections

Sections 2 (upper bound / uncertainty decomposition), 3-4 (information
oracle / information value), 7 (variance decomposition / ANOVA), and the
final L5 criterion (section 9) and deliverable (section 10,
`docs/predictability_final_report.md`) are addressed after the campaigns
above produce data - this document is updated as each section
completes, not written in advance of the evidence.
