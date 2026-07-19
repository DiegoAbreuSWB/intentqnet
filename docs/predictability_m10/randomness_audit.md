# Randomness source audit (M10.1)

Reproducible via `scripts/audit_randomness_sources.py` (static grep across
`src/ibqn/` and `SeQUeNCe/sequence/`, plus a dynamic monkeypatch-and-run
verification on one real trial - never touches P01-P02B/P03/M9 data).

## Correction of an M9 claim

M9 (`docs/predictability_study.md`) concluded that `sequence.kernel.
quantum_utils`'s use of Python's bare `random` module explained the
observed wall-time variance across repeated "identical" trials, and that
this meant `operational_seed` did not fully control determinism. **This
audit does not support that specific mechanism** and downgrades that
claim from SUPPORTED to NOT SUPPORTED (see `m9_conclusion_audit.md` for
the formal per-claim classification):

- `quantum_utils.random_state()` (the function M9 pointed to) has **zero
  call sites anywhere in SeQUeNCe's shipped code** - it is dead code for
  every configuration this project uses, not merely unused by IBQN.
- A dynamic audit (monkeypatching `random.random`/`.choice`/`.seed`/
  `.uniform`/`.shuffle`, running the exact trial M9 investigated -
  four-node chain, L3, seed=7, `min_fidelity=0.6`) recorded **zero calls**
  to any of these during a real trial. The bare `random` module is
  genuinely never drawn from in IBQN's simulation path.
- Repeating that same configuration under three different
  `PYTHONHASHSEED` values (0, 1, 42) produced **identical** `final_status`
  and `delivered_pairs` in all three, and consistently fast wall times
  (~1.85-1.88s) - no observed sensitivity to hash randomization for this
  configuration.

**What M9 got right, even though the specific mechanism was wrong**: the
observed wall-time variance across reruns (3.1s-11.2s in M9's informal
tests) was real and reproducible as a *phenomenon* - it just was not
caused by the bare `random` module. The current best explanation,
consistent with everything below, is ordinary system-level timing noise
(concurrent processes, OS scheduling) rather than a different physical
trajectory - **the underlying simulation appears to be genuinely
deterministic given a fixed seed**, pending the formal replay validation
(M10.3) that supersedes this informal finding.

**The ~48723s P02B outlier remains unexplained** by this audit. It is
explicitly NOT attributed to the (now-refuted) `quantum_utils` mechanism.
Root-causing it is scheduled for M10.8 (tail-event instrumentation) with
proper heartbeat/no-progress/event-count instrumentation, per the
project's phased order - this document does not attempt to resolve it.

## Source table

| Source | File/function | RNG type | Seeded? | Controlled by `operational_seed`? | Action |
|---|---|---|---|---|---|
| Python `random` module (bare, global) | `beam_splitter.py`, `transducer.py`, `transmon.py`, `quantum_utils.py:random_state` (never called), `qkd/cascade.py` | global stdlib `random` | No | N/A - dynamically confirmed **0 calls** during a real IBQN trial; none of these components are on the ket-vector/BSM/BBPSSW/swapping path IBQN topologies use | None needed - dormant/unused for current IBQN usage, documented not silently dismissed |
| `Timeline.seed()` | `kernel/timeline.py:166` (calls global `random.seed`) | global stdlib `random`, via SeQUeNCe's own public API | Only if called | No - `SequenceAdapter` never calls it | Not required (bare `random` unused in our path), but `DeterministicExecutionContext` (M10.2) calls it anyway for defense-in-depth |
| Per-node/per-link `numpy.random.default_rng(seed)` | `topology/node.py:72,86,773,780`, seeded via `NetworkTopologySpec.to_router_net_topo_config`'s `seed + index` | `numpy.random.Generator` | **Yes**, deterministically from `operational_seed` | **Yes** - confirmed this is the actual source of every physical sampling event exercised in a real trial (BSM success/loss, BBPSSW/swapping measurement outcomes, optical-channel loss), all routed through `Entity.get_generator()` | None needed - already correctly controlled; this is the primary reproducibility mechanism |
| `Entity.get_generator()` fallback | `kernel/entity.py:100,161` (`return default_rng()` when `owner` lacks `get_generator`) | `numpy.random.Generator` | No (OS entropy) | Not exhaustively tested for every entity type - no entity was observed hitting this fallback in the audited trial | Flagged as a residual, not-fully-ruled-out risk; documented in `DeterministicExecutionContext` |
| qutip's module-level `_RAND` singleton | `qutip/random_objects.py:28` (third-party, via `qutip_qip`, imported transitively) | `numpy.random.Generator` | No (unseeded at import time) | No, but dynamically confirmed **dormant** - its bit-generator state does not change during a real trial (never sampled from) | None - confirmed inert, documented rather than ignored |
| `scipy.stats` sampling (`.rvs()`) | N/A | N/A | N/A | N/A - L3/L3-R only call `.sf`/`.ppf` (deterministic distribution functions), never `.rvs()` | None needed |
| Legacy `numpy.random.*` globals (`np.random.seed`, `.rand`, ...) | 0 occurrences found in `sequence/` or `src/ibqn/` | N/A | N/A | N/A - dynamically confirmed 0 calls during the audited trial | None needed |
| `PYTHONHASHSEED` / set-dict iteration order | Process-wide interpreter setting | hash seed | Not fixed by default | No - independent of `operational_seed` | Tested directly (3 values) on the audited trial: identical outcome in all three; not proven absent for every configuration (untested on topologies with multiple candidate routes, where set/dict ordering of candidates could in principle matter) - `DeterministicExecutionContext` pins it where possible |
| Threading / multiprocessing | `quantum_manager/base.py:19,47` - a `threading.Lock` guarding a global formalism setting only | N/A | N/A | N/A - no concurrent execution within a trial | None needed |
| Time-derived seeds / `secrets` / `os.urandom` | 0 occurrences found | N/A | N/A | N/A | None needed |

## Known limitations of this audit (disclosed, not hidden)

1. **`Entity.get_generator()`'s unseeded fallback was not exhaustively
   tested** across every entity/component type IBQN's four topologies
   instantiate - only confirmed absent for the one configuration
   dynamically audited. A different topology or component combination
   could still hit it.
2. **`PYTHONHASHSEED` sensitivity was tested on a linear chain (only one
   candidate route)** - a topology with multiple candidate routes (the
   diamond or small-mesh topologies, where `IntentPlanner`'s candidate
   enumeration could plausibly iterate a set/dict whose order depends on
   hash seed) was not tested here. `DeterministicExecutionContext` pins
   `PYTHONHASHSEED` regardless, closing this gap going forward even
   though it was not proven to matter.
3. **This audit ran ONE trial.** The formal replay-determinism campaign
   (M10.3, `P10_replay_determinism.yaml`) is the rigorous test - running
   the same nominal trial 10 times across multiple topologies and
   purification regimes and comparing logical outputs - and is what
   Checkpoint M10-A's verdict is actually based on, not this audit alone.
