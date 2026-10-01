"""R00 - generation-model audit under the calibrated single-heralded
physics (docs/generation_model_audit.md).

Runs linear chains across repeater counts, link lengths and memory-slot
counts with purification disabled, and checks the planners' generation
model (`planning.planners.generation_models`) against the simulator:

1. the attempt cycle of a link, in one-way classical delays - 4 when the
   node requesting the pairing is not the protocol's primary, 5 when it is
   (the same direct link is run in both reservation directions);
2. the per-attempt success probability against the closed form
   1/2 * (efficiency * detector_efficiency)^2 * transmission;
3. the end-to-end rate of the `buffered` law (finite-buffer matching
   queues composed in SeQUeNCe's swap order), which has no fitted constant.

Writes results/realistic/audit/generation_model_audit.csv (resumable) and
generation_model_audit_summary.csv.
Run: python scripts/realistic/audit_generation_model.py [workers] [seeds]
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ibqn.experiments.generation_audit import run_generation_audit_job  # noqa: E402
from ibqn.experiments.realistic_suite import run_jobs_to_csv  # noqa: E402
from ibqn.experiments.realistic_topologies import realistic_chain  # noqa: E402
from ibqn.network.capabilities import NetworkCapabilities  # noqa: E402
from ibqn.network.platforms import resolve_platform  # noqa: E402
from ibqn.planning.planners.generation_models import (  # noqa: E402
    attempt_cycle_s,
    estimate_generation,
    hop_success_probability,
)

OUT = PROJECT_ROOT / "results" / "realistic" / "audit" / "generation_model_audit.csv"
SUMMARY = OUT.with_name("generation_model_audit_summary.csv")
PLATFORMS = ["siv_2024"]
REPEATERS = [0, 1, 2, 3]
LINKS_M = [2_000.0, 5_000.0, 10_000.0]
SLOTS = [2, 4]
DURATION_S = 0.3
MIN_FIDELITY = 0.3  # below the 3-repeater swap output (0.51), so every swap proceeds
DEFAULT_SEEDS = 12
REVERSED_SEEDS = 4  # direct link only, reservation from b to a: the requester is then the protocol's primary
CELL = ["platform", "reverse", "n_repeaters", "link_m", "slots"]


def model_row(platform: str, reverse: bool, n_repeaters: int, link_m: float, slots: int) -> dict:
    """The planner model's numbers for one audited configuration."""
    spec = realistic_chain(
        n_repeaters, platform=resolve_platform(platform), link_m=link_m, end_memories=slots, repeater_memories=2 * slots,
    )
    capabilities = NetworkCapabilities(spec)
    route = [node.id for node in spec.nodes]
    if reverse:
        route = route[::-1]
    return dict(
        p_model=hop_success_probability(capabilities, route[0], route[1]),
        first_cycle_model_s=attempt_cycle_s(capabilities, route[0], route[1]),
        last_cycle_model_s=attempt_cycle_s(capabilities, route[-2], route[-1]),
        rate_model=estimate_generation(capabilities, route, slots, model="buffered").raw_end_to_end_pair_rate,
        rate_same_cycle=estimate_generation(capabilities, route, slots, model="same_cycle").raw_end_to_end_pair_rate,
    )


def main() -> None:
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    seeds = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_SEEDS
    jobs = [
        dict(platform=platform, n_repeaters=n, link_m=link_m, slots=slots, duration_s=DURATION_S, seed=seed,
             min_fidelity=MIN_FIDELITY)
        for platform, n, link_m, slots, seed in itertools.product(PLATFORMS, REPEATERS, LINKS_M, SLOTS, range(seeds))
    ]
    jobs += [
        dict(platform=platform, n_repeaters=0, link_m=link_m, slots=slots, duration_s=DURATION_S, seed=seed,
             min_fidelity=MIN_FIDELITY, reverse=True)
        for platform, link_m, slots, seed in itertools.product(PLATFORMS, LINKS_M, SLOTS, range(min(seeds, REVERSED_SEEDS)))
    ]
    df = run_jobs_to_csv(
        jobs, run_generation_audit_job, OUT, workers=workers,
        key=lambda j: f"{j['platform']}|{j['n_repeaters']}|{j['link_m']}|{j['slots']}|{j['duration_s']}|{j['seed']}"
                      + ("|reverse" if j.get("reverse") else ""),
        describe=lambda j, r: f"rep={r['n_repeaters']} L={r['link_m'] / 1000:.0f}km slots={r['slots']} seed={r['seed']}"
                              f"{' reversed' if r.get('reverse') else ''} -> delivered={r['delivered_pairs']} "
                              f"wall={r['wall_time_s']}s",
    )
    df["reverse"] = df["reverse"].fillna(False).astype(bool) if "reverse" in df else False
    df = df.sort_values([*CELL, "seed"]).reset_index(drop=True)
    df.to_csv(OUT, index=False)

    model = pd.DataFrame([
        dict(zip(CELL, cell), **model_row(cell[0], bool(cell[1]), int(cell[2]), float(cell[3]), int(cell[4])))
        for cell in df[CELL].drop_duplicates().itertuples(index=False, name=None)
    ])
    df = df.merge(model, on=CELL)
    pd.set_option("display.width", 220)

    # ---- 1. attempt cycle ---------------------------------------------------
    # A link's memories attempt whenever they are not holding a pair, so on a 0-repeater chain (nothing
    # is ever held: pairs are delivered at once) attempts * cycle = slots * window exactly. The same
    # link is measured in both reservation directions: a -> b (requester `a` is not the primary) and
    # b -> a (requester `b` is the primary).
    direct = df[df["n_repeaters"] == 0].copy()
    direct["k"] = direct["slots"] * direct["duration_s"] / direct["first_link_attempts"] / direct["classical_delay_s"]
    direct["k_model"] = direct["first_cycle_model_s"] / direct["classical_delay_s"]
    print("\n== attempt cycle of a direct link, in one-way classical delays ==")
    print(direct.groupby(["reverse", "link_m"]).agg(
        runs=("seed", "count"), k_measured=("k", "mean"), k_std=("k", "std"), k_model=("k_model", "first"),
        pairs_per_s=("delivered_pairs", lambda s: s.sum() / (len(s) * DURATION_S)),
    ).round(4).to_string())

    # ---- 2. per-attempt success ---------------------------------------------
    per_link = df.groupby("link_m").agg(
        attempts=("first_link_attempts", "sum"), successes=("first_link_successes", "sum"), p_model=("p_model", "first"),
    )
    per_link["p_measured"] = per_link["successes"] / per_link["attempts"]
    per_link["measured/model"] = per_link["p_measured"] / per_link["p_model"]
    per_link["1 sigma"] = 1 / np.sqrt(per_link["successes"])
    print("\n== per-attempt success probability (first link of every run) ==")
    print(per_link.round(5).to_string())

    # ---- 3. end-to-end rate -------------------------------------------------
    by_cell = df.groupby(CELL[1:]).agg(
        runs=("seed", "count"), delivered=("delivered_pairs", "sum"), window=("duration_s", "sum"),
        second_half=("delivered_second_half", "sum"), first_delivery_s=("first_delivery_s", "mean"),
        rate_model=("rate_model", "first"), rate_same_cycle=("rate_same_cycle", "first"),
        fidelity=("mean_fidelity", "mean"),
    )
    by_cell["rate_measured"] = by_cell["delivered"] / by_cell["window"]
    by_cell["rate_second_half"] = by_cell["second_half"] / (by_cell["window"] / 2)
    by_cell["measured/model"] = by_cell["rate_measured"] / by_cell["rate_model"]
    by_cell["2nd half/model"] = by_cell["rate_second_half"] / by_cell["rate_model"]
    by_cell["1 sigma"] = 1 / np.sqrt(by_cell["delivered"].clip(lower=1))
    by_cell["measured/same_cycle"] = by_cell["rate_measured"] / by_cell["rate_same_cycle"]
    print("\n== end-to-end pairs per second: simulator vs the buffered law ==")
    print(by_cell[["runs", "delivered", "rate_measured", "rate_model", "measured/model", "1 sigma", "2nd half/model",
                   "first_delivery_s", "measured/same_cycle", "fidelity"]].round(4).to_string())
    forward = by_cell[~by_cell.index.get_level_values("reverse")]
    multi = forward[forward.index.get_level_values("n_repeaters") > 0]
    pooled = multi["delivered"].sum() / (multi["rate_model"] * multi["window"]).sum()
    pooled_second_half = multi["second_half"].sum() / (multi["rate_model"] * multi["window"] / 2).sum()
    print(f"\nmulti-hop cells: measured/model mean {multi['measured/model'].mean():.3f} "
          f"(min {multi['measured/model'].min():.3f}, max {multi['measured/model'].max():.3f}), "
          f"mean |error| {(multi['measured/model'] - 1).abs().mean():.3f}; pooled over all pairs {pooled:.3f} "
          f"(second half of the window only: {pooled_second_half:.3f})")
    by_cell.to_csv(SUMMARY)


if __name__ == "__main__":
    main()
