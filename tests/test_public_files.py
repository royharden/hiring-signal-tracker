"""Positive and negative controls for the staged product-text guard."""

import importlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
guard = importlib.import_module("hiring_signals.public_files")


class PublicFileTests(unittest.TestCase):
    def test_clean_text_and_placeholder_environment_are_allowed(self):
        """Catches a guard that rejects harmless product docs/placeholders."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("Original synthetic scaffold", encoding="utf-8")
            (root / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")
            self.assertEqual(guard.check_files(root, ["README.md", ".env.example"]), [])

    def test_planted_key_and_private_key_controls_fail_without_value_output(self):
        """Catches a scanner that scans nothing or leaks the matched secret."""
        canaries = ["sk-" + "A" * 40, "-----BEGIN " + "PRIVATE KEY-----"]
        for canary in canaries:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / "bad.txt").write_text(canary, encoding="utf-8")
                failures = guard.check_files(root, ["bad.txt"])
                self.assertEqual([failure.code for failure in failures], ["sensitive_content"])
                self.assertNotIn(canary, repr(failures))

    def test_private_paths_refuse_before_reading(self):
        """Catches opening credential/private data files during a publication scan."""
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(Path, "read_bytes", side_effect=AssertionError("private contents opened")),
        ):
            paths = [
                ".env",
                ".env.local",
                "data/gold.jsonl",
                ".chatexports/chat.md",
                "key.pem",
                ".ENV",
                "DATA/gold.jsonl",
                ".CREDS/key.txt",
            ]
            failures = guard.check_files(Path(directory), paths)
            self.assertEqual(len(failures), len(paths))
            self.assertTrue(all(failure.code == "private_path" for failure in failures))

    def test_path_escape_refuses_without_external_read(self):
        """Catches traversal/absolute targets bypassing the product-root boundary."""
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.object(
                Path, "read_bytes", side_effect=AssertionError("external contents opened")
            ),
        ):
            failures = guard.check_files(Path(directory), ["../external.txt", str(Path(directory))])
            self.assertEqual(len(failures), 2)
            self.assertTrue(all(failure.code == "invalid_relative_path" for failure in failures))

    def test_nonexistent_binary_and_oversized_inputs_are_explicit_failures(self):
        """Catches silently treating unscannable/bounded-out inputs as clean."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "binary.txt").write_bytes(b"\xff\xfe\xff")
            (root / "large.txt").write_text("oversized", encoding="utf-8")
            with patch.object(guard, "MAX_TEXT_BYTES", 4):
                failures = guard.check_files(root, ["missing.txt", "binary.txt", "large.txt"])
            self.assertEqual(
                {failure.code for failure in failures},
                {"missing_product_file", "unscannable_or_escaped_file", "text_bound_exceeded"},
            )

    def test_cli_checks_staged_blob_instead_of_clean_working_copy(self):
        """Catches a staged secret hidden by editing its working copy before scanning."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "src", root / "src")
            shutil.copytree(ROOT / "scripts", root / "scripts")
            subprocess.run(["git", "init", "--quiet", str(root)], check=True, capture_output=True)
            canary = "sk-" + "B" * 40
            (root / "candidate.txt").write_text(canary, encoding="utf-8")
            subprocess.run(
                ["git", "-C", str(root), "add", "--", "candidate.txt"],
                check=True,
                capture_output=True,
            )
            (root / "candidate.txt").write_text("Clean working copy", encoding="utf-8")
            outcome = subprocess.run(
                [sys.executable, str(root / "scripts" / "check_public_files.py")],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(outcome.returncode, 1, outcome.stderr)
            self.assertEqual(json.loads(outcome.stdout)["violations"], 1)
            self.assertNotIn(canary, outcome.stdout + outcome.stderr)
            subprocess.run(
                ["git", "-C", str(root), "add", "--", "candidate.txt"],
                check=True,
                capture_output=True,
            )
            clean = subprocess.run(
                [sys.executable, str(root / "scripts" / "check_public_files.py")],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertEqual(json.loads(clean.stdout)["source"], "git_index")


if __name__ == "__main__":
    unittest.main()
