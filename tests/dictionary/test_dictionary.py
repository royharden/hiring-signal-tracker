"""Small handwritten syntax controls, not Gold, a fixture generator or empirical quality."""

import ast
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from hiring_signals.shared.skill_dictionary import core as d

CORE = Path(d.__file__).resolve().parent

# Independent handoracles; do not derive expected labels from catalog matching.
POSITIVE = [
    ("python", "Python"),
    ("javascript", "JavaScript"),
    ("typescript", "TypeScript"),
    ("go", "Go"),
    ("rust", "Rust"),
    ("java", "Java"),
    ("c", "C"),
    ("cpp", "C++"),
    ("sql", "SQL"),
    ("pytorch", "PyTorch"),
    ("tensorflow", "TensorFlow"),
    ("jax", "JAX"),
    ("llm_apis", "LLM APIs"),
    ("agents", "AI agents"),
    ("rag", "RAG"),
    ("evals", "evals"),
    ("fine_tuning", "fine-tuning"),
    ("mcp", "Model Context Protocol"),
    ("vector_db", "vector databases"),
    ("prompt_engineering", "prompt engineering"),
    ("mlops", "MLOps"),
    ("data_pipelines", "data pipelines"),
    ("kubernetes", "K8s"),
    ("aws", "Amazon Web Services"),
    ("gcp", "Google Cloud Platform"),
    ("react", "React.js"),
    ("node", "Node.js"),
    ("postgres", "PostgreSQL"),
    ("distributed_systems", "distributed systems"),
    ("security", "security"),
]


def by_id(text):
    return {signal.skill_id: signal for signal in d.scan(text)}


@pytest.mark.parametrize("skill,phrase", POSITIVE)
def test_thirty_independent_requested_skill_controls(skill, phrase):
    """Catches any required taxonomy skill lacking a working original positive pattern."""
    text = f"Requirements: {phrase}"
    signal = by_id(text)[skill]
    assert signal.input_sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert signal.status == "requested"
    assert len(signal.matches) >= 1
    assert any(
        text.encode()[match.start_byte : match.end_byte].decode().lower() == phrase.lower()
        for match in signal.matches
    )


@pytest.mark.parametrize(
    "text,skill",
    [
        ("Requirements: go to market", "go"),
        ("Requirements: Go-to-market", "go"),
        ("Requirements: Series C", "c"),
        ("Requirements: C-level experience", "c"),
        ("Requirements: C++", "c"),
        ("Requirements: C#", "c"),
        ("Requirements: vitamin C", "c"),
        ("Requirements: JavaScript", "java"),
        ("Requirements: TypeScript", "javascript"),
        ("Requirements: CPython", "python"),
        ("Requirements: real estate agents", "agents"),
        ("A Python mascot appears in our newsletter.", "python"),
    ],
)
def test_word_case_language_and_context_traps(text, skill):
    """Catches Go/C/Java and incidental nontechnical text counted as requested technology."""
    assert by_id(text)[skill].status == "not_stated"


@pytest.mark.parametrize(
    "text,expected",
    [
        ("No Python required.", "excluded"),
        ("Python not required.", "excluded"),
        ("No experience with Python required.", "excluded"),
        ("Requirements: Python\nPython not required.", "conflicting"),
        ("Python optional.", "uncertain"),
        ("Maybe Python", "uncertain"),
        ("No requirements are supplied.", "not_stated"),
    ],
)
def test_explicit_negation_conflict_optional_and_absence(text, expected):
    """Catches absence or optional/conflicting evidence collapsed into explicit false."""
    assert by_id(text)["python"].status == expected


def test_negation_scope_and_count_once():
    """Catches one excluded clause negating another skill, or repeated aliases counted twice."""
    signals = by_id("No Python, Go required.\nSkills: PostgreSQL, Postgres, PostgreSQL")
    assert signals["python"].status == "excluded"
    assert signals["go"].status == "requested"
    assert signals["postgres"].status == "requested"
    assert len([signal for signal in signals.values() if signal.skill_id == "postgres"]) == 1
    assert by_id("Requirements: no Python and Go")["go"].status == "uncertain"


def test_reference_bound_keeps_late_opposite_evidence_and_unicode_offsets():
    """Catches clipping away late negation or returning character offsets as UTF-8 offsets."""
    text = "éé Python required.\n" + "Python required.\n" * 20 + "No Python required."
    signal = by_id(text)["python"]
    assert signal.status == "conflicting" and len(signal.matches) <= 8
    assert {match.polarity for match in signal.matches} == {"requested", "excluded"}
    assert signal.matches[0].start_byte == 5
    for match in signal.matches:
        assert text.encode()[match.start_byte : match.end_byte] == b"Python"


def test_catalog_and_exhaustive_schema_have_no_owner_dependency_or_source_quote():
    """Catches taxonomy drift, open models or raw match text accidentally made serializable."""
    # Frozen adopted taxonomy oracle, independent of the library under test.
    SKILL_IDS = (
        "python",
        "javascript",
        "typescript",
        "go",
        "rust",
        "java",
        "c",
        "cpp",
        "sql",
        "pytorch",
        "tensorflow",
        "jax",
        "llm_apis",
        "agents",
        "rag",
        "evals",
        "fine_tuning",
        "mcp",
        "vector_db",
        "prompt_engineering",
        "mlops",
        "data_pipelines",
        "kubernetes",
        "aws",
        "gcp",
        "react",
        "node",
        "postgres",
        "distributed_systems",
        "security",
    )

    assert tuple(entry.skill_id for entry in d.CATALOG) == SKILL_IDS
    assert tuple(signal.skill_id for signal in d.scan("")) == SKILL_IDS
    assert json.loads((CORE / "schemas.json").read_text()) == d.schema_documents()
    assert len(d.catalog_sha256()) == 64
    data = d.scan("Requirements: Python")[0].model_dump(mode="json")
    assert "text" not in data and "quote" not in data
    for changed in (
        {**data, "raw_text": "SYNTHETIC_PRIVATE_CANARY"},
        {**data, "status": "excluded"},
    ):
        with pytest.raises(ValidationError):
            d.SkillSignal.model_validate_json(json.dumps(changed))
    with pytest.raises(ValueError):
        d.scan("é" * 16385)
    with pytest.raises(ValidationError):
        d.Match(alias_index=True, start_byte=0, end_byte=5, polarity="requested")
    data["matches"][0]["alias_index"] = 7
    with pytest.raises(ValidationError):
        d.SkillSignal.model_validate_json(json.dumps(data))


@pytest.mark.parametrize("consumer", ["M2", "M9"])
def test_actual_detached_dictionary_consumers(tmp_path, consumer):
    """Catches owner app/ingest imports or consumer copy losing negation/offset semantics."""
    for file in CORE.glob("*.py"):
        for node in ast.walk(ast.parse(file.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("hiring_signals")
            if isinstance(node, ast.Import):
                assert not any(alias.name.startswith("hiring_signals") for alias in node.names)
    shutil.copytree(CORE, tmp_path / "dictionary", ignore=shutil.ignore_patterns("__pycache__"))
    script = tmp_path / "consumer.py"
    script.write_text(
        "import sys\nfrom pathlib import Path\n"
        "sys.path.insert(0,str(Path(__file__).resolve().parent))\n"
        "from dictionary import scan\n"
        "signals={s.skill_id:s for s in scan('No Python, Go required.')}\n"
        "assert signals['python'].status=='excluded'\n"
        "assert signals['go'].status=='requested'\n"
        "assert not any(n.startswith('hiring_signals') for n in sys.modules)\n"
        "print(sys.argv[1]+'-detached-pass')\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-I", str(script), consumer],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == consumer + "-detached-pass"
