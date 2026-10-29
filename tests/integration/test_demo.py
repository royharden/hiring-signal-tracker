"""Actual tiny input-free demo, privacy and refusal controls; never benchmark evidence."""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hiring_signals import cli, demo
from hiring_signals.reporting import render

ROOT = Path(__file__).resolve().parents[2]
SECRET = "SYNTHETIC_DEMO_SECRET_NOT_A_KEY"


def verify(destination, result):
    assert result["status"] == "offline_demo_complete"
    assert result["complete_workflow"] is False and result["quality_status"] == "not_measured"
    assert result["provider_calls"] == 0 and result["external_cost_usd"] == "0"
    assert result["semantic_methods"] == result["human_or_heldout"] == "not_run"
    assert result["fixture_sha256"] == demo.FIXTURE_SHA256
    assert result["private_processing_state"] == "temporary_removed"
    assert result["report_directory"] == str(destination)
    assert (
        result["report_manifest_sha256"]
        == hashlib.sha256((destination / "manifest.json").read_bytes()).hexdigest()
    )
    window = render.verify_report(destination)
    assert window.month_ids == demo.MONTHS
    assert all(month.eligible_denominator is None for month in window.months)
    assert all(
        cell.numerator is cell.share is None
        for month in window.months
        for part in month.partitions
        for cell in part.cells
    )
    assert len(window.months) == 4 and all(len(month.partitions) == 37 for month in window.months)
    svg = (destination / "trends.svg").read_text(encoding="utf-8")
    assert "suppressed" in svg and "observed-point" not in svg and "observed-segment" not in svg
    combined = b"".join(p.read_bytes() for p in destination.iterdir()) + json.dumps(result).encode()
    for canary in (demo.IDENTITY, demo.AUTHOR, SECRET, "Duties: build ML systems", "920000"):
        assert canary.encode() not in combined


def test_actual_demo_runs_rules_four_times_cleans_private_state_and_seals_suppressed_report(
    tmp_path, monkeypatch
):
    """Catches fake success, privacy leaks, persistent private state and invented trend points."""
    monkeypatch.setattr("socket.socket", lambda *a, **k: pytest.fail("network reached"))
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    monkeypatch.setenv("TYPESAFE_API_KEY", SECRET)
    scratch, records = [], []
    original_temporary = demo.tempfile.TemporaryDirectory
    original_store = demo.workflow.rules.classify_and_store

    def temporary(*args, **kwargs):
        resource = original_temporary(*args, dir=tmp_path, **kwargs)
        scratch.append(Path(resource.name))
        return resource

    def store(*args, **kwargs):
        record = original_store(*args, **kwargs)
        records.append(record)
        return record

    monkeypatch.setattr(demo.tempfile, "TemporaryDirectory", temporary)
    monkeypatch.setattr(demo.workflow.rules, "classify_and_store", store)
    destination = tmp_path / "report"
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert cli.main(["demo", "--offline", "--out", str(destination)]) == 0
    assert len(records) == 4 and len(scratch) == 1 and not scratch[0].exists()
    assert all(len(record.classification.judgments()) == 37 for record in records)
    assert records[0].classification.skills.python.value is True
    assert records[3].classification.salary.normalization_status == "abstained"
    verify(destination, json.loads(output.getvalue()))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["report"]


def test_no_out_selects_unique_temporary_report_and_repeated_run_is_identical(
    tmp_path, monkeypatch
):
    """Catches a cwd write, overwritten default run or random private IDs entering public output."""
    monkeypatch.setattr(demo.tempfile, "gettempdir", lambda: str(tmp_path))
    first, second = demo.execute(), demo.execute()
    assert first["report_directory"] != second["report_directory"]
    for result in (first, second):
        verify(Path(result["report_directory"]), result)
    one, two = Path(first["report_directory"]), Path(second["report_directory"])
    assert {p.name: p.read_bytes() for p in one.iterdir()} == {
        p.name: p.read_bytes() for p in two.iterdir()
    }


@pytest.mark.parametrize(
    "fault", ["exists", "product", "missing_parent", "private_path", "symlink"]
)
def test_destination_refuses_before_processing_and_preserves_prior_files(
    tmp_path, monkeypatch, fault
):
    """Catches overwriting, product/private-path output and linked-directory writes."""
    destination = tmp_path / "report"
    if fault == "exists":
        destination.mkdir()
        (destination / "keep.txt").write_text("owner data", encoding="utf-8")
    elif fault == "product":
        destination = demo.resources.PRODUCT_ROOT / "REFUSED_DEMO_OUTPUT"
    elif fault == "missing_parent":
        destination = tmp_path / "missing/report"
    elif fault == "private_path":
        destination = tmp_path / ".creds/report"
    else:
        # Portable deterministic seam for the canonical link/reparse detector.
        actual = demo._is_link
        monkeypatch.setattr(demo, "_is_link", lambda p: p == tmp_path or actual(p))
    monkeypatch.setattr(
        demo.workflow, "execute_rules", lambda *a, **k: pytest.fail("processing reached")
    )
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        assert cli.main(["demo", "--offline", "--out", str(destination)]) == 2
    assert json.loads(stderr.getvalue())["effects_possible"] is False
    if fault == "exists":
        assert (destination / "keep.txt").read_text() == "owner data"
    else:
        assert not destination.exists()


def test_fixture_change_refuses_before_processing_and_does_not_echo_source(tmp_path, monkeypatch):
    """Catches a changed built-in source silently treated as the pinned original fixture."""
    original = demo.document()
    original["months"][0]["response"]["children"][0]["text"] = "SYNTHETIC_REJECTED_TEXT"
    monkeypatch.setattr(demo, "document", lambda: original)
    monkeypatch.setattr(
        demo.workflow, "execute_rules", lambda *a, **k: pytest.fail("processing reached")
    )
    with pytest.raises(demo.DemoError) as caught:
        demo.execute(tmp_path / "report")
    assert caught.value.code == "demo_fixture_binding_changed"
    assert caught.value.effects_possible is False and "SYNTHETIC_REJECTED_TEXT" not in str(
        caught.value
    )
    assert list(tmp_path.iterdir()) == []


def test_late_failure_keeps_partial_public_output_and_reports_effects(tmp_path, monkeypatch):
    """Catches a partial report called success or a retry deleting prior effects."""

    def failed(source, *, private_directory, destination, **kwargs):
        destination.mkdir()
        (destination / "report.html").write_text("original partial output", encoding="utf-8")
        raise RuntimeError("SYNTHETIC_FAILURE_CANARY")

    monkeypatch.setattr(demo.workflow, "execute_rules", failed)
    destination = tmp_path / "report"
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        assert cli.main(["demo", "--offline", "--out", str(destination)]) == 2
    assert json.loads(stderr.getvalue())["effects_possible"] is True
    assert "SYNTHETIC_FAILURE_CANARY" not in stderr.getvalue()
    assert (destination / "report.html").read_text() == "original partial output"
    assert not (destination / "manifest.json").exists()


@pytest.mark.parametrize("entry", ["module", "script"])
def test_actual_process_module_and_demo_script_need_no_inputs_credentials_or_network(
    tmp_path, entry
):
    """Catches script/module wiring that only works with supplied inputs or in-process patches."""
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(
        "import sys\n"
        "def audit(event,args):\n"
        " if event.startswith('socket.') or event in {'subprocess.Popen','os.system'}:"
        " raise RuntimeError('outbound_refused')\n"
        " if event=='open' and isinstance(args[0],str) and '.creds' in args[0].lower():"
        " raise RuntimeError('credentials_refused')\n"
        "sys.addaudithook(audit)\n",
        encoding="utf-8",
    )
    environment = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC"}
    }
    environment.update(
        PYTHONPATH=str(guard) + os.pathsep + str(ROOT / "src"),
        PYTHONDONTWRITEBYTECODE="1",
        OPENAI_API_KEY=SECRET,
        TYPESAFE_API_KEY=SECRET,
    )
    command = [sys.executable, "-B"] + (
        ["-m", "hiring_signals", "demo"] if entry == "module" else [str(ROOT / "scripts/demo.py")]
    )
    destination = tmp_path / "report"
    result = subprocess.run(
        command + ["--offline", "--out", str(destination)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0 and not result.stderr
    verify(destination, json.loads(result.stdout))
