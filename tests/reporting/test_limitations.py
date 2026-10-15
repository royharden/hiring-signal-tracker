"""Public-only numeric projection controls, not source data or extraction quality."""

import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import test_reporting as h

from hiring_signals import cli
from hiring_signals.reporting import render
from hiring_signals.reporting.limitations import sample_limitations


def window(**changes):
    return render.ReportWindow(
        **(
            dict(
                schema_version=1,
                month_ids=h.MONTHS,
                method="rules",
                source_scope="gold_sample",
                quality_status="not_measured",
                months=(h.public_month(h.MONTHS[-1], scope="gold_sample"),),
            )
            | changes
        )
    )


def test_limitations_cli_reproduces_only_verified_projection_without_writes(tmp_path):
    """Catches accidental input execution or changes to a report during prose regeneration."""
    supplied = window()
    directory = tmp_path / "closed-report"
    render.export_report(supplied, directory)
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        assert cli.main(["report", "limitations", "--directory", str(directory)]) == 0
    assert output.getvalue() == sample_limitations(supplied)
    assert "not_provided" in output.getvalue() and "not population trends" in output.getvalue()
    # The closed schema cannot prove synthetic origin or prior execution history.
    assert "Scope: synthetic" not in output.getvalue()
    assert "was run" not in output.getvalue()
    assert "do not establish source origin" in output.getvalue()
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before
    assert set(tmp_path.iterdir()) == {directory}


@pytest.mark.parametrize("fault", ["changed", "extra", "unsealed", "population", "method"])
def test_invalid_or_wrong_scope_report_never_produces_limitations(tmp_path, fault):
    """Catches using a bad seal or another report scope to assert synthetic rules limitations."""
    changes = {}
    if fault == "population":
        changes = {"source_scope": "population_predictions", "months": ()}
    elif fault == "method":
        changes = {"method": "generative", "months": ()}
    directory = tmp_path / "closed-report"
    render.export_report(window(**changes), directory)
    if fault == "changed":
        (directory / "report.html").write_text("SYNTHETIC_UNTRUSTED_REPORT_CANARY")
    elif fault == "extra":
        (directory / "unexpected.txt").write_text("SYNTHETIC_UNTRUSTED_REPORT_CANARY")
    elif fault == "unsealed":
        (directory / "manifest.json").unlink()
    before = {p.name: p.read_bytes() for p in directory.iterdir()}
    output, error = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
        assert cli.main(["report", "limitations", "--directory", str(directory)]) == 2
    assert output.getvalue() == ""
    assert json.loads(error.getvalue())["private_effects_possible"] is False
    assert "SYNTHETIC_UNTRUSTED_REPORT_CANARY" not in error.getvalue()
    assert {p.name: p.read_bytes() for p in directory.iterdir()} == before


def test_detached_cli_needs_no_evaluator_source_data_or_network(tmp_path):
    """Catches workspace imports or private evaluator loading in the reusable report path."""
    detached = tmp_path / "detached"
    source = Path(__file__).resolve().parents[2] / "src"
    shutil.copytree(source, detached / "src", ignore=shutil.ignore_patterns("__pycache__"))
    report = tmp_path / "report"
    supplied = window()
    render.export_report(supplied, report)
    guard = """
import builtins, runpy, sys
from pathlib import Path
original_import = builtins.__import__
def import_public(name, *args, **kwargs):
    if name.startswith('hiring_signals.evaluation'):
        raise RuntimeError('evaluator_import_forbidden')
    return original_import(name, *args, **kwargs)
builtins.__import__ = import_public
def audit(event, args):
    if event.startswith('socket.'):
        raise RuntimeError('network_forbidden')
    if event == 'open' and isinstance(args[0], str):
        denied = {'.creds', 'heldout', 'private-scratch', '.thinking', '.chatexports'}
        if any(p.casefold() in denied for p in Path(args[0]).parts):
            raise RuntimeError('private_input_forbidden')
sys.addaudithook(audit)
runpy.run_module('hiring_signals', run_name='__main__')
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", guard, "report", "limitations", "--directory", str(report)],
        cwd=detached,
        env={**os.environ, "PYTHONPATH": str(detached / "src")},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == sample_limitations(supplied)
