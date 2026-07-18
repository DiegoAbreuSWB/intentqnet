# L3: probabilistic analytical planner

## What is real physics vs. what is approximated

L3 predicts `P(satisfied)`, `P(delivered_pairs >= min_delivered_pairs)`,
and an expected-delivered-pairs distribution - not just a feasible/
infeasible point estimate. Every component is documented as either
grounded in SeQUeNCe's actual mechanics or an explicit, named
approximation - never presented as more precise than it is.

### Grounded in real SeQUeNCe physics

- **Elementary-generation success probability**: photon transmission over
  the fiber, `sequence.components.optical_channel.QuantumChannel.loss = 1
  - 10**(-distance*attenuation/10)`, with SeQUeNCe placing the BSM at the
  link midpoint (`network.topology.QuantumLinkSpec`'s docstring) - the two
  half-distance transmissions combine multiplicatively to the
  full-distance transmission probability, times the BSM's linear-optics
  success rate (`sequence.components.bsm`'s `success_rate: float = 0.5`
  default).
- **Purification round success probability**: the Dur-Briegel BBPSSW
  formula's own denominator, `f**2 + 2*f*(1-f)/3 + 5*((1-f)/3)**2` -
  literally the normalization term already present in
  `bbpssw_circuit.BBPSSWCircuit.improved_fidelity`, not a separately
  invented formula.
- **Swap success probability = 1**: confirmed by reading
  `sequence.topology.node` (`swapping_success_prob` defaults to 1) and
  `network.sequence_adapter` (only sets `swapping_degradation`, a fidelity
  factor, never `swapping_success_prob`) - this project's configuration
  never fails a swap operationally, only degrades its fidelity.

### Explicitly approximate (named simplifying assumptions)

1. **A "raw path pair" requires every hop to succeed in the same attempt
   cycle.** Real SeQUeNCe generates each link's elementary pair
   independently and buffers completed links until a swap partner is
   ready. Treating all-hops-in-lockstep as required likely
   UNDERESTIMATES achievable throughput on longer routes (fewer
   effectively-independent trials than the real buffered process allows).
2. **Attempt rate = `reserved_memory_slots / (2 * classical_delay_s)`.**
   This assumes one classical round trip per attempt cycle. Barret-Kok's
   real protocol (`sequence.entanglement_management.generation.
   barret_kok.py`) runs THREE rounds (`ent_round` 1->2->3) each requiring
   photon emission, BSM measurement, and classical message coordination -
   a real per-attempt-cycle time is plausibly 1.5-2x a single round trip,
   not exactly one. **This is checked, not assumed away**: comparing this
   formula's implied attempt rate against real F02 campaign data
   (`results/raw/F02_routing/trials.csv`, diamond topology, `eg_attempts /
   duration_s`) shows the model over-predicts attempt rate by a factor of
   roughly 2.4-4.3x. This constant was deliberately NOT tuned to close
   that gap - doing so before P02 measures the resulting calibration error
   would be circular (fitting the model to the exact data used to validate
   it). P02's Brier score / calibration curve is where this gets
   measured honestly.
3. **Effective purification pair cost = `product over rounds of (2 /
   Dur-Briegel round success probability)`.** Models purification retries
   as an inflated deterministic pair cost, not an explicit retry loop;
   reduces to L2's `2**rounds` exactly as the round success probability
   approaches 1.
4. **`fidelity_success_probability` is 0/1, from L2's deterministic
   reachability** (not independently modeled). This reuses checkpoint 1's
   own empirical finding - L2's fidelity estimate matched observed
   fidelity almost exactly on both topologies tested - rather than
   inventing a second, unvalidated fidelity-uncertainty model. If P02's
   topologies show worse fidelity calibration, this assumption is exactly
   what would need revisiting first.
5. **`delivered_pairs` is Poisson-distributed.** A standard approximation
   for a rare, memoryless success-counting process; real delivery counts
   may be over/under-dispersed relative to Poisson - not verified here.
6. **Independence between fidelity success and delivery success** when
   forming `satisfaction_probability = fidelity_success_probability *
   delivery_success_probability`. Both are driven by the same underlying
   attempt process, so this likely understates their true positive
   correlation.

## Known calibration gap going into P02

The attempt-rate overestimate (point 2 above) means `expected_delivered_
pairs` is itself over-predicted by a similar factor. In the P01 topologies
specifically, this does NOT change admission decisions, because expected
counts (hundreds) are so far above `min_delivered_pairs=10` that
`delivery_success_probability` rounds to 1.0 either way (Poisson survival
function saturates). **P02 is designed to probe regimes where this
matters** - lower `reserved_memory_slots`, shorter `duration_s`, higher
`attenuation_db_per_m` - where `expected_delivered_pairs` and
`min_delivered_pairs` are close enough that a 2-4x error in the mean
changes the admission decision. This is the whole point of measuring
calibration empirically rather than assuming L3 "must be better" than L1/L2
because it is more sophisticated.

## Admission policy

`ProbabilisticPlanner(admission_threshold=...)` admits the best candidate
route whose `satisfaction_probability >= admission_threshold`. Candidate
thresholds to compare (per the planner-study brief): 0.50, 0.75, 0.90,
0.95. The final threshold must be chosen on a validation subset of P02's
seeds, never the test subset - see `docs/planner_comparison_methodology.md`
(updated for P02) for the exact split used.
