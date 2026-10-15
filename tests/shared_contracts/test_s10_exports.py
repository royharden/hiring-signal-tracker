"""Run entire own public library controls after a real namespace and root move."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_whole_dictionary_and_privacy_suites_without_owner_provider_or_network(tmp_path):
    """Catches a portable claim whose full controls still require owner code or hidden effects."""
    sources = (
        ("skill_dictionary", "portable_dictionary", "tests/dictionary/test_dictionary.py"),
        ("aggregate_privacy", "portable_privacy", "tests/privacy/test_aggregate_core.py"),
    )
    testdir = tmp_path / "tests"
    testdir.mkdir()
    for original, portable, test in sources:
        source = ROOT / "src/hiring_signals/shared" / original
        target = tmp_path / portable
        shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
        for file in source.iterdir():
            if file.is_file():
                assert (
                    hashlib.sha256(file.read_bytes()).digest()
                    == hashlib.sha256((target / file.name).read_bytes()).digest()
                )
        text = (ROOT / test).read_text(encoding="utf-8")
        text = text.replace("hiring_signals.shared." + original, portable)
        (testdir / Path(test).name).write_text(text, encoding="utf-8")
    script = f"""
import importlib,importlib.abc,json,socket,sys
from pathlib import Path
sys.path.insert(0,{str(tmp_path)!r})
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self,name,path=None,target=None):
        if name.split('.')[0] in {{'hiring_signals','openai','typesafe'}}:
            raise RuntimeError('owner or provider import blocked')
sys.meta_path.insert(0,Guard())
def denied(*args,**kwargs):raise RuntimeError('network blocked')
socket.create_connection=denied;socket.socket.connect=denied
try:importlib.import_module('hiring_signals.contracts')
except RuntimeError:pass
else:raise AssertionError('owner import guard did not fire')
try:socket.create_connection(('example.invalid',443))
except RuntimeError:pass
else:raise AssertionError('network guard did not fire')
import pytest
code=pytest.main([{str(testdir)!r},'-q','--tb=short',
    '--junitxml='+{str(tmp_path / "moved.xml")!r}])
assert not any(n=='hiring_signals' or n.startswith('hiring_signals.') for n in sys.modules)
for name,module in tuple(sys.modules.items()):
    if name.startswith(('portable_dictionary','portable_privacy')):
        Path(module.__file__).resolve().relative_to(Path({str(tmp_path)!r}))
print(json.dumps({{'exit':code,'owner_guard':'detected','network_guard':'detected'}}))
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
    assert proof == {"exit": 0, "owner_guard": "detected", "network_guard": "detected"}
    cases = list(ET.parse(tmp_path / "moved.xml").getroot().iter("testcase"))
    assert len(cases) == len({(c.get("classname"), c.get("name")) for c in cases}) == 88
    assert not any(
        c.find(tag) is not None for c in cases for tag in ("failure", "error", "skipped")
    )
