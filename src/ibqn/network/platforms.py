"""Hardware platform profiles: every physical parameter the simulator
consumes, set to a value DEMONSTRATED in a peer-reviewed experiment, with
the source recorded next to it (docs/parameter_calibration.md is the full
survey and the justification for each mapping).

Profiles are applied to a `NetworkTopologySpec` by `apply_platform` (or
declared in a scenario YAML as `platform: <name>`), so an experiment's
hardware assumptions are explicit and recorded (`TrialRecord.platform`)
instead of living in schema defaults. `NodeSpec`/`QuantumLinkSpec` keep
ideal-hardware defaults (gate/measurement fidelity 1, emission efficiency
1) for unit tests of the mechanics; no campaign should run on them.

How each field maps onto SeQUeNCe (see docs/parameter_calibration.md,
section 7):

- `raw_fidelity`: fidelity of the heralded memory-memory pair.
- `gate_fidelity` / `measurement_fidelity`: `Node.gate_fid`/`meas_fid`,
  used by the Bell-diagonal swap and BBPSSW formulas.
- `swapping_success_prob`: deterministic (1.0) for processing nodes that
  swap with local gates; 0.5 for photonic linear-optics BSMs.
- `coherence_time_s`: survival time of the stored half of a pair while the
  node keeps attempting on its other link (NOT the idle-qubit T2);
  `decoherence_errors=(0,0,1)` because dephasing dominates (T1 >> T2).
- `memory_efficiency`: per-attempt, per-photon probability of emission +
  collection + frequency conversion (+ fiber coupling), EXCLUDING fiber
  attenuation and detector efficiency, which the simulator applies itself.
- `memory_frequency_hz`: maximum attempt (excitation) rate.
- `detector_efficiency`: SNSPD system efficiency.
- `attenuation_db_per_m`: telecom-band fiber loss after conversion.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from .topology import FIBER_SPEED_OF_LIGHT_M_PER_S, NetworkTopologySpec, NodeSpec, QuantumLinkSpec

TELECOM_C_BAND_ATTENUATION_DB_PER_M = 2.2e-4
"""0.22 dB/km measured on standard single-mode fiber at 1550 nm (van Leent
et al., Nature 607, 69, 2022); the spec value is 0.2 dB/km."""

TELECOM_O_BAND_ATTENUATION_DB_PER_M = 3.0e-4
"""0.3 dB/km at 1342 nm (Liu et al., Nature 629, 579, 2024)."""

DEPLOYED_FIBER_ATTENUATION_DB_PER_M = 4.9e-4
"""Deployed fiber including splices/connectors: 17 dB over the 35 km Boston
loop (Knaut et al., Nature 629, 573, 2024); 0.39-0.51 dB/km on the
Delft-The Hague link (Stolk et al., Sci. Adv. 10, eadp6442, 2024)."""

VISIBLE_637NM_ATTENUATION_DB_PER_M = 8.0e-3
"""~8 dB/km at the NV zero-phonon line, i.e. without frequency conversion
(Dreau et al., Phys. Rev. Applied 9, 064031, 2018)."""

SNSPD_DETECTOR_EFFICIENCY = 0.9
"""Commercial-grade SNSPD: 93% (Marsili et al., Nat. Photon. 7, 210, 2013);
98% (Reddy et al., Optica 7, 1649, 2020); 99.5% (Chang et al., APL Photon.
6, 036114, 2021). SeQUeNCe's own Detector default is also 0.9."""

DEPHASING_ERRORS: tuple[float, float, float] = (0.0, 0.0, 1.0)
"""Pure dephasing (Z) channel - the dominant decoherence mechanism of spin
memories in every surveyed network experiment."""

DEPOLARIZING_ERRORS: tuple[float, float, float] = (1 / 3, 1 / 3, 1 / 3)


@dataclass(frozen=True)
class PlatformProfile:
    name: str
    description: str
    raw_fidelity: float
    gate_fidelity: float
    measurement_fidelity: float
    swapping_success_prob: float
    coherence_time_s: float
    decoherence_errors: tuple[float, float, float]
    memory_efficiency: float
    memory_frequency_hz: float
    detector_efficiency: float
    attenuation_db_per_m: float
    cutoff_ratio: float = 0.5
    sources: tuple[str, ...] = field(default_factory=tuple)

    def node(self, node_id: str, memories: int, **overrides) -> NodeSpec:
        values = dict(
            id=node_id, memories=memories, raw_fidelity=self.raw_fidelity,
            gate_fidelity=self.gate_fidelity, measurement_fidelity=self.measurement_fidelity,
            swapping_success_prob=self.swapping_success_prob, coherence_time_s=self.coherence_time_s,
            cutoff_ratio=self.cutoff_ratio, decoherence_errors=self.decoherence_errors,
            memory_efficiency=self.memory_efficiency, memory_frequency_hz=self.memory_frequency_hz,
        )
        values.update(overrides)
        return NodeSpec(**values)

    def link(self, source: str, destination: str, distance_m: float, **overrides) -> QuantumLinkSpec:
        values = dict(
            source=source, destination=destination, distance_m=distance_m,
            attenuation_db_per_m=self.attenuation_db_per_m, detector_efficiency=self.detector_efficiency,
        )
        values.update(overrides)
        return QuantumLinkSpec(**values)


TRAPPED_ION_2023 = PlatformProfile(
    name="trapped_ion_2023",
    description=(
        "Cavity-coupled trapped-ion network node with telecom conversion (Innsbruck/Oxford class): the "
        "only platform with a demonstrated memory-based repeater node over 50 km"
    ),
    raw_fidelity=0.88,          # ion-ion over 230 m / 520 m fiber: 0.882 (Krutyanskiy et al., PRL 130, 050803, 2023)
    gate_fidelity=0.95,         # deterministic ion BSM used for swapping: 0.95(2) (Krutyanskiy et al., PRL 130, 213601, 2023)
    measurement_fidelity=0.999, # 99.991% single-shot readout (Myerson et al., PRL 100, 200502, 2008)
    swapping_success_prob=1.0,  # deterministic local Bell-state measurement
    coherence_time_s=0.062,     # 62(3) ms memory decoherence during the repeater protocol (Krutyanskiy 2023, PRL 130, 213601)
    decoherence_errors=DEPHASING_ERRORS,
    memory_efficiency=0.018,    # P_link0 = 0.018(1): telecom photon generation+conversion+detection per node (Krutyanskiy 2023)
    memory_frequency_hz=8e5,    # 182 Hz / 2.18e-4 per attempt ~ 0.83 MHz attempts (Stephenson et al., PRL 124, 110501, 2020)
    detector_efficiency=SNSPD_DETECTOR_EFFICIENCY,
    attenuation_db_per_m=TELECOM_C_BAND_ATTENUATION_DB_PER_M,
    sources=(
        "Krutyanskiy et al., Phys. Rev. Lett. 130, 213601 (2023)",
        "Krutyanskiy et al., Phys. Rev. Lett. 130, 050803 (2023)",
        "Stephenson et al., Phys. Rev. Lett. 124, 110501 (2020)",
        "Myerson et al., Phys. Rev. Lett. 100, 200502 (2008)",
        "Avis et al., npj Quantum Inf. 9, 100 (2023)",
    ),
)

SIV_2024 = PlatformProfile(
    name="siv_2024",
    description="Silicon-vacancy centre in a nanophotonic diamond cavity with 29Si nuclear memory (Harvard class)",
    raw_fidelity=0.86,          # electron-electron 0.86(3) over 20 m (Knaut et al., Nature 629, 573, 2024)
    gate_fidelity=0.937,        # decoupled CeNOTn 93.7(7)% (Stas et al., Science 378, 557, 2022)
    measurement_fidelity=0.995, # electron readout 99.5(1)% (Stas et al. 2022)
    swapping_success_prob=1.0,
    coherence_time_s=2.0,       # 29Si nuclear memory T2 = 2.1(1) s (Stas 2022); ~2 s (Knaut 2024)
    decoherence_errors=DEPHASING_ERRORS,
    memory_efficiency=0.14,     # heralding efficiency 0.423 (Bhaskar et al., Nature 580, 60, 2020) x 33% conversion (Knaut 2024)
    memory_frequency_hz=1.2e6,  # 1.2 MHz effective clock (Bhaskar 2020)
    detector_efficiency=SNSPD_DETECTOR_EFFICIENCY,
    attenuation_db_per_m=TELECOM_O_BAND_ATTENUATION_DB_PER_M,  # 1350 nm conversion target (Knaut 2024)
    sources=(
        "Knaut et al., Nature 629, 573 (2024)",
        "Stas et al., Science 378, 557 (2022)",
        "Bhaskar et al., Nature 580, 60 (2020)",
    ),
)

SIV_2024_THEORETICAL_OPS = replace(
    SIV_2024,
    name="siv_2024_theoretical_ops",
    description=(
        "SiV 2024 hardware (link fidelity, efficiency, memory, fiber - all demonstrated values) with IDEAL local "
        "operations: gate and measurement fidelity 1. Not a demonstrated node - the reference condition in which "
        "BBPSSW purification behaves as in the textbook (Dur-Briegel), used alongside `siv_2024` to separate what "
        "the management architecture does from what present-day gate noise allows"
    ),
    gate_fidelity=1.0,
    measurement_fidelity=1.0,
)

NV_2022 = PlatformProfile(
    name="nv_2022",
    description=(
        "Nitrogen-vacancy centre network node with 13C memory (Delft class). NOTE: its demonstrated Hz-level "
        "rates rely on the single-photon (single-click) protocol, which SeQUeNCe does not implement; under the "
        "two-photon protocol simulated here this profile is a low-efficiency sensitivity case, not a rate benchmark"
    ),
    raw_fidelity=0.80,          # >0.8 on both links (Pompili et al., Science 372, 259, 2021); 0.81(2) at 6 Hz (Humphreys et al., Nature 558, 268, 2018)
    gate_fidelity=0.97,         # electron-nuclear two-qubit gate (Kalb et al., Science 356, 928, 2017; Avis et al. 2023 baseline)
    measurement_fidelity=0.98,  # memory readout 98.1(4)-99.2(4)% (Hermans et al., Nature 605, 663, 2022)
    swapping_success_prob=1.0,
    coherence_time_s=0.02,      # ~1800-5300 attempts x 5.5 us under network operation (Pompili 2021; Hermans 2022; Kalb et al., PRA 97, 062330, 2018)
    decoherence_errors=DEPHASING_ERRORS,
    memory_efficiency=5.1e-4,   # photon detection probability excluding attenuation (Avis et al. 2023, citing Hermans 2022)
    memory_frequency_hz=1.8e5,  # 5.5 us attempt cycle (Humphreys 2018); 3.8 us (Pompili et al., npj Quantum Inf. 8, 121, 2022)
    detector_efficiency=SNSPD_DETECTOR_EFFICIENCY,
    attenuation_db_per_m=TELECOM_C_BAND_ATTENUATION_DB_PER_M,  # after conversion (Stolk 2024); 8e-3 at 637 nm without it
    sources=(
        "Humphreys et al., Nature 558, 268 (2018)",
        "Pompili et al., Science 372, 259 (2021)",
        "Hermans et al., Nature 605, 663 (2022)",
        "Kalb et al., Science 356, 928 (2017)",
        "Kalb et al., Phys. Rev. A 97, 062330 (2018)",
        "Stolk et al., Sci. Adv. 10, eadp6442 (2024)",
        "Avis et al., npj Quantum Inf. 9, 100 (2023)",
    ),
)

ATOMIC_ENSEMBLE_2024 = PlatformProfile(
    name="atomic_ensemble_2024",
    description="Cold atomic-ensemble (DLCZ-type) memory with telecom conversion and photonic BSM (USTC class)",
    raw_fidelity=0.67,          # 0.672(32)/0.666(31) over 12.5 km (Liu et al., Nature 629, 579, 2024)
    gate_fidelity=1.0,          # no local two-qubit gate: swapping is a photonic linear-optics BSM
    measurement_fidelity=0.99,
    swapping_success_prob=0.5,  # linear-optics Bell-state measurement
    coherence_time_s=1.07e-4,   # 107 us storage, longer than the round-trip time (Liu 2024); 70 us (Yu et al., Nature 578, 240, 2020)
    decoherence_errors=DEPOLARIZING_ERRORS,
    memory_efficiency=0.15,     # retrieval 0.33 (Yu 2020) x conversion 0.46 (Liu 2024)
    memory_frequency_hz=2.8e3,  # 2.76 kHz repetition (Liu 2024)
    detector_efficiency=SNSPD_DETECTOR_EFFICIENCY,
    attenuation_db_per_m=TELECOM_O_BAND_ATTENUATION_DB_PER_M,
    sources=(
        "Liu et al., Nature 629, 579 (2024)",
        "Yu et al., Nature 578, 240 (2020)",
    ),
)

NEAR_TERM_TARGET = PlatformProfile(
    name="near_term_target",
    description=(
        "Projected 'minimal requirements' node, not a demonstrated one: Avis et al. (npj Quantum Inf. 9, 100, 2023) "
        "find that every hardware configuration meeting the Delft-Eindhoven repeater target has photon detection "
        "probability (excluding attenuation) above 30%; gate/readout quality taken from the best DEMONSTRATED local "
        "operations (Ballance et al. 2016; Myerson et al. 2008), memory from SiV (Stas et al. 2022)"
    ),
    raw_fidelity=0.90,          # between demonstrated ion links (0.88-0.94) with telecom conversion
    gate_fidelity=0.99,         # below the 0.999 local two-qubit gate (Ballance et al., PRL 117, 060504, 2016) to allow for network-node overhead
    measurement_fidelity=0.999, # Myerson et al., PRL 100, 200502 (2008)
    swapping_success_prob=1.0,
    coherence_time_s=2.0,       # Stas et al., Science 378, 557 (2022)
    decoherence_errors=DEPHASING_ERRORS,
    memory_efficiency=0.30,     # Avis et al. (2023) minimal requirement: photon detection probability > 30%
    memory_frequency_hz=1.2e6,
    detector_efficiency=0.95,   # Reddy et al., Optica 7, 1649 (2020): 98%; 95% on the deployed-grade side
    attenuation_db_per_m=TELECOM_C_BAND_ATTENUATION_DB_PER_M,
    sources=(
        "Avis et al., npj Quantum Inf. 9, 100 (2023)",
        "Ballance et al., Phys. Rev. Lett. 117, 060504 (2016)",
        "Myerson et al., Phys. Rev. Lett. 100, 200502 (2008)",
        "Stas et al., Science 378, 557 (2022)",
        "Reddy et al., Optica 7, 1649 (2020)",
    ),
)

IDEALIZED_LEGACY = PlatformProfile(
    name="idealized_legacy",
    description=(
        "The pre-calibration defaults this project used until September 2026 - no experimental basis; kept only "
        "to reproduce old results and as the 'ideal hardware' reference"
    ),
    raw_fidelity=0.85, gate_fidelity=1.0, measurement_fidelity=1.0, swapping_success_prob=1.0,
    coherence_time_s=1.0, decoherence_errors=DEPOLARIZING_ERRORS,
    memory_efficiency=1.0, memory_frequency_hz=80e6, detector_efficiency=0.9, attenuation_db_per_m=1e-5,
    sources=(),
)

PLATFORMS: dict[str, PlatformProfile] = {
    profile.name: profile
    for profile in (
        SIV_2024, SIV_2024_THEORETICAL_OPS, TRAPPED_ION_2023, NV_2022, ATOMIC_ENSEMBLE_2024,
        NEAR_TERM_TARGET, IDEALIZED_LEGACY,
    )
}

DEFAULT_PLATFORM = SIV_2024
"""Baseline for the article's campaigns (docs/parameter_calibration.md,
sections 7-9): the demonstrated platform whose two-photon-heralded
efficiency (0.14) yields end-to-end pair rates of ~10^2/s over 5 km links
in the simulator - the trapped-ion profile's telecom-converted efficiency
(0.018) gives ~6 pairs/s at 1 km and none over 5 km within a second, and
the NV profile cannot herald at all under the two-photon protocol. It also
has the longest demonstrated repeater memory (2 s) and a 35 km deployed
telecom demonstration (Knaut et al. 2024)."""


class UnknownPlatformError(ValueError):
    pass


def resolve_platform(name: str) -> PlatformProfile:
    try:
        return PLATFORMS[name]
    except KeyError:
        raise UnknownPlatformError(f"unknown platform {name!r} - supported: {sorted(PLATFORMS)}") from None


def classical_delay_s(distance_m: float) -> float:
    """One-way classical delay over `distance_m` of fiber (5 us/km)."""
    return distance_m / FIBER_SPEED_OF_LIGHT_M_PER_S


def apply_platform(
    spec: NetworkTopologySpec, profile: PlatformProfile, *, classical_delay_from_longest_link: bool = True,
) -> NetworkTopologySpec:
    """Returns a copy of `spec` with every node's and link's hardware
    parameters replaced by `profile`'s (node ids, memory counts, link
    distances and the formalism are kept). With
    `classical_delay_from_longest_link`, `classical_delay_s` becomes the
    one-way fiber delay of the longest quantum link (the full-mesh classical
    network's single delay value)."""
    nodes = [
        profile.node(node.id, node.memories)
        for node in spec.nodes
    ]
    links = [
        profile.link(link.source, link.destination, link.distance_m)
        for link in spec.quantum_links
    ]
    updates: dict = {"nodes": nodes, "quantum_links": links, "platform": profile.name}
    if classical_delay_from_longest_link:
        # Classical channels follow the fiber: per-pair delays from the
        # shortest fiber path (`classical_delay_model='fiber'`); the scalar is
        # kept as the longest link's delay for router pairs with no path.
        updates["classical_delay_s"] = classical_delay_s(max(link.distance_m for link in links))
        updates["classical_delay_model"] = "fiber"
    return spec.model_copy(update=updates)
