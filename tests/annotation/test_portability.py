"""Input-free installed-wheel checks; not an annotation or baseline data rerun."""

import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest

from hiring_signals.annotation import workflow as w


@pytest.fixture(scope="module")
def installed():
    value = os.environ.get("HST_PORTABLE_PYTHON")
    wheel = os.environ.get("HST_PORTABLE_WHEEL")
    if not value or not wheel:
        pytest.skip("requires explicitly built wheel installed in an owned isolated environment")
    return Path(value), Path(wheel)


def run(installed, tmp_path, *args):
    allowed = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC"}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    guard = """
import sys
def audit(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system'}:
        raise RuntimeError('outbound_or_child_refused')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        path = str(args[0]).lower().replace(chr(92), '/')
        denied = ['.creds','.thinking','.chatexports','.agent-registry','heldout']
        if any('/'+part+'/' in path for part in denied):
            raise RuntimeError('protected_input_refused')
sys.addaudithook(audit)
from hiring_signals.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    result = subprocess.run(
        [str(installed[0]), "-I", "-B", "-c", guard, *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    (tmp_path / "installed.stdout").write_text(result.stdout, encoding="utf-8")
    (tmp_path / "installed.stderr").write_text(result.stderr, encoding="utf-8")
    return result


def test_installed_bindings_match_exact_checkout_bytes_without_source_inputs(installed, tmp_path):
    """Catches installed commands reaching back to repo-only src/docs paths or cwd imports."""
    result = run(installed, tmp_path, "annotate", "--show-bindings")
    assert result.returncode == 0 and not result.stderr
    assert json.loads(result.stdout) == w.bindings()
    assert w.RUBRIC_PATH == w.PRODUCT_ROOT / "docs/annotation-guide.md"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["installed.stderr", "installed.stdout"]


def test_wheel_contains_exact_rubric_vendor_source_and_notices(installed):
    """Catches a wheel missing the runtime rubric or unchanged canonical producer licenses."""
    with zipfile.ZipFile(installed[1]) as archive:
        expected = {
            "hiring_signals/data/annotation-guide.md": w.RUBRIC_PATH,
            "hiring_signals/data/VENDORED.md": w.PRODUCT_ROOT / "VENDORED.md",
        }
        expected.update(
            {
                "hiring_signals/data/LICENSES/" + p.name: p
                for p in (w.PRODUCT_ROOT / "LICENSES").glob("*.txt")
            }
        )
        expected.update(
            {
                "hiring_signals/shared/rulings/" + p.name: p
                for p in (w.PACKAGE_ROOT / "shared/rulings").glob("*.py")
            }
        )
        assert len(expected) > 10
        for member, path in expected.items():
            assert (
                hashlib.sha256(archive.read(member)).digest()
                == hashlib.sha256(path.read_bytes()).digest()
            )
        assert not any(
            part in name.casefold()
            for name in archive.namelist()
            for part in (".creds", ".chatexports", ".agent-registry", "rulings.jsonl", "/tests/")
        )


def test_installed_partial_binding_arguments_refuse_without_state(installed, tmp_path):
    """Catches resolving source/target paths despite missing explicit annotation inputs."""
    result = run(installed, tmp_path, "annotate", "--show-bindings", "--manifest", "missing.json")
    assert result.returncode == 2 and not result.stdout
    error = json.loads(result.stderr)
    assert error["code"] == "annotation_explicit_inputs_required"
    assert not error["private_effects_possible"]
    assert error["durable_acknowledgments_this_process"] == 0


def test_installed_readiness_still_keyless_incomplete_and_no_dataset(installed, tmp_path):
    """Catches package installation changing readiness into a corpus/model execution."""
    result = run(installed, tmp_path, "status", "--json")
    assert result.returncode == 0 and not result.stderr
    data = json.loads(result.stdout)
    assert not data["network_required"] and not data["credentials_required"]
    assert not data["complete_workflow"]
    assert "synthetic_dev_annotation_cli" in data["implemented"]
