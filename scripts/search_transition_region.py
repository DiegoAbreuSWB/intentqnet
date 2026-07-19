"""M10.4-M10.5: two-stage transition-region search. Driven by
configs/campaigns/predictability_m10/P11_boundary_search.yaml. Stage A
(coarse) sweeps requested_fidelity around each topology's analytically
computed swap-only fidelity; Stage B (refinement) bisects toward the
P(satisfied)=0.5 crossing for any topology where Stage A found a
transition-range point. Every point tested is persisted (section 6's
explicit requirement - nothing discarded silently). Writes only to
results/predictability_m10/raw/P11_boundary_search/.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from predictability_m10_common import run_trial_with_timeout  # noqa: E402

from ibqn.experiments.predictability_m10_records import (  # noqa: E402
    PredictabilityM10TrialRecord,
    append_trial_record,
    read_trial_ids,
    trials_csv_path,
)
from ibqn.experiments.sweeps import compute_parameter_hash  # noqa: E402

CONFIG_PATH = PROJECT_ROOT / "configs" / "campaigns" / "predictability_m10" / "P11_boundary_search.yaml"


def wilson_ci(successes: int, n: int, confidence: float = 0.95) -> tuple[float, float]:
    """Same formula reused throughout this project (L4's `_wilson_ci`,
    P02B's analysis) - not re-derived."""
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    z = stats.norm.ppf(1 - (1 - confidence) / 2)
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / denom
    return max(0.0, center - half), min(1.0, center + half)


def classify_region(p_hat: float, ci_lo: float, ci_hi: float) -> str:
    """Section 7's exact five-region classification - CI bounds for the
    two ROBUST categories, point estimate for the three middle ones, per
    the governing brief."""
    if ci_lo >= 0.95:
        return "ROBUST_SUCCESS"
    if ci_hi <= 0.05:
        return "ROBUST_FAILURE"
    if p_hat >= 0.75:
        return "LIKELY_SUCCESS"
    if p_hat >= 0.25:
        return "TRANSITION"
    return "LIKELY_FAILURE"


def run_point(*, campaign_name: str, topo_cfg: dict, common: dict, min_fidelity: float,
              seeds: list[int], stage: str, iteration: int, known_records: dict | None = None) -> dict:
    """`known_records`: `{trial_id: final_status}` already in the CSV -
    resume-safety so re-running this script after fixing a bug (e.g. the
    stage-B trigger condition below) never re-executes already-collected
    coarse points, only the new stage-B points."""
    parameter_hash = compute_parameter_hash({
        "min_fidelity": min_fidelity, "duration_s": common["duration_s"],
        "reserved_memory_slots": common["reserved_memory_slots"], "topology": topo_cfg["name"],
        "stage": stage, "iteration": iteration,
    })
    known_records = known_records or {}
    n_satisfied = 0
    n = 0
    for seed in seeds:
        trial_id = (
            f"{campaign_name}:{topo_cfg['scenario']}:{parameter_hash}:{common['planner_level']}:"
            f"{seed}:m10-intent:0"
        )
        if trial_id in known_records:
            final_status = known_records[trial_id]
        else:
            row = run_trial_with_timeout(
                campaign=campaign_name, scenario=topo_cfg["scenario"], topology_builder=topo_cfg["topology_builder"],
                parameter_hash=parameter_hash, planner_level=common["planner_level"], seed=seed,
                min_fidelity=min_fidelity, reserved_memory_slots=common["reserved_memory_slots"],
                min_delivered_pairs=common["min_delivered_pairs"], duration_s=common["duration_s"],
                timeout_s=common["timeout_s"],
            )
            record = PredictabilityM10TrialRecord(**row)
            append_trial_record(common["trials_path"], record)
            final_status = record.final_status
        n += 1
        if final_status == "SATISFIED":
            n_satisfied += 1

    p_hat = n_satisfied / n if n else 0.0
    ci_lo, ci_hi = wilson_ci(n_satisfied, n)
    region = classify_region(p_hat, ci_lo, ci_hi)
    return {
        "topology": topo_cfg["name"], "stage": stage, "iteration": iteration, "min_fidelity": min_fidelity,
        "n": n, "n_satisfied": n_satisfied, "p_satisfied": p_hat, "ci_lo": ci_lo, "ci_hi": ci_hi, "region": region,
    }


def main() -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))["campaign"]
    campaign_name = config["name"]
    output_dir = str(PROJECT_ROOT / config["output_directory"])
    trials_path = trials_csv_path(output_dir, campaign_name)
    common = {
        "planner_level": config["planner_level"], "reserved_memory_slots": config["reserved_memory_slots"],
        "min_delivered_pairs": config["min_delivered_pairs"], "duration_s": config["duration_s"],
        "timeout_s": config["timeout_s"], "trials_path": trials_path,
    }
    seed_base = config["seed_base"]
    n_coarse = config["n_seeds_coarse"]
    n_refine = config["n_seeds_refine"]

    known_records: dict[str, str] = {}
    if trials_path.exists():
        import pandas as pd

        existing = pd.read_csv(trials_path)
        known_records = dict(zip(existing["trial_id"], existing["final_status"]))
        print(f"resuming: {len(known_records)} trials already recorded in {trials_path}")

    all_points = []
    for topo_cfg in config["topologies"]:
        print(f"\n=== Stage A (coarse): {topo_cfg['name']} ===")
        coarse_seeds = list(range(seed_base, seed_base + n_coarse))
        coarse_results = []
        for fid in topo_cfg["coarse_fidelity_grid"]:
            result = run_point(
                campaign_name=campaign_name, topo_cfg=topo_cfg, common=common, min_fidelity=fid,
                seeds=coarse_seeds, stage="coarse", iteration=0, known_records=known_records,
            )
            coarse_results.append(result)
            all_points.append(result)
            print(f"  fid={fid}: p_satisfied={result['p_satisfied']:.2f} CI=[{result['ci_lo']:.2f},{result['ci_hi']:.2f}] region={result['region']}")

        # Stage B triggers on ANY high(>=0.5)/low(<0.5) bracket in the coarse
        # grid - NOT only when a coarse point itself lands inside [0.05,0.95].
        # A sharp cliff (e.g. p=1.0 at fid=0.78, p=0.0 at fid=0.80, nothing
        # in between tested) still has a real crossing worth refining; the
        # first version of this script incorrectly required a coarse point
        # already IN the transition band, which skipped stage B for exactly
        # this cliff shape on three_node and small_mesh - fixed here.
        high_side = [r for r in coarse_results if r["p_satisfied"] >= 0.5]
        low_side = [r for r in coarse_results if r["p_satisfied"] < 0.5]
        if not high_side or not low_side:
            print(f"  no high/low bracket for {topo_cfg['name']} (all coarse points on one side) - skipping stage B")
            continue
        lo_fid = max(r["min_fidelity"] for r in high_side)
        hi_fid = min(r["min_fidelity"] for r in low_side)
        if lo_fid >= hi_fid:
            print(f"  bracket inverted for {topo_cfg['name']} ({lo_fid} >= {hi_fid}) - skipping stage B")
            continue

        print(f"=== Stage B (refinement): {topo_cfg['name']}, bracket [{lo_fid}, {hi_fid}] ===")
        refine_seeds = list(range(seed_base + 500, seed_base + 500 + n_refine))
        for iteration in range(1, config["max_refine_iterations"] + 1):
            midpoint = round((lo_fid + hi_fid) / 2, 6)
            result = run_point(
                campaign_name=campaign_name, topo_cfg=topo_cfg, common=common, min_fidelity=midpoint,
                seeds=refine_seeds, stage="refine", iteration=iteration, known_records=known_records,
            )
            all_points.append(result)
            print(f"  iter={iteration} fid={midpoint}: p_satisfied={result['p_satisfied']:.2f} CI=[{result['ci_lo']:.2f},{result['ci_hi']:.2f}] region={result['region']}")
            if result["p_satisfied"] >= 0.5:
                lo_fid = midpoint
            else:
                hi_fid = midpoint

        print(f"  final bracket for {topo_cfg['name']}: [{lo_fid}, {hi_fid}] (width={hi_fid - lo_fid:.4f})")

    import pandas as pd

    report = pd.DataFrame(all_points)
    processed_dir = Path(output_dir) / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    report.to_csv(processed_dir / "boundary_search_report.csv", index=False)
    print(f"\nwrote {processed_dir / 'boundary_search_report.csv'} ({len(report)} points total)")


if __name__ == "__main__":
    main()
