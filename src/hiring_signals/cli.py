"""Readiness commands, with no posting, credential or provider access."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path


class SafeParser(argparse.ArgumentParser):
    """Keep rejected argument values out of command error output."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, "hst: invalid arguments; use --help.\n")


def scaffold_status() -> dict[str, object]:
    """Return product-stage metadata, never guessed benchmark evidence."""
    return {
        "schema_version": 1,
        "stage": "original_synthetic_cli_and_libraries",
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
            "canonical_offline_provider_ledger",
            "semantic_question_schema_compilers",
            "synthetic_offline_jev_extraction",
            "synthetic_generation_counted_repair",
            "canonical_evalkit_axis_status_library",
            "hiring_reference_codecs",
            "development_majority_fit_library",
            "private_canonical_37field_comparison",
            "private_class_skill_salary_calibration_statistics",
            "explicit_synthetic_dev_rules_evaluation_cli",
            "original_synthetic_rules_cli",
            "public_report_export_verify_cli",
        ],
        "unavailable": [
            "live_cli_ingestion",
            "semantic_cli_extraction",
            "live_acquisition",
            "annotation",
            "heldout_evaluation",
            "semantic_cli_evaluation",
            "real_population_reports",
            "live_generation_content_repair",
            "live_semantic_extraction",
        ],
        "complete_workflow": False,
        "network_required": False,
        "credentials_required": False,
        "evaluation_status": "synthetic_dev_rules_only",
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
    evaluate.add_argument("--show-bindings", action="store_true")
    evaluate.add_argument("--split", choices=["dev"], default="dev")
    evaluate.add_argument("--manifest", type=Path)
    evaluate.add_argument("--manifest-sha256")
    evaluate.add_argument("--sources", type=Path)
    evaluate.add_argument("--sources-sha256")
    evaluate.add_argument("--out", type=Path)
    run = commands.add_parser(
        "run-synthetic", help="Process an explicit original-synthetic manifest"
    )
    run.add_argument("--input", required=True, type=Path)
    run.add_argument("--private-dir", required=True, type=Path)
    run.add_argument("--out", required=True, type=Path)
    run.add_argument("--lease-seconds", required=True, type=float)
    run.add_argument("--policy", choices=["v1", "v2"], default="v1")
    report = commands.add_parser("report", help="Export or verify closed public report artifacts")
    actions = report.add_subparsers(dest="action", required=True, parser_class=SafeParser)
    export = actions.add_parser("export")
    export.add_argument("--input", required=True, type=Path)
    export.add_argument("--out", required=True, type=Path)
    verify = actions.add_parser("verify")
    verify.add_argument("--directory", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "status":
        if args.json:
            print(json.dumps(scaffold_status(), sort_keys=True))
        else:
            print(
                "Hiring Signal Tracker: original-synthetic CLI and local libraries. "
                "Use status --json."
            )
        return 0
    if args.command == "eval" and args.offline:
        supplied = (
            args.manifest,
            args.manifest_sha256,
            args.sources,
            args.sources_sha256,
            args.out,
        )
        if args.show_bindings or any(value is not None for value in supplied):
            from hiring_signals.evaluation import workflow as evaluation

            try:
                if args.show_bindings:
                    if any(value is not None for value in supplied):
                        raise evaluation.EvaluationError("bindings_command_requires_no_input")
                    result = evaluation.bindings()
                elif not all(value is not None for value in supplied):
                    raise evaluation.EvaluationError("explicit_dev_inputs_and_hashes_required")
                else:
                    result = evaluation.execute_dev_rules(
                        args.manifest,
                        manifest_sha256=args.manifest_sha256,
                        sources_path=args.sources,
                        sources_sha256=args.sources_sha256,
                        destination=args.out,
                    )
                print(json.dumps(result, sort_keys=True))
                return 3 if result.get("status") == "partial" else 0
            except evaluation.EvaluationError as error:
                print(
                    json.dumps(
                        {
                            "code": error.code,
                            "private_effects_possible": error.private_effects_possible,
                        }
                    ),
                    file=sys.stderr,
                )
                return 2
            except (Exception, KeyboardInterrupt):
                print(
                    json.dumps(
                        {"code": "evaluation_failed_or_cancelled", "private_effects_possible": True}
                    ),
                    file=sys.stderr,
                )
                return 2
    if args.command in {"run-synthetic", "report"}:
        # Lazy import keeps readiness independent of source/state/model access.
        from hiring_signals import workflow
        from hiring_signals.shared.aggregate_privacy import models as privacy

        try:
            if args.command == "run-synthetic":
                result = workflow.execute_rules(
                    args.input,
                    private_directory=args.private_dir,
                    destination=args.out,
                    lease_seconds=args.lease_seconds,
                    policy=privacy.POLICY_V1 if args.policy == "v1" else privacy.POLICY_V2,
                )
            elif args.action == "export":
                result = workflow.export_public_report(args.input, args.out)
            else:
                result = workflow.verify_public_report(args.directory)
            print(json.dumps(result, sort_keys=True))
            return 3 if result.get("status") in {"partial", "no_eligible_input"} else 0
        except workflow.WorkflowError as error:
            print(
                json.dumps(
                    {"code": error.code, "private_effects_possible": error.private_effects_possible}
                ),
                file=sys.stderr,
            )
            return 2
        except (Exception, KeyboardInterrupt):
            print(
                json.dumps(
                    {
                        "code": "workflow_failed_or_cancelled",
                        "private_effects_possible": args.command == "run-synthetic",
                    }
                ),
                file=sys.stderr,
            )
            return 2
    print(
        json.dumps({"code": "workflow_not_implemented", "workflow": args.command}),
        file=sys.stderr,
    )
    return 2
