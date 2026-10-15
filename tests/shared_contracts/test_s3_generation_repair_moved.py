"""Run the whole published repair suite on an actual isolated canonical source copy."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_full_repair_suite_moved_with_owner_provider_and_network_guards(tmp_path):
    """Catches a repair source closure that works only with an owner app or hidden dependencies."""
    source = ROOT / "src/hiring_signals/shared"
    target = tmp_path / "portable_shared"
    target.mkdir()
    shutil.copyfile(source / "__init__.py", target / "__init__.py")
    for name in ("providers", "callledger"):
        shutil.copytree(source / name, target / name, ignore=shutil.ignore_patterns("__pycache__"))
    files = tuple(p for p in target.rglob("*") if p.is_file())
    assert len(files) == 15
    for path in files:
        assert (
            hashlib.sha256(path.read_bytes()).digest()
            == hashlib.sha256((source / path.relative_to(target)).read_bytes()).digest()
        )
    tests = tmp_path / "tests"
    tests.mkdir()
    for name in ("conftest.py", "test_generation_repair.py"):
        original = (ROOT / "tests/shared_contracts/s3/tests/providers" / name).read_text(
            encoding="utf-8"
        )
        (tests / name).write_text(
            original.replace("hiring_signals.shared", "portable_shared"), encoding="utf-8"
        )
    (tests / "test_guards.py").write_text(
        "import importlib,socket\nimport pytest\n"
        "def test_owner_and_provider_import_guard_positive_control():\n"
        "    for name in ('hiring_signals','llm_router_eval','openai','typesafe'):\n"
        "        with pytest.raises(RuntimeError,match='import blocked'):\n"
        "            importlib.import_module(name)\n"
        "def test_network_guard_positive_control():\n"
        "    with pytest.raises(RuntimeError,match='network blocked'):\n"
        "        socket.create_connection(('example.invalid',443))\n",
        encoding="utf-8",
    )
    script = f"""
import importlib.abc,json,socket,sys
sys.path.insert(0,{str(tmp_path)!r})
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self,name,path=None,target=None):
        if name.split('.')[0] in {{'hiring_signals','llm_router_eval','openai','typesafe'}}:
            raise RuntimeError('import blocked')
sys.meta_path.insert(0,Guard())
def denied(*args,**kwargs):raise RuntimeError('network blocked')
socket.create_connection=denied;socket.socket.connect=denied
import pytest
code=pytest.main([{str(tests)!r},'-q','--tb=short',
    '--junitxml='+{str(tmp_path / "moved.xml")!r}])
assert not any(n.split('.')[0] in {{'hiring_signals','llm_router_eval','openai','typesafe'}}
    for n in sys.modules)
print(json.dumps({{'exit':code,'copied_runtime_files':15,'scope':'whole_repair_plus_two_guards'}}))
raise SystemExit(code)
"""
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    run = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    proof = json.loads(run.stdout.strip().splitlines()[-1])
    assert proof["exit"] == 0 and proof["copied_runtime_files"] == 15
    cases = list(ET.parse(tmp_path / "moved.xml").getroot().iter("testcase"))
    assert len(cases) == len({(c.get("classname"), c.get("name")) for c in cases}) == 42
    assert not any(
        c.find(tag) is not None for c in cases for tag in ("failure", "error", "skipped")
    )
