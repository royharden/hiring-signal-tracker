"""Installed CLI checks using fresh original syntax controls, never an admitted corpus."""

import hashlib
import json
import os
import subprocess
from pathlib import Path

import pytest
import test_workflow as wiring

from hiring_signals.evaluation import workflow as w


@pytest.fixture(scope="module")
def installed_python():
    value = os.environ.get("HST_PORTABLE_PYTHON")
    if not value:
        pytest.skip("requires the current wheel installed in an owned isolated environment")
    return Path(value)


def run(installed_python, cwd, *args):
    allowed = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    guard = """
import sys
checkout = sys.argv.pop(1).lower().replace(chr(92), '/').rstrip('/')
def audit(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen', 'os.system'}:
        raise RuntimeError('outbound_or_child_refused')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = str(args[0]).lower().replace(chr(92), '/')
        denied = ['.creds', '.thinking', '.chatexports', '.agent-registry', 'heldout']
        if path.startswith(checkout + '/') or any('/'+part+'/' in path for part in denied):
            raise RuntimeError('checkout_or_protected_input_refused')
sys.addaudithook(audit)
from hiring_signals.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    result = subprocess.run(
        [str(installed_python), "-I", "-B", "-c", guard, str(w.PRODUCT_ROOT), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    (cwd / "installed.stdout").write_text(result.stdout, encoding="utf-8")
    (cwd / "installed.stderr").write_text(result.stderr, encoding="utf-8")
    return result


@pytest.mark.parametrize("support", [None, 1])
def test_installed_dev_bindings_match_actual_checkout_bytes(installed_python, tmp_path, support):
    """Catches repo-only rubric lookup and location-dependent default/majority bindings."""
    args = ["eval", "--offline", "--show-bindings"]
    if support is not None:
        args += ["--dev-majority-min-support", str(support)]
    result = run(installed_python, tmp_path, *args)
    assert result.returncode == 0 and not result.stderr
    assert json.loads(result.stdout) == w.bindings(dev_majority_min_support=support)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["installed.stderr", "installed.stdout"]


def test_installed_dev_rules_report_and_limitations_use_only_supplied_controls(
    installed_python, tmp_path
):
    """Catches input-free-only portability fixes, raw leaks and bypassed sample suppression."""
    options = wiring.inputs(tmp_path / "input")
    result = run(
        installed_python,
        tmp_path,
        *wiring.command(options),
        "--sample-months",
        "2026-07",
        "2026-08",
        "2026-09",
        "2026-10",
    )
    assert result.returncode == 0 and not result.stderr
    outcome = json.loads(result.stdout)
    assert outcome["count"] == 1 and outcome["field_outcomes"] == 37
    assert outcome["provider_attempts"] == 0 and not outcome["heldout_read"]
    assert outcome["semantic_methods"] == "not_run"
    output = options["destination"]
    seal = json.loads((output / "artifact-manifest.json").read_bytes())
    for name, pin in seal["files"].items():
        data = (output / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == pin["sha256"] and len(data) == pin["bytes"]
    report = output / "sample-report"
    verify = run(installed_python, tmp_path, "report", "verify", "--directory", str(report))
    assert verify.returncode == 0 and not verify.stderr
    public = json.loads((report / "aggregates.json").read_bytes())
    month = public["months"][0]
    assert month["eligible_denominator"] is None
    assert all(
        cell["numerator"] is None and cell["share"] is None
        for partition in month["partitions"]
        for cell in partition["cells"]
    )
    limitations = run(
        installed_python, tmp_path, "report", "limitations", "--directory", str(report)
    )
    assert limitations.returncode == 0 and not limitations.stderr
    assert limitations.stdout == (output / "sample-limitations.md").read_text(encoding="utf-8")
    public_text = "".join(p.read_text(encoding="utf-8") for p in report.iterdir())
    for private in ("Requirements: Python", "SYNTHETIC_PRIVATE_GOLD_PROVENANCE_CANARY", "a" * 64):
        assert private not in public_text + limitations.stdout


@pytest.mark.parametrize("fault", ["manifest_hash", "malformed_source"])
def test_installed_bad_dev_input_refuses_before_output(installed_python, tmp_path, fault):
    """Catches installed workflows accepting wrong hashes or malformed rows and writing state."""
    options = wiring.inputs(tmp_path / "input")
    if fault == "manifest_hash":
        options["manifest_sha256"] = "f" * 64
    else:
        data = b'{"private":"SYNTHETIC_REJECTED_SOURCE_CANARY"}\n'
        options["sources_path"].write_bytes(data)
        options["sources_sha256"] = hashlib.sha256(data).hexdigest()
    result = run(installed_python, tmp_path, *wiring.command(options))
    assert result.returncode == 2 and not result.stdout
    assert json.loads(result.stderr)["private_effects_possible"] is False
    assert "SYNTHETIC_REJECTED_SOURCE_CANARY" not in result.stderr
    assert not options["destination"].exists()
