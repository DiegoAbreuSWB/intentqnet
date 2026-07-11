"""`python -m ibqn.experiments <command> --campaign <file>` (Fase H3, see
the project brief's Fase H3, section 18, and docs/campaign_architecture.md).

No web server, no GUI - six plain subcommands, each doing exactly one
thing:

    validate   schema + file/parameter/strategy checks, no execution
    plan       expected trial count, no execution
    run        executes from scratch (respects CampaignSpec.execution.resume)
    resume     executes, explicitly continuing regardless of that setting
    status     progress from what's already on disk, no execution
    aggregate  writes results/processed/<campaign>/aggregated.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .aggregation import aggregate_records
from .campaigns import load_campaign_file
from .persistence import read_trials_dataframe, trials_csv_path
from .runner import CampaignRunner, CampaignRunSummary
from .status import compute_campaign_status
from .sweeps import expand_parameter_grid
from .validation import validate_trials


def _print_summary(summary: CampaignRunSummary) -> None:
    print(f"Campaign '{summary.campaign}':")
    print(f"  expected:  {summary.expected_trials}")
    print(f"  completed: {summary.completed_trials}")
    print(f"  skipped:   {summary.skipped_trials}")
    print(f"  failed:    {summary.failed_trials}")
    print(f"  duration:  {summary.duration_s:.2f} s")
    for path in summary.output_files:
        print(f"  output:    {path}")


def cmd_validate(args: argparse.Namespace) -> int:
    spec = load_campaign_file(args.campaign)  # raises on any schema/file/parameter/strategy problem
    combinations = expand_parameter_grid(spec.effective_parameter_grid())
    print(f"Campaign '{spec.name}' is valid.")
    print(f"  scenario_file: {spec.scenario_file}")
    print(f"  intents: {spec.intents}")
    print(f"  seeds: {spec.seeds}")
    print(f"  parameter combinations: {len(combinations)}")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    spec = load_campaign_file(args.campaign)
    combinations = expand_parameter_grid(spec.effective_parameter_grid())
    expected = len(combinations) * len(spec.seeds) * len(spec.intents)
    print(f"Campaign '{spec.name}': {expected} expected trial(s), not executed (plan only)")
    print(f"  {len(combinations)} parameter combination(s) x {len(spec.seeds)} seed(s) x {len(spec.intents)} intent(s)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    spec = load_campaign_file(args.campaign)
    summary = CampaignRunner(spec, campaign_file=args.campaign).run()
    _print_summary(summary)
    return 0 if summary.failed_trials == 0 else 1


def cmd_resume(args: argparse.Namespace) -> int:
    spec = load_campaign_file(args.campaign)
    summary = CampaignRunner(spec, campaign_file=args.campaign).run(force_resume=True)
    _print_summary(summary)
    return 0 if summary.failed_trials == 0 else 1


def cmd_status(args: argparse.Namespace) -> int:
    spec = load_campaign_file(args.campaign)
    status = compute_campaign_status(spec, campaign_file=args.campaign)
    print(f"Campaign '{status.campaign}':")
    print(f"  expected:  {status.expected_trials}")
    print(f"  completed: {status.completed_trials}")
    print(f"  failed:    {status.failed_trials}")
    print(f"  remaining: {status.remaining_trials}")
    if status.manifest is not None:
        print(f"  last updated: {status.manifest['updated_at']}")
    return 0


def cmd_aggregate(args: argparse.Namespace) -> int:
    spec = load_campaign_file(args.campaign)
    df = read_trials_dataframe(trials_csv_path(spec.output_directory, spec.name))
    if df.empty:
        print(f"No trials recorded yet for campaign '{spec.name}' - run it first.", file=sys.stderr)
        return 1

    issues = validate_trials(df)
    if issues:
        print(f"WARNING: {len(issues)} validation issue(s) found in {len(df)} trial(s):", file=sys.stderr)
        for issue in issues[:20]:
            print(f"  [{issue.trial_id}] {issue.check}: {issue.message}", file=sys.stderr)
        if len(issues) > 20:
            print(f"  ... and {len(issues) - 20} more", file=sys.stderr)

    group_by = args.group_by.split(",") if args.group_by else ["routing_strategy"]
    aggregated = aggregate_records(df, group_by=group_by)

    out_dir = Path(spec.output_directory) / "processed" / spec.name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "aggregated.csv"
    aggregated.to_csv(out_path, index=False)
    print(f"Wrote {out_path} ({len(aggregated)} row(s), grouped by {group_by})")
    return 0


_COMMANDS = {
    "validate": cmd_validate,
    "plan": cmd_plan,
    "run": cmd_run,
    "resume": cmd_resume,
    "status": cmd_status,
    "aggregate": cmd_aggregate,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m ibqn.experiments")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in _COMMANDS:
        sub = subparsers.add_parser(name)
        sub.add_argument("--campaign", required=True, help="path to a campaign YAML/JSON file")
        if name == "aggregate":
            sub.add_argument(
                "--group-by", default=None,
                help="comma-separated TrialRecord column names to group by (default: routing_strategy)",
            )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
