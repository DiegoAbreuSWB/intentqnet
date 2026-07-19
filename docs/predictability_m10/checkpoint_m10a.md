# Checkpoint M10-A — Reproducibility

Covers M10.1 (randomness audit), M10.2 (`DeterministicExecutionContext`),
and M10.3 (replay-determinism validation). All new artifacts live under
`configs/campaigns/predictability_m10/`, `results/predictability_m10/`,
`docs/predictability_m10/`, `tests/experiments/predictability_m10/` -
P01-P02B/P03 (planner-family study) and M9's own campaigns are untouched
(verified by `tests/experiments/predictability_m10/
test_old_campaigns_unaffected.py`'s frozen row-count guards, 8/8 passing).

## Complete randomness inventory

Full table: `docs/predictability_m10/randomness_audit.md`. Summary:

| Source | Seeded? | Actually drawn from in a real trial? |
|---|---|---|
| Per-node/per-link `numpy.random.default_rng(seed)` | Yes, from `operational_seed` | **Yes - the only source confirmed to drive physical sampling** (BSM, BBPSSW, swapping, optical-channel loss, all via `Entity.get_generator()`) |
| Bare Python `random` module (`quantum_utils.random_state`, `beam_splitter`, `transducer`, `transmon`, `qkd/cascade`) | No | **No - dynamically confirmed 0 calls** during a real trial; dead code for IBQN's ket-vector/BSM/BBPSSW/swapping path |
| qutip's module-level `_RAND` singleton | No (OS entropy at import time) | **No - confirmed dormant**, its bit-generator state never changes during a real trial |
| Legacy `numpy.random.*` globals | N/A | 0 calls observed |
| `scipy.stats` sampling (`.rvs()`) | N/A | Never called - L3/L3-R only use deterministic `.sf`/`.ppf` |
| `PYTHONHASHSEED` | Not fixed by default | Tested at 3 values on one configuration - no observed sensitivity, but not exhaustively tested on multi-route topologies |
| `Entity.get_generator()`'s unseeded fallback | No | Not observed triggering in any audited trial - not exhaustively ruled out for every entity type |
| Threading/multiprocessing | N/A | A `Lock` for a global formalism setting only - no concurrent execution within a trial |

**Important correction of an M9 claim**: M9 attributed observed wall-time
variance to `quantum_utils.py`'s use of the global `random` module. This
audit does not support that mechanism (zero calls, dead code) - see
`randomness_audit.md`'s "Correction of an M9 claim" section. The
~48723s P02B outlier remains **unexplained**, explicitly deferred to
M10.8 (tail-event instrumentation), not resolved here.

## Seed mapping (`DeterministicExecutionContext`, M10.2)

`master_seed` → SHA-256(`campaign_id | trial_id | namespace | master_seed`)
→ one 64-bit seed per namespace (`execution`, `generation`, `swap`,
`purification`, `planner`, `internal_simulation`, `instrumentation`).
Only `execution` is actually wired into `SequenceAdapter(seed=...)` -
SeQUeNCe's architecture gives one generator per node, not one stream per
physical process, so the other six namespaces are recorded in
`RngManifest`/`rng_manifest` for provenance and future extensibility,
not separately injected - a disclosed design limit, not a silent gap
(`deterministic_context.py`'s module docstring). `PYTHONHASHSEED` is
pinned (`"0"`) only in subprocess children this context launches - it
cannot be changed for an already-running process (documented, not worked
around). Verified: `determinism.enabled=false` (the default) is a
complete no-op - existing campaigns are provably unaffected.

## Replay results

`scripts/run_p10_replay_determinism.py`: 8 configurations (three-node,
four-node, diamond, small-mesh, purification disabled, purification
automatic/1-round, a multi-round-purification case, and the exact
previously-slow P02B outlier configuration - four_node/L3/seed=7/
fidelity=0.6/`admission_threshold=0.0`), each replayed 10 times with
`determinism` both disabled and enabled (160 trials total, 0 duplicates
after a fix - see below, 0 timeouts).

| Configuration | Scenario | Planner | Determinism | Classification |
|---|---|---|---|---|
| three_node_baseline | three_node | L2 | off / on | BITWISE_IDENTICAL / BITWISE_IDENTICAL |
| four_node_baseline | four_node | L2 | off / on | BITWISE_IDENTICAL / BITWISE_IDENTICAL |
| diamond_baseline | diamond_heterogeneous | L2 | off / on | BITWISE_IDENTICAL / BITWISE_IDENTICAL |
| small_mesh_baseline | small_mesh | L2 | off / on | LOGICALLY_IDENTICAL / LOGICALLY_IDENTICAL (all 10 REJECTED, no trajectory to hash) |
| purification_disabled | three_node | L2 | off / on | BITWISE_IDENTICAL / BITWISE_IDENTICAL |
| purification_automatic_one_round | three_node | L2 | off / on | BITWISE_IDENTICAL / BITWISE_IDENTICAL |
| multi_round_purification | four_node | L2 | off / on | BITWISE_IDENTICAL / BITWISE_IDENTICAL |
| **previously_slow_case** | four_node | L3 | off / on | **BITWISE_IDENTICAL / BITWISE_IDENTICAL** |

**16/16 groups classified BITWISE_IDENTICAL or LOGICALLY_IDENTICAL. 0
NONDETERMINISTIC.** Full data: `results/predictability_m10/processed/
replay_determinism_report.csv`, raw trials: `results/predictability_m10/
raw/P10_replay_determinism/trials.csv`.

Critically, `previously_slow_case` - the exact configuration that produced
the ~48723s P02B outlier - was **BITWISE_IDENTICAL across all 10 replays,
in both determinism modes**, and never approached that wall time (all
replays completed in a few seconds). This is consistent with the M10.1
finding that the underlying physics is properly seeded and deterministic;
it does NOT explain why the original P02B run took ~48723s once - that
remains open for M10.8.

## Trajectory hashes

`compute_trajectory_hash` (SHA-256 over `final_status`, `delivered_pairs`,
`average_fidelity` (rounded to 9 decimals), `route`, `eg/ep/es_attempts`/
`_success`, `timeline_end_time_s` - explicitly EXCLUDING wall-clock time
and any timestamp) was used as the primary replay-comparison evidence,
per section 5's explicit instruction not to use wall time as evidence of
determinism. 14/16 groups had a literal single trajectory_hash across all
10 replays; the 2 `small_mesh_baseline` groups had no trajectory to hash
at all (consistently REJECTED before any simulation ran) but were
classified LOGICALLY_IDENTICAL on consistent categorical outcome.

## A real bug found and fixed during this milestone

The first P10 run produced 144/160 duplicate `trial_id` values - not a
data-corruption issue (every OTHER field, including `replay_index`
itself, was correctly distinct per row), but `PredictabilityM10TrialRecord.
trial_id` was built directly from `TrialIdentity.trial_id` (the shared,
frozen schema used by every prior phase), which has no concept of
`replay_index` at all - collapsing all 10 replays of one configuration
onto a single `trial_id`. Fixed by appending `:{replay_index}` in
`predictability_m10_runner.py` (never modifying the shared, frozen
`TrialIdentity`), the already-collected P10 data was corrected in place
(a legitimate fix to M10's own not-yet-analyzed data, not a frozen
prior-phase result), and a regression test
(`test_replay_index_produces_distinct_trial_ids`) now guards against a
recurrence. This is disclosed here rather than silently corrected,
because it is exactly the kind of resume-safety bug section 20 of the
governing brief asked to be tested for.

## Remaining nondeterminism / disclosed limitations

Not fully closed by this checkpoint:

1. `Entity.get_generator()`'s unseeded fallback (`kernel/entity.py:100,161`)
   was never observed triggering, but was not exhaustively tested across
   every entity/component type IBQN's four topologies instantiate.
2. `PYTHONHASHSEED` sensitivity was tested on a linear chain (single
   candidate route) in M10.1's dynamic audit; P10 additionally covers
   diamond and small-mesh (topologies with genuinely multiple candidate
   routes) at 10 replays each, and found no sensitivity there either -
   this substantially closes the gap flagged in M10.1, though still only
   at one seed per topology.
3. The ~48723s P02B outlier is unexplained - explicitly deferred to
   M10.8, not something this checkpoint claims to resolve.
4. Only one operational seed (7) was used across all P10 replays -
   reproducibility was tested for "same seed, same trajectory", not yet
   across many different seeds at scale (that is M10.4-M10.6's job).

## Verdict

**REPRODUCIBLE.**

Justification: 0 of 16 tested (configuration x determinism-mode) groups
showed any logical disagreement across 10 replays, using wall-clock-free
trajectory-hash evidence as mandated. This includes the exact
configuration responsible for the one confirmed anomaly in this entire
study (the P02B retry-storm trial), which was perfectly reproducible in
this controlled test. The randomness audit independently corroborates
this: the only randomness source confirmed to drive physical sampling
(per-node `numpy.random.default_rng`) is properly seeded from
`operational_seed`, and every other candidate source was dynamically
confirmed dormant or unused.

**Experiments MAY proceed to M10.4 (boundary search) once explicitly
authorized** - per the governing brief's own ordering, this checkpoint
does not itself authorize continuation; it reports that the
prerequisite (logical replay determinism) is satisfied.
