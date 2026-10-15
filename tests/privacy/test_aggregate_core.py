"""Single-partition privacy controls; no population/reporting accuracy claim."""

import ast
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from hiring_signals.shared.aggregate_privacy import models as p

CORE = Path(p.__file__).resolve().parent
CANARY = "SYNTHETIC_PRIVATE_COMPANY_PERSON https://example.invalid/private"


def partition(counts=None, metric="ai_engineering_role", coverage="complete"):
    labels = p.class_inventory(metric)
    counts = [10] * len(labels) if counts is None else counts
    return {
        "month": "2026-10",
        "metric": metric,
        "method": "rules",
        "version_sha256": "a" * 64,
        "evidence_category": "synthetic_expectation",
        "coverage": coverage,
        "denominator": sum(counts),
        "cells": [
            {"label": label, "numerator": count, "uncertainty": None}
            for label, count in zip(labels, counts, strict=True)
        ],
    }


def validate(data):
    return p.Partition.model_validate_json(json.dumps(data))


def test_supported_exhaustive_partition_release():
    """Catches supported cells suppressed or shares using the wrong denominator."""
    result = p.release_partition(validate(partition()))
    assert not result.suppressed and result.trend_eligible
    assert result.denominator == 70
    assert all(cell.numerator == 10 and cell.share == 10 / 70 for cell in result.cells)


@pytest.mark.parametrize("rare", [0, 1, 9])
def test_primary_and_every_complementary_sibling_withheld(rare):
    """Catches subtracting published siblings from a total to reconstruct a rare cell."""
    data = partition([rare, 30, 20, 10, 10, 10, 10])
    data["cells"][1]["uncertainty"] = {"lower": 0.1, "upper": 0.9}
    result = p.release_partition(validate(data))
    assert result.suppressed and not result.trend_eligible
    for cell in result.cells:
        assert cell.numerator is None and cell.share is None and cell.uncertainty is None
    # No lone reconstructible primary is left after all other cells are published.
    assert sum(cell.numerator is not None for cell in result.cells) == 0


@pytest.mark.parametrize("total", [0, 1, 9])
def test_small_denominator_itself_is_withheld(total):
    """Catches a cohort smaller than ten exposed through the public denominator."""
    result = p.release_partition(validate(partition([total, 0, 0, 0, 0, 0, 0])))
    assert result.denominator is None and result.suppressed


@pytest.mark.parametrize("coverage", ["partial", "failed"])
def test_incomplete_month_never_complete_trend(coverage):
    """Catches a supported but incomplete month's rates represented as a complete trend."""
    result = p.release_partition(validate(partition(coverage=coverage)))
    assert result.coverage == coverage and not result.trend_eligible


@pytest.mark.parametrize("format_name", ["json", "table", "chart", "html"])
def test_every_format_projection_preserves_exact_suppression(format_name):
    """Catches a future format adapter falling back to unsuppressed counts/intervals."""
    bundle = p.release_partition(validate(partition([1, 30, 20, 10, 10, 10, 10])))
    projection = p.format_projection(bundle, format_name)
    assert projection == json.loads(bundle.model_dump_json())
    assert all(cell["numerator"] is None and cell["share"] is None for cell in projection["cells"])
    assert CANARY not in json.dumps(projection)


@pytest.mark.parametrize(
    "change",
    [
        {"denominator": 69},
        {"denominator": True},
        {"metric": "company_breakdown"},
        {"version_sha256": CANARY},
        {"evidence_category": "anonymous"},
        {"company": CANARY},
        {"person": CANARY},
        {"source_id": "a" * 64},
        {"url": CANARY},
        {"group_digest": "a" * 64},
        {"marginal_cut": "small_company"},
    ],
)
def test_closed_partition_rejects_privacy_and_scalar_injections(change):
    """Positive controls catch identity-bearing and overlapping marginal inputs in public types."""
    data = partition()
    data.update(change)
    with pytest.raises(ValidationError) as failure:
        validate(data)
    assert CANARY not in str(failure.value)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "reordered", "extra", "negative", "text", "nan"]
)
def test_exhaustive_unique_class_count_boundaries(mutation):
    """Catches missing/error denominators, duplicate classes and invalid numeric scalars."""
    data = partition()
    if mutation == "missing":
        data["cells"].pop()
    elif mutation == "duplicate":
        data["cells"][0]["label"] = data["cells"][1]["label"]
    elif mutation == "reordered":
        data["cells"].reverse()
    elif mutation == "extra":
        data["cells"][0]["snippet"] = CANARY
    elif mutation == "negative":
        data["cells"][0]["numerator"] = -1
    elif mutation == "text":
        data["cells"][0]["numerator"] = "10"
    else:
        data["cells"][0]["uncertainty"] = {"lower": "NaN", "upper": 1.0}
    with pytest.raises(ValidationError):
        validate(data)


def test_released_model_rejects_bypassed_suppression_and_complete_claims():
    """Catches a caller constructing a released-looking object to bypass the release function."""
    bundle = p.release_partition(validate(partition([1, 30, 20, 10, 10, 10, 10])))
    data = json.loads(bundle.model_dump_json())
    data["cells"][0]["numerator"] = 1
    with pytest.raises(ValidationError):
        p.ReleasedPartition.model_validate_json(json.dumps(data))
    partial = p.release_partition(validate(partition(coverage="partial")))
    unchecked = partial.model_copy(update={"trend_eligible": True})
    with pytest.raises(ValidationError):
        p.format_projection(unchecked, "chart")


def test_all_field_inventories_and_generated_closed_schema():
    """Catches owner-free copy closure losing a skill or exporting an open/stale nested schema."""
    # Frozen adopted taxonomy oracle, independent of the library under test.
    FIELD_IDS = (
        "ai_engineering_role",
        "portfolio_requested",
        "seniority",
        "work_mode",
        "employment",
        "skills.python",
        "skills.javascript",
        "skills.typescript",
        "skills.go",
        "skills.rust",
        "skills.java",
        "skills.c",
        "skills.cpp",
        "skills.sql",
        "skills.pytorch",
        "skills.tensorflow",
        "skills.jax",
        "skills.llm_apis",
        "skills.agents",
        "skills.rag",
        "skills.evals",
        "skills.fine_tuning",
        "skills.mcp",
        "skills.vector_db",
        "skills.prompt_engineering",
        "skills.mlops",
        "skills.data_pipelines",
        "skills.kubernetes",
        "skills.aws",
        "skills.gcp",
        "skills.react",
        "skills.node",
        "skills.postgres",
        "skills.distributed_systems",
        "skills.security",
        "salary",
        "location_stated",
    )

    for metric in FIELD_IDS:
        assert p.release_partition(validate(partition(metric=metric))).metric == metric
    schema = json.loads((CORE / "schemas.json").read_text())
    assert schema == p.schema_documents()
    for document in schema.values():
        assert document["x-runtime-validators-required"] is True
        for obj in [document, *document.get("$defs", {}).values()]:
            if obj.get("type") == "object":
                assert obj["additionalProperties"] is False
                assert set(obj["required"]) == set(obj["properties"])


def test_detached_consumer_has_no_owner_app_or_ingest_imports(tmp_path):
    """Catches hidden owner contracts/app dependency or a moved consumer exposing a rare cell."""
    for file in CORE.glob("*.py"):
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("hiring_signals")
            if isinstance(node, ast.Import):
                assert not any(alias.name.startswith("hiring_signals") for alias in node.names)
    shutil.copytree(CORE, tmp_path / "privacy_core", ignore=shutil.ignore_patterns("__pycache__"))
    script = tmp_path / "consumer.py"
    script.write_text(
        "import json,sys\nfrom pathlib import Path\n"
        "sys.path.insert(0,str(Path(__file__).resolve().parent))\n"
        "from privacy_core import Partition,release_partition,format_projection\n"
        "data=Partition.model_validate_json(sys.stdin.read())\n"
        "output=format_projection(release_partition(data),'html')\n"
        "assert output['suppressed']\n"
        "assert all(c['numerator'] is None for c in output['cells'])\n"
        "assert not any(n.startswith('hiring_signals') for n in sys.modules)\n"
        "print('detached-privacy-consumer-pass')\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-I", str(script)],
        cwd=tmp_path,
        input=json.dumps(partition([1, 30, 20, 10, 10, 10, 10])),
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "detached-privacy-consumer-pass"
