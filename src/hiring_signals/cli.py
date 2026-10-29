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
            "input_free_keyless_rules_demo",
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
            "synthetic_dev_annotation_cli",
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
            "explicit_synthetic_dev_majority_reference_baseline",
            "explicit_synthetic_dev_semantic_mock_comparison",
            "original_synthetic_rules_cli",
            "original_synthetic_posting_file_cli",
            "public_report_export_verify_cli",
            "public_sample_limitations_cli",
        ],
        "unavailable": [
            "live_cli_ingestion",
            "semantic_cli_extraction",
            "live_acquisition",
            "human_annotation_cli",
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
        "evaluation_status_scope": "default_profile",
        "reference_baseline_status": "explicit_opt_in_synthetic_dev",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = SafeParser(prog="hst", description="Hiring Signal Tracker readiness")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=SafeParser)
    status = commands.add_parser("status", help="Show the current package stage")
    status.add_argument("--json", action="store_true", help="Emit machine-readable metadata")
    demo = commands.add_parser("demo", help="Run four original synthetic records without keys")
    demo.add_argument("--offline", action="store_true")
    demo.add_argument("--out", type=Path, help="New report directory outside the product checkout")
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
    evaluate.add_argument("--sample-months", nargs=4)
    evaluate.add_argument("--sample-policy", choices=["v1", "v2"], default="v1")
    evaluate.add_argument("--dev-majority-min-support", type=int)
    evaluate.add_argument(
        "--semantic-mock",
        action="store_true",
        help="Compare authored constant offline replies; no real model or quality claims",
    )
    annotate = commands.add_parser(
        "annotate", help="Annotate explicit original-synthetic DEV input"
    )
    annotate.add_argument("--show-bindings", action="store_true")
    annotate.add_argument("--manifest", type=Path)
    annotate.add_argument("--manifest-sha256")
    annotate.add_argument("--journal-dir", type=Path)
    run = commands.add_parser(
        "run-synthetic", help="Process an explicit original-synthetic manifest"
    )
    run.add_argument("--input", required=True, type=Path)
    run.add_argument("--private-dir", required=True, type=Path)
    run.add_argument("--out", required=True, type=Path)
    run.add_argument("--lease-seconds", required=True, type=float)
    run.add_argument("--policy", choices=["v1", "v2"], default="v1")
    intake = commands.add_parser("import", help="Import one reviewed original-synthetic posting")
    intake.add_argument("--file", required=True, type=Path)
    intake.add_argument("--review", required=True, type=Path)
    intake.add_argument("--month", required=True)
    intake.add_argument("--source-id", required=True, type=int)
    intake.add_argument("--synthetic-only", action="store_true")
    intake.add_argument("--private-dir", required=True, type=Path)
    intake.add_argument("--lease-seconds", required=True, type=float)
    report = commands.add_parser("report", help="Export or verify closed public report artifacts")
    actions = report.add_subparsers(dest="action", required=True, parser_class=SafeParser)
    export = actions.add_parser("export")
    export.add_argument("--input", required=True, type=Path)
    export.add_argument("--out", required=True, type=Path)
    verify = actions.add_parser("verify")
    verify.add_argument("--directory", required=True, type=Path)
    limitations = actions.add_parser("limitations", help="Reproduce verified sample limitations")
    limitations.add_argument("--directory", required=True, type=Path)
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
    if args.command == "demo" and args.offline:
        from hiring_signals import demo as demo_workflow

        try:
            result = demo_workflow.execute(args.out)
            print(json.dumps(result, sort_keys=True))
            return 0
        except demo_workflow.DemoError as error:
            print(
                json.dumps({"code": error.code, "effects_possible": error.effects_possible}),
                file=sys.stderr,
            )
            return 2
    if args.command == "annotate":
        from hiring_signals.annotation import workflow as annotation

        def read_choice(prompt):
            # Prompts and diagnostics use stderr; stdout remains one closed JSON result.
            print(prompt, end="", file=sys.stderr, flush=True)
            line = sys.stdin.readline(258)
            if not line:
                raise EOFError
            if len(line) > 257 or (len(line) == 257 and not line.endswith("\n")):
                # Do not echo an unbounded/rejected line or treat its tail as new choices.
                raise EOFError
            return line.rstrip("\r\n")

        try:
            supplied = (args.manifest, args.manifest_sha256, args.journal_dir)
            if args.show_bindings and not any(value is not None for value in supplied):
                result = annotation.bindings()
            elif args.show_bindings or not all(value is not None for value in supplied):
                raise annotation.AnnotationError("annotation_explicit_inputs_required")
            else:
                result = annotation.execute(
                    args.manifest,
                    manifest_sha256=args.manifest_sha256,
                    journal_directory=args.journal_dir,
                    reader=read_choice,
                    writer=lambda message: print(message, file=sys.stderr),
                )
            print(json.dumps(result, sort_keys=True))
            return 0 if result.get("status") in {None, "owner_receipts_complete"} else 3
        except annotation.AnnotationError as error:
            print(
                json.dumps(
                    {
                        "code": error.code,
                        "private_effects_possible": error.private_effects_possible,
                        "durable_acknowledgments_this_process": error.durable_acknowledgments,
                    }
                ),
                file=sys.stderr,
            )
            return 2
        except (Exception, KeyboardInterrupt):
            print(
                json.dumps({"code": "annotation_failed", "private_effects_possible": True}),
                file=sys.stderr,
            )
            return 2
    if args.command == "eval" and args.offline:
        supplied = (
            args.manifest,
            args.manifest_sha256,
            args.sources,
            args.sources_sha256,
            args.out,
        )
        if (
            args.show_bindings
            or any(value is not None for value in supplied)
            or args.sample_months is not None
            or args.sample_policy != "v1"
            or args.dev_majority_min_support is not None
            or args.semantic_mock
        ):
            from hiring_signals.evaluation import workflow as evaluation

            try:
                if args.show_bindings:
                    if (
                        any(value is not None for value in supplied)
                        or args.sample_months is not None
                        or args.sample_policy != "v1"
                    ):
                        raise evaluation.EvaluationError("bindings_command_requires_no_input")
                    result = evaluation.bindings(
                        dev_majority_min_support=args.dev_majority_min_support,
                        semantic_mock=args.semantic_mock,
                    )
                elif not all(value is not None for value in supplied):
                    raise evaluation.EvaluationError("explicit_dev_inputs_and_hashes_required")
                else:
                    result = evaluation.execute_dev_rules(
                        args.manifest,
                        manifest_sha256=args.manifest_sha256,
                        sources_path=args.sources,
                        sources_sha256=args.sources_sha256,
                        destination=args.out,
                        sample_months=tuple(args.sample_months)
                        if args.sample_months is not None
                        else None,
                        sample_policy=args.sample_policy,
                        dev_majority_min_support=args.dev_majority_min_support,
                        semantic_mock=args.semantic_mock,
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
    if args.command == "import":
        from hiring_signals.ingest import file_import

        try:
            result = file_import.execute_file_import(
                args.file,
                review_path=args.review,
                month=args.month,
                source_id=args.source_id,
                synthetic_only=args.synthetic_only,
                private_directory=args.private_dir,
                lease_seconds=args.lease_seconds,
            )
            print(json.dumps(result, sort_keys=True))
            return 0
        except file_import.FileImportError as error:
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
                    {"code": "file_import_failed_or_cancelled", "private_effects_possible": True}
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
            elif args.action == "verify":
                result = workflow.verify_public_report(args.directory)
            else:
                print(workflow.public_sample_limitations(args.directory), end="")
                return 0
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
