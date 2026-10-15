"""Readiness commands, with no posting, credential or provider access."""

import argparse
import json
import sys
from collections.abc import Sequence


class SafeParser(argparse.ArgumentParser):
    """Keep rejected argument values out of command error output."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, "hst: invalid arguments; use --help.\n")


def scaffold_status() -> dict[str, object]:
    """Return product-stage metadata, never guessed benchmark evidence."""
    return {
        "schema_version": 1,
        "stage": "deterministic_libraries_only",
        "implemented": [
            "readiness_command",
            "staged_public_file_checks",
            "domain_contracts",
            "json_schemas",
            "synthetic_ingest",
            "private_state",
            "aggregate_privacy",
            "skill_dictionary",
            "deterministic_rules",
            "population_reporting_library",
            "annotation_session_library",
            "offline_rules_screen",
            "canonical_annotation_journal",
        ],
        "unavailable": [
            "cli_ingestion",
            "cli_extraction",
            "live_acquisition",
            "annotation",
            "evaluation",
            "aggregate_reports",
        ],
        "complete_workflow": False,
        "network_required": False,
        "credentials_required": False,
        "evaluation_status": "not_implemented",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = SafeParser(prog="hst", description="Hiring Signal Tracker readiness")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=SafeParser)
    status = commands.add_parser("status", help="Show the current package stage")
    status.add_argument("--json", action="store_true", help="Emit machine-readable metadata")
    demo = commands.add_parser("demo", help="Check offline demo availability")
    demo.add_argument("--offline", action="store_true")
    evaluate = commands.add_parser("eval", help="Check evaluation availability")
    evaluate.add_argument("--dataset", choices=["synthetic"], default="synthetic")
    evaluate.add_argument("--offline", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "status":
        if args.json:
            print(json.dumps(scaffold_status(), sort_keys=True))
        else:
            print("Hiring Signal Tracker: deterministic libraries only. Use status --json.")
        return 0
    print(
        json.dumps({"code": "workflow_not_implemented", "workflow": args.command}),
        file=sys.stderr,
    )
    return 2
