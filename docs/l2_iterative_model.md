# L2: iterative analytical purification model

## The gap L2 targets

`docs/false_rejection_root_cause.md` established that L1
(`planning.purification.PurifyUntilTarget`) estimates post-purification
fidelity using **exactly one** analytical round of
`BBPSSWCircuit.improved_fidelity`, while SeQUeNCe's real
`purification_mode='until_target'` applies potentially several rounds at
execution time. Any `min_fidelity` above the one-round ceiling
(`0.7202522030749277` on the three-node chain) is rejected by L1
deterministically, regardless of proximity to that ceiling - confirmed as
a 100% false-rejection rate over 240 oracle-tested trials.

## The formula

`BBPSSWCircuit.improved_fidelity` (Dür and Briegel 2007, formula 18,
`sequence/entanglement_management/purification/bbpssw_circuit.py:134-143`):

```
f' = (f^2 + ((1-f)/3)^2) / (f^2 + 2f(1-f)/3 + 5((1-f)/3)^2)
```

For `f > 0.5` this is a contraction toward the fixed point `f = 1`: each
application strictly increases fidelity, with diminishing gains as `f`
approaches 1. L1 applies this once; L2
(`planning.planners.l2_iterative.IterativeAnalyticalPurification`) applies
it repeatedly, feeding each round's output back in as the next round's
input, exactly mirroring what a real multi-round `until_target` purification
attempt does to a memory's fidelity on repeated success
(`bbpssw_circuit.py:120`, `self.kept_memo.fidelity =
self.improved_fidelity(self.kept_memo.fidelity)`).

## Pair cost

Each round consumes two input pairs (one kept and improved, one measured
and discarded - `bbpssw_circuit.py`'s `received_message`) to produce one
higher-fidelity output pair. L2 tracks `cumulative_pair_cost` as
`2^rounds` - a purely combinatorial, analytical accounting, not a
prediction of how many elementary-generation ATTEMPTS are needed to
produce that many raw pairs in the first place (attempt-level modeling is
out of scope for L2 - see `docs/l3_probabilistic_model.md`, once written).

## Stopping conditions (all three are real, not arbitrary truncations)

1. **Target reached**: `output_fidelity >= target_fidelity` - success.
2. **`max_rounds` exceeded** (default 8): a hard cap: unbounded analytical
   iteration is not a meaningful planning-time computation, and no real
   `until_target` deployment retries indefinitely either.
3. **`max_pair_cost` exceeded** (optional, `None` by default = unbounded):
   marks the estimate `resource_feasible=False` once the projected pair
   cost would be impractical given the reservation's actual memory
   allocation - a resource-awareness knob future P0x campaigns can sweep.
4. **Fixed-point detection** (`output_fidelity <= current_fidelity +
   1e-12`): as `f` approaches 1, floating-point gains per round shrink to
   numerical noise; this stops the loop from spinning uselessly near the
   fixed point rather than silently truncating before a genuinely
   reachable target. Verified in
   `tests/planning/planners/test_l2_iterative.py::test_fixed_point_detection_stops_before_max_rounds_near_unity`.

## What L2 deliberately does NOT model

- **Round success probability**: `PurificationRoundEstimate.
  estimated_success_probability` is always `None` at L2 - a round's real
  success depends on the quantum measurement statistics SeQUeNCe's
  circuit simulation resolves (`bbpssw_circuit.py`'s `meas_res ==
  msg.meas_res` check), which this closed-form model does not attempt to
  predict. L3 introduces an approximate probability model instead (see
  `docs/l3_probabilistic_model.md`, added after checkpoint 1) - L2 is
  intentionally silent here rather than guessing.
- **SeQUeNCe's internal retry/failure accounting**: a failed purification
  round in SeQUeNCe consumes pairs without improving fidelity and the
  reservation's resource manager decides whether to retry; L2 assumes
  every modeled round succeeds (an optimistic, not conservative,
  assumption relative to L1's "assume purification barely works" framing)
  - explicitly NOT a re-derivation of SeQUeNCe's internal loop (see
  `planning.purification`'s module docstring on why that would require
  bypassing the reservation API).

## Audit: is `2^rounds` computed correctly? (requested after checkpoint 1)

Verified directly: `cumulative_pairs` starts at 1 and is multiplied by
`PAIR_CONSUMPTION_PER_ROUND=2` once per round, giving exactly `2^rounds`
at every step (checked round-by-round up to round 8: 2, 4, 8, 16, 32, 64,
128, 256 - all match `2**round_index` exactly). No double exponentiation,
no formula bug. Python's arbitrary-precision integers mean no silent
overflow either: forcing `max_rounds=100` with a near-unity target
(0.999999999) converges after 69 rounds at `cumulative_pair_cost =
2**69 ≈ 5.9e20` without crashing or wrapping.

**That number itself is the real problem, not a bug in computing it**:
`2**69` raw pairs is physically meaningless (no real reservation window
could produce anywhere near that many elementary pairs), yet
`IterativeAnalyticalPurification` reports `target_reached=True,
resource_feasible=True` for it whenever `max_pair_cost=None` (the
parameter's default, and what every P01/P02 campaign actually used).
`max_pair_cost` exists on the class specifically to cap this, but was
never wired to anything physically meaningful (like the intent's
`reserved_memory_slots` or a generation-rate-derived budget) - this is
exactly the gap `docs/l2_resource_aware_model.md` (L2-R) closes.

## Empirical result at checkpoint 1 (P01)

See `docs/planner_study_findings_checkpoint1.md` for the full P01
comparison. Two distinct outcomes, both real (not cherry-picked):

- **Three-node chain**: L2 (2 rounds, ~0.7572 estimated fidelity) resolves
  the entire previously-100%-false-rejected range (`min_fidelity`
  0.73-0.75), confirmed SATISFIED against real SeQUeNCe execution.
- **Four-node chain**: L2 trades false REJECTION for a DIFFERENT failure
  mode. At `min_fidelity` 0.65-0.73, L2 accepts (where L1 rejects
  everything, matching F03 exactly) but the real execution comes back
  **VIOLATED**, not SATISFIED - `delivered_pairs` is 0-1 against a
  `min_delivered_pairs=10` goal. Cause: `cumulative_pair_cost` grows as
  `2^rounds` (up to `2^8=256` at the `max_rounds=8` cap), and this
  analytical model never checks that projected cost against the
  intent's actual `reserved_memory_slots`/`duration_s` - `max_pair_cost`
  exists on `IterativeAnalyticalPurification` precisely for this, but P01
  ran with the class's default (`max_pair_cost=None`, unbounded). At
  `min_fidelity` >= 0.735, L2 still REJECTS on this topology (8 rounds
  reaches only ~0.7315, short of 0.735) - L2 does not universally resolve
  false rejections; it has its own limits, topology-dependent, exactly as
  the planner-study brief warned not to assume away.

This is the central checkpoint-1 finding: increasing purification-round
fidelity (L1 -> L2) measurably helps in one topology and trades one
failure mode for another in a second - never assume a "more sophisticated"
analytical model is strictly better without checking what it costs.
