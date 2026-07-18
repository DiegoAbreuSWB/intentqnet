# Planner levels (L1-L5): common interface and design decisions

## The common interface

`src/ibqn/planning/planners/base.py` defines `IntentPlannerPolicy`:

```python
class IntentPlannerPolicy(Protocol):
    name: str
    level: str

    def plan(
        self,
        intent: EntanglementIntent,
        network_state: NetworkCapabilities,
        candidate_paths: list[list[str]],
        context: PlanningContext,
    ) -> PlannerDecision: ...
```

`network_state` is the existing `network.capabilities.NetworkCapabilities`
- no new, duplicate "network state" type was introduced. `candidate_paths`
is generated ONCE, outside any policy, by
`base.generate_candidate_paths(intent, network_state, context)`, which
itself delegates entirely to `context.routing_strategy` (the existing
`planning.routing.RoutingStrategy` interface) - so candidate-path
generation is never duplicated per planner level, and every level under
comparison sees the exact same candidate set for a given intent/topology.

`PlannerDecision` (in `planners/models.py`) wraps a real
`planning.models.ExecutionPlan` in `selected_plan` - the same type
`execution.sequence_executor.SequenceExecutor.deploy()` already consumes.
A `PlannerDecision` is always directly deployable; no adapter layer sits
between the planner family and the rest of IBQN.

Fields a planner level cannot predict are `None`, never a guessed number
or `0` (e.g. L1 never sets `predicted_satisfaction_probability` -
see `tests/planning/planners/test_l1_regression.py::test_l1_never_predicts_fields_it_has_no_basis_for`).

## Why L1/L2 wrap `IntentPlanner` instead of reimplementing it

`planning.planners.l1_conservative.ConservativeOneRoundPlanner` and
`planning.planners.l2_iterative.IterativeAnalyticalPlanner` both
internally construct and call the existing `planning.planner.IntentPlanner`
- L1 with `PurifyUntilTarget` (unchanged), L2 with the new
`IterativeAnalyticalPurification` (a drop-in replacement, same
`PurificationStrategy` interface). This is a deliberate design choice, not
a shortcut:

1. **L1 must reproduce history exactly.** The only way to GUARANTEE
   byte-for-byte identical decisions to every F01-F08 trial is to call the
   literal, already-tested code path - not a parallel reimplementation
   that could drift, however carefully written. See
   `tests/planning/planners/test_l1_regression.py`.
2. **Zero duplication of candidate generation, resource validation, or the
   base fidelity model** (planner-study brief, section 3's explicit
   requirement) - `IntentPlanner.plan()` already composes
   `planning.routing`, `planning.feasibility.evaluate_route`,
   `planning.resource_allocation.build_reservations` correctly; wrapping it
   reuses all of that for free.

`IntentPlanner.plan()` regenerates its own candidate routes internally
(from the same `context.routing_strategy` instance) rather than accepting
a pre-computed list, so the `candidate_paths` argument L1/L2 receive is
used only to populate `PlannerDecision.candidate_evaluations` for
analysis/explainability - never re-passed into `IntentPlanner`. Since
route generation is a deterministic, pure function of the topology and
strategy, the routes `IntentPlanner` regenerates are identical to
`candidate_paths` by construction; this is exercised (not just asserted)
by `test_l1_regression.py`, which compares an `IntentPlanner.plan()` call
directly against `ConservativeOneRoundPlanner.plan()`'s output on the same
inputs.

This wrapping approach stops being appropriate once a level's decision
process no longer fits `IntentPlanner`'s "one deterministic estimate per
candidate route" shape - L3 (probabilistic), L4 (simulation-in-the-loop),
and L5 (learned) will need genuinely different internal logic, though
they will still call `base.generate_candidate_paths`/`evaluate_candidates`
for the parts that are still shared (see each level's own doc, added
after checkpoint 1).

## Why L2 is ALSO registered as a `sweeps.PURIFICATION_POLICIES` entry

`IterativeAnalyticalPurification` implements the existing
`planning.purification.PurificationStrategy` interface, so it can be
plugged into `IntentPlanner` exactly like `PurifyUntilTarget`/`NeverPurify`
already are. Registering it as `"iterative_analytical"` in
`experiments.sweeps.PURIFICATION_POLICIES` (additively - `"disabled"`/
`"automatic"` keep their exact prior meaning and F01-F08 configs never
reference the new name) lets campaign P01 run through the existing,
already-tested `CampaignRunner`/YAML pipeline completely unchanged -
manifests, resumability, `TrialRecord` persistence, `continue_on_error`,
everything - with zero modification to `experiments/runner.py`.

This means P01's bulk data collection (20 seeds x 8 fidelity thresholds x
2 topologies x 2 policies = 640 trials) happens through the mature
campaign infrastructure, while the `IntentPlannerPolicy`/`PlannerDecision`
abstraction exists for direct, programmatic comparison (tests, notebooks,
and - from L3 onward - planner levels that cannot be expressed as just
another `PurificationStrategy`). Both paths are real and tested, not one
faked in terms of the other: `tests/planning/planners/test_l2_iterative.py`
exercises `IterativeAnalyticalPlanner`/`IterativeAnalyticalPurification`
directly, and P01's campaign results independently confirm the same
behavior through the full simulation pipeline (see
`docs/planner_study_findings_checkpoint1.md`).

## Registry

`planning.planners.registry.PLANNER_POLICIES` maps `"L1"`/`"L2"` to their
classes (`resolve_planner_policy("L1")`), mirroring the existing
`experiments.sweeps.ROUTING_STRATEGIES`/`PURIFICATION_POLICIES` pattern.
L3/L4/L5/hybrid are added to this SAME dict as they're implemented (never
a parallel registry).
