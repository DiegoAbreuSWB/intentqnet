# L2-R: resource-aware iterative analytical planner

## The gap L2-R closes

Checkpoint 1 (`docs/planner_study_findings_checkpoint1.md`) found L2 fully
resolves the three-node chain's false rejections, but on the four-node
chain trades REJECTED for VIOLATED: it accepts intents whose fidelity
target is reachable but whose delivery target (`min_delivered_pairs`)
cannot actually be met within the reservation window, because L2's
purification-round estimate never checks the resulting pair cost against
ANY resource constraint (`max_pair_cost` exists on
`IterativeAnalyticalPurification` but defaults to `None`/unbounded, and
was never wired to anything in P01/P02).

## Three resources, never conflated

The planner-study brief explicitly warns against
`required_pairs <= reserved_memory_slots` as a single, conflated check.
L2-R keeps three distinct quantities apart:

1. **Peak simultaneous memory occupancy** (`peak_memory_slots_required`):
   how many memories must be held AT ONCE. A purification round needs 2
   (kept + measured - `bbpssw_circuit.py`'s `received_message`, which
   measures one memory while keeping/improving the other); with no
   purification, 1 suffices. This is a snapshot requirement, constant
   regardless of how many total rounds run over time - `2`, never
   `2**rounds`.
2. **Cumulative raw-pair consumption** (`structural_raw_pairs_per_final_
   pair` = `2**rounds`, `expected_raw_pairs_per_final_pair` = the same
   inflated by the Dur-Briegel round success probability, exactly as L2/L3
   already compute it - reused, not re-derived): the TOTAL number of
   elementary pairs consumed, across all rounds, to produce ONE final
   purified pair. Audited (`docs/l2_iterative_model.md`) and confirmed
   correct (`2**rounds`, no double exponentiation) - the gap was never a
   computation bug, only the absence of any check against it.
3. **Generation capacity within the reservation window**
   (`estimated_generation_rate`, `estimated_max_delivered_pairs`): how
   many elementary pairs the route can plausibly produce in `duration_s`,
   which - divided by (2)'s pair cost - bounds how many FINAL pairs can
   be delivered, and thus whether `min_delivered_pairs` is achievable at
   all.

`reserved_memory_slots` is a snapshot pool size reused many times over the
window (memories are recycled as attempts succeed/fail) - it constrains
(1), not (2) or (3) directly.

## The four specific feasibility gates

```
feasible = fidelity_feasible AND memory_feasible AND duration_feasible AND delivery_feasible
```

Each has its own specific rejection reason - never a single generic
string:

| Gate | Reason if failed |
|---|---|
| Fidelity target unreachable within `max_rounds` | `TARGET_FIDELITY_UNREACHABLE` |
| `reserved_memory_slots < peak_memory_slots_required` | `INSUFFICIENT_PEAK_MEMORY` |
| Route can't generate any raw pairs (e.g. disconnected/zero transmission) | `INSUFFICIENT_GENERATION_CAPACITY` |
| Fidelity and memory both fine, but `estimated_max_delivered_pairs < requested` | `DELIVERY_TARGET_EXCEEDS_WINDOW` |
| Structural pair cost saturates (`> MODEL_MAX_STRUCTURAL_PAIR_COST=10000`) | `MODEL_LIMIT_REACHED` |

## Generation-rate model (a documented stopgap, not a validated correction)

`estimate_resource_aware_plan` reuses the same naive attempt-rate formula
L3 uses (`reserved_memory_slots / (2 * classical_delay_s)`), but divides
it by `ATTEMPT_RATE_CONSERVATIVE_FACTOR = 4.5` - the high end of the
2.4-4.3x overestimate already found by comparing that naive formula
against real F02 campaign data (`docs/l3_probabilistic_model.md`),
rounded up for a safety margin. This is a deliberate, conservative
correction in the SAFE direction (under-estimating capacity, so L2-R
fails closed - rejects a plan that might actually have worked - rather
than failing open): **it is explicitly a stopgap**, not the outcome of
the formal audit (`docs/l3_attempt_rate_audit.md`). Both L2-R's and
L3-R's generation-rate models should be revisited together once that
audit's root cause is confirmed.

## Validation against checkpoint 1's exact regression

- **Three-node chain** (`min_fidelity` 0.65-0.73): L2-R accepts every
  case L2 accepted - the genuine checkpoint-1 win is preserved, not
  regressed (`tests/planning/planners/test_l2_resource_aware.py::
  test_l2r_still_accepts_the_three_node_chain_where_l2_succeeded`).
- **Four-node chain** (`min_fidelity` 0.65, `reserved_memory_slots=10`,
  `min_delivered_pairs=10`, `duration_s=0.1` - the exact case checkpoint 1
  found VIOLATED under L2): L2-R rejects with
  `DELIVERY_TARGET_EXCEEDS_WINDOW` (`test_l2r_rejects_the_four_node_
  chain_where_l2_would_violate`) - converting a false ACCEPT into an
  honest, specifically-reasoned REJECT.

## What L2-R does NOT fix

L2-R is still a deterministic, point-estimate planner - it does not
quantify uncertainty in its generation-capacity estimate (that is L3-R's
job, built on this same resource model - see `docs/l3_resource_aware_model.md`
once written) and its conservative correction factor is a stopgap, not a
validated physical model. A rejected-by-L2-R intent might still be
genuinely satisfiable with a less conservative (but unvalidated) capacity
estimate - P02B's comparison against L4 (which uses real internal
simulation, not an analytical formula) is where this gets checked
empirically.
