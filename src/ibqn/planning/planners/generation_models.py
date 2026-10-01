"""Elementary-generation models shared by the resource-aware planners
(L2-R, L3, L3-R and their buffered variants L2-RB, L3-RB): how often a
route attempts generation, how likely an attempt is to succeed, and how
that turns into raw end-to-end pairs per second.

Two generation protocols exist, selected by the topology's formalism
(docs/physical_model.md), and each has its own audited constants:

- `ket_vector` -> Barrett-Kok. Audit: docs/l3_attempt_rate_audit.md (frozen
  F02/F03 data). Per-attempt success `transmission * 1/2`; the naive attempt
  rate `slots / (2 * classical_delay)` over-counts by ~3.66x, corrected by
  the conservative factor 7.5. These numbers are unchanged.
- `bell_diagonal` -> single-heralded. Audit: docs/generation_model_audit.md
  (`scripts/realistic/audit_generation_model.py`). Per-attempt success
  `1/2 * eff_a * eff_b * detector_eff^2 * transmission` (both photons must
  be emitted, survive the fiber and be detected, then the linear-optics BSM
  succeeds half the time). One attempt takes 4 or 5 one-way classical
  delays of the link, depending on which end starts the handshake - see
  `single_heralded_cycle_factor`.

Two rate laws turn those into raw end-to-end pairs:

- `same_cycle` (the original L2-R/L3 assumption): a raw end-to-end pair
  needs EVERY hop to succeed in the same attempt cycle -
  `attempt_rate * prod(p_hop)`. Tolerable when `p_hop ~ 0.5` (legacy
  idealized hardware); with calibrated hardware (`p_hop ~ 6e-3`) it
  under-predicts multi-hop throughput by one to two orders of magnitude.
- `buffered`: links are generated independently and WAIT in memory for
  their swap partner. A memory holding a pair is not attempting, so each
  swap behaves as a finite-buffer matching queue fed by two pair streams
  (`matched_stream_rate`), and a route is those queues composed in
  SeQUeNCe's own swap order (`buffered_end_to_end_rate`). No fitted
  constant: the audit only checks it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ...network.capabilities import LinkCapability, NetworkCapabilities

BSM_SUCCESS_RATE = 0.5
"""`sequence.components.bsm` linear-optics Bell-state-measurement success
rate (`SingleAtomBSM`/`SingleHeraldedBSM` default)."""

SEQUENCE_DEFAULT_DETECTOR_EFFICIENCY = 0.9
"""`sequence.components.detector.Detector` default, used when a link does
not declare `detector_efficiency`."""

BARRETT_KOK_ATTEMPT_RATE_FACTOR = 7.5
"""Conservative divisor on the naive Barrett-Kok attempt rate
(docs/l3_attempt_rate_audit.md) - exported by `l2_resource_aware` as
`ATTEMPT_RATE_CONSERVATIVE_FACTOR`, its original name."""

BARRETT_KOK_CYCLE_FACTOR = 7.32
"""Best-fit Barrett-Kok attempt cycle in classical delays (same audit) -
used only by the `buffered` law under `ket_vector`."""

SINGLE_HERALDED_CYCLE_FACTOR = 4.0
"""Single-heralded attempt cycle, in one-way classical delays of the link,
when the node that requests the pairing is NOT the protocol's primary
(measured 4.002, std 0.001 - docs/generation_model_audit.md)."""

SINGLE_HERALDED_PRIMARY_REQUESTER_CYCLE_FACTOR = 5.0
"""The same cycle when the requesting node IS the primary: its NEGOTIATE
can only leave after the pairing RESPONSE came back, one more one-way
delay (measured 5.000 on every such link of the audit)."""

GENERATION_MODELS: tuple[str, ...] = ("same_cycle", "buffered")


def link_transmission(link: LinkCapability) -> float:
    """Photon survival over the whole link (both BSM legs combined)."""
    return 10 ** (-(link.distance_m * link.attenuation_db_per_m) / 10)


def hop_success_probability(capabilities: NetworkCapabilities, a: str, b: str) -> float:
    """Probability that one elementary-generation attempt on link a-b
    succeeds, for the generation protocol the topology's formalism implies."""
    link = capabilities.link(a, b)
    transmission = link_transmission(link)
    if not capabilities.physics.is_bell_diagonal:
        return transmission * BSM_SUCCESS_RATE
    detector_efficiency = (
        link.detector_efficiency if link.detector_efficiency is not None else SEQUENCE_DEFAULT_DETECTOR_EFFICIENCY
    )
    return (
        BSM_SUCCESS_RATE * capabilities.node(a).memory_efficiency * capabilities.node(b).memory_efficiency
        * detector_efficiency ** 2 * transmission
    )


def single_heralded_cycle_factor(requester: str, responder: str) -> float:
    """One-way classical delays per single-heralded attempt on a link whose
    resource-manager pairing is requested by `requester`.

    Two handshakes precede every attempt in SeQUeNCe: the resource managers
    pair the two protocol instances (REQUEST from the node earlier on the
    reservation path, RESPONSE back), then the protocol's PRIMARY - the node
    with the lexicographically larger name
    (`EntanglementGenerationA.primary`) - opens NEGOTIATE/NEGOTIATE_ACK. If
    the primary is the node that received the REQUEST it negotiates as soon
    as it approves, and the two handshakes overlap: 4 delays per attempt.
    If the primary is the requester it has to wait for the RESPONSE first:
    5 delays. So the same physical link is 20% slower in one direction of
    the reservation path than in the other."""
    return SINGLE_HERALDED_PRIMARY_REQUESTER_CYCLE_FACTOR if requester > responder else SINGLE_HERALDED_CYCLE_FACTOR


def attempt_cycle_s(capabilities: NetworkCapabilities, a: str, b: str) -> float:
    """Seconds between consecutive attempts of ONE memory pair on link a-b
    while it is free to attempt, `a` being the node earlier on the route
    (the one whose resource manager requests the pairing)."""
    delay = capabilities.classical_delay_between(a, b)
    if capabilities.physics.is_bell_diagonal:
        excitation_period = 1.0 / min(capabilities.node(a).memory_frequency_hz, capabilities.node(b).memory_frequency_hz)
        return max(single_heralded_cycle_factor(a, b) * delay, excitation_period)
    return BARRETT_KOK_CYCLE_FACTOR * delay


def matched_stream_rate(left_rate: float, right_rate: float, slots: int) -> float:
    """Pairs per second leaving a swap that joins two independent pair
    streams, each buffered in `slots` memories.

    `left_rate`/`right_rate` are what each side produces while all its
    `slots` memories are attempting. A pair that arrives while the other
    side has none waits in its memory, and that memory stops attempting -
    so with `d` pairs waiting a side produces at `(slots - d) / slots` of
    its rate. The difference between the two sides' waiting pairs is a
    birth-death chain on `-slots..slots`; a swap happens whenever a pair
    arrives on the side that is behind. Its stationary throughput is
    returned (0.75 of the common rate for two equal streams and 2 slots,
    0.82 for 4, tending to 1 as the buffer grows)."""
    if left_rate <= 0 or right_rate <= 0 or slots <= 0:
        return 0.0
    left_ahead = [1.0]   # unnormalized stationary weights of d = 0, 1, .., slots left pairs waiting
    right_ahead = [1.0]
    for waiting in range(slots):
        free_fraction = (slots - waiting) / slots
        left_ahead.append(left_ahead[-1] * free_fraction * left_rate / right_rate)
        right_ahead.append(right_ahead[-1] * free_fraction * right_rate / left_rate)
    total = sum(left_ahead) + sum(right_ahead) - 1.0
    return (sum(left_ahead[1:]) * right_rate + sum(right_ahead[1:]) * left_rate) / total


def buffered_end_to_end_rate(
    link_rates: list[float], slots: int, swap_success_probabilities: list[float] | None = None,
) -> float:
    """Raw end-to-end pairs per second of a route whose links produce
    `link_rates` (all `slots` memories attempting), composing
    `matched_stream_rate` in the order SeQUeNCe swaps
    (`ResourceManager.generate_load_rules`): every second node first, then
    every second node of what is left, and so on.

    `swap_success_probabilities[i]` belongs to the node between link `i` and
    link `i + 1` (default: swaps always succeed); a failed swap loses both
    pairs. Treating a merged segment as a fresh stream for the next level
    is an approximation - its pairs share the end nodes' memories with the
    links below them - checked against the simulator in
    docs/generation_model_audit.md."""
    if not link_rates:
        return 0.0
    if swap_success_probabilities is None:
        swap_success_probabilities = [1.0] * (len(link_rates) - 1)
    if len(swap_success_probabilities) != len(link_rates) - 1:
        raise ValueError("one swap success probability per interior node is required")
    rates = list(link_rates)
    swaps = list(swap_success_probabilities)  # swaps[i]: the node between segment i and segment i + 1
    while len(rates) > 1:
        merged_rates, merged_swaps = [], []
        for i in range(0, len(rates) - 1, 2):
            merged_rates.append(matched_stream_rate(rates[i], rates[i + 1], slots) * swaps[i])
            if i + 1 < len(swaps):
                merged_swaps.append(swaps[i + 1])
        if len(rates) % 2 == 1:
            merged_rates.append(rates[-1])
        rates, swaps = merged_rates, merged_swaps
    return rates[0]


@dataclass(frozen=True)
class GenerationEstimate:
    model: str
    attempt_rate: float
    """Attempts per second across the reserved slots (slowest hop)."""
    raw_pair_probability: float
    """Product of per-hop success probabilities - what `same_cycle`
    multiplies the attempt rate by; reported for every model."""
    raw_end_to_end_pair_rate: float
    """Raw (pre-purification) end-to-end pairs per second."""


def estimate_generation(
    capabilities: NetworkCapabilities, route: list[str], reserved_memory_slots: int, *, model: str = "same_cycle",
) -> GenerationEstimate:
    if model not in GENERATION_MODELS:
        raise ValueError(f"unknown generation model {model!r} - supported: {GENERATION_MODELS}")
    hops = list(zip(route, route[1:]))
    per_hop = [hop_success_probability(capabilities, a, b) for a, b in hops]
    raw_pair_probability = math.prod(per_hop) if per_hop else 0.0

    if model == "buffered":
        cycles = [attempt_cycle_s(capabilities, a, b) for a, b in hops]
        link_rates = [reserved_memory_slots * p / cycle if cycle > 0 else 0.0 for p, cycle in zip(per_hop, cycles)]
        swap_success = [capabilities.node(node).swapping_success_prob for node in route[1:-1]]
        return GenerationEstimate(
            model=model,
            attempt_rate=reserved_memory_slots / max(cycles) if cycles and max(cycles) > 0 else 0.0,
            raw_pair_probability=raw_pair_probability,
            raw_end_to_end_pair_rate=buffered_end_to_end_rate(link_rates, reserved_memory_slots, swap_success),
        )

    if capabilities.physics.is_bell_diagonal:
        slowest_cycle = max(attempt_cycle_s(capabilities, a, b) for a, b in hops) if hops else 0.0
        attempt_rate = reserved_memory_slots / slowest_cycle if slowest_cycle > 0 else 0.0
    else:
        # The original, audited Barrett-Kok model - arithmetic unchanged.
        naive_attempt_rate = reserved_memory_slots / (2 * capabilities.classical_delay_s)
        attempt_rate = naive_attempt_rate / BARRETT_KOK_ATTEMPT_RATE_FACTOR
    return GenerationEstimate(
        model=model, attempt_rate=attempt_rate, raw_pair_probability=raw_pair_probability,
        raw_end_to_end_pair_rate=attempt_rate * raw_pair_probability,
    )
