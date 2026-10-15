"""Entry-point controls for the actual limited scaffold."""

import contextlib
import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
cli = importlib.import_module("hiring_signals.cli")


class ScaffoldTests(unittest.TestCase):
    def test_status_does_not_claim_complete_workflow_or_results(self):
        """Catches a scaffold silently advertised as completed extraction/evaluation."""
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(["status", "--json"])
        result = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(result["stage"], "original_synthetic_cli_and_libraries")
        self.assertIn("domain_contracts", result["implemented"])
        self.assertFalse(result["complete_workflow"])
        self.assertEqual(result["evaluation_status"], "synthetic_dev_rules_only")
        self.assertIn("semantic_cli_extraction", result["unavailable"])
        self.assertIn("deterministic_rules", result["implemented"])
        self.assertIn("population_reporting_library", result["implemented"])
        self.assertIn("annotation_session_library", result["implemented"])
        self.assertIn("offline_rules_screen", result["implemented"])
        self.assertIn("canonical_annotation_journal", result["implemented"])
        self.assertIn("canonical_offline_provider_ledger", result["implemented"])
        self.assertIn("semantic_question_schema_compilers", result["implemented"])
        self.assertIn("synthetic_offline_jev_extraction", result["implemented"])
        self.assertIn("synthetic_generation_counted_repair", result["implemented"])
        self.assertIn("live_generation_content_repair", result["unavailable"])
        self.assertIn("original_synthetic_rules_cli", result["implemented"])

    def test_readiness_needs_no_network_or_credential_values(self):
        """Catches provider startup/env dumping introduced into a keyless command."""
        output = io.StringIO()
        canary = "SYNTHETIC_CREDENTIAL_CANARY_NEVER_A_REAL_KEY"
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": canary, "TYPESAFE_API_KEY": canary}),
            patch("socket.socket", side_effect=AssertionError("network forbidden")),
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(cli.main(["status", "--json"]), 0)
        self.assertNotIn(canary, output.getvalue())

    def test_unimplemented_workflows_fail_without_writes(self):
        """Catches a fake demo/evaluation pass or manufactured result files."""
        for command in (["demo", "--offline"], ["eval", "--dataset", "synthetic", "--offline"]):
            with tempfile.TemporaryDirectory() as directory:
                before = Path.cwd()
                error = io.StringIO()
                try:
                    os.chdir(directory)
                    with contextlib.redirect_stderr(error):
                        self.assertEqual(cli.main(command), 2)
                    self.assertEqual(list(Path(directory).iterdir()), [])
                finally:
                    os.chdir(before)
                self.assertEqual(json.loads(error.getvalue())["code"], "workflow_not_implemented")

    def test_invalid_argument_values_are_not_echoed(self):
        """Catches accidental exposure of rejected imported/secret argument text."""
        error = io.StringIO()
        canary = "SYNTHETIC_UNTRUSTED_ARGUMENT_CANARY"
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as failure:
            cli.main(["status", "--unknown", canary])
        self.assertEqual(failure.exception.code, 2)
        self.assertNotIn(canary, error.getvalue())

    def test_module_command_runs_from_an_unrelated_directory(self):
        """Catches cwd-dependent imports in the actual Python module entry point."""
        with tempfile.TemporaryDirectory() as directory:
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(ROOT / "src")
            completed = subprocess.run(
                [sys.executable, "-m", "hiring_signals", "status", "--json"],
                cwd=directory,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            json.loads(completed.stdout)["stage"], "original_synthetic_cli_and_libraries"
        )

    def test_moved_scripts_use_only_their_detached_package(self):
        """Catches hidden workspace/import dependency or a fake script success."""
        with tempfile.TemporaryDirectory() as directory:
            detached = Path(directory) / "detached"
            shutil.copytree(ROOT / "src", detached / "src")
            shutil.copytree(ROOT / "scripts", detached / "scripts")
            environment = os.environ.copy()
            environment.pop("PYTHONPATH", None)
            for script, args in (
                ("demo.py", ["--offline"]),
                ("eval.py", ["--dataset", "synthetic", "--offline"]),
            ):
                completed = subprocess.run(
                    [sys.executable, str(detached / "scripts" / script), *args],
                    cwd=directory,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=10,
                )
                self.assertEqual(completed.returncode, 2, completed.stderr)
                self.assertEqual(json.loads(completed.stderr)["code"], "workflow_not_implemented")


if __name__ == "__main__":
    unittest.main()
