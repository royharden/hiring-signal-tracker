"""Small supplied-syntax CLI controls; no independent corpus or benchmark authoring."""

import contextlib
import hashlib
import io
import json
from pathlib import Path

import pytest
import test_domain as h

from hiring_signals import cli
from hiring_signals.evaluation import workflow as w
from hiring_signals.shared.evalkit.identity import canonical_bytes


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inputs(root, *, text="Requirements: Python", source_changes=None, gold_changes=None):
    root.mkdir()
    source, _ = h.item(text)
    gold = h.gold(source).model_copy(update={"group_id": "b" * 64} | (gold_changes or {}))
    manifest = h.freeze(root / "corpus", (gold,))
    actual = w.bindings()

    def pin(name):
        return {
            "schema_version": 1,
            "status": "available",
            "ref": "syntax-control/1",
            "sha256": actual[name],
        }

    document = manifest.model_dump(mode="json") | {
        "domain_adapter_ref": pin("domain_adapter_sha256"),
        "comparator_config": pin("config_sha256"),
        "experiment_refs": {"taxonomy": pin("taxonomy_sha256"), "rubric": pin("rubric_sha256")},
    }
    manifest_path = root / "corpus/manifest.json"
    manifest_data = canonical_bytes(document)
    manifest_path.write_bytes(manifest_data)
    row = {
        "item_id": source.pin.item_id,
        "source_id": 1,
        "month": "2026-10",
        "group_id": "b" * 64,
        "split": "dev",
        "text": text,
        "input_sha256": source.pin.input_sha256,
    } | (source_changes or {})
    data = canonical_bytes(row) + b"\n"
    sources = root / "sources.jsonl"
    sources.write_bytes(data)
    return dict(
        manifest_path=manifest_path,
        manifest_sha256=sha(manifest_data),
        sources_path=sources,
        sources_sha256=sha(data),
        destination=root / "output",
    )


def command(options):
    return [
        "eval",
        "--offline",
        "--dataset",
        "synthetic",
        "--manifest",
        str(options["manifest_path"]),
        "--manifest-sha256",
        options["manifest_sha256"],
        "--sources",
        str(options["sources_path"]),
        "--sources-sha256",
        options["sources_sha256"],
        "--out",
        str(options["destination"]),
    ]


def test_actual_cli_dev_rules_produces_private37field_artifacts_without_network_or_credentials(
    tmp_path, monkeypatch
):
    """Catches no-op success, hidden provider access and synthetic metrics called real quality."""
    options = inputs(tmp_path / "input")
    monkeypatch.setattr("socket.socket", lambda *a, **k: pytest.fail("network reached"))
    monkeypatch.setenv("OPENAI_API_KEY", "SYNTHETIC_SECRET_NEVER_A_REAL_KEY")
    monkeypatch.setenv("TYPESAFE_API_KEY", "SYNTHETIC_SECRET_NEVER_A_REAL_KEY")
    public = io.StringIO()
    with contextlib.redirect_stdout(public):
        assert cli.main(command(options)) == 0
    result = json.loads(public.getvalue())
    assert result["count"] == 1 and result["field_outcomes"] == 37
    assert result["heldout_read"] is False and result["provider_attempts"] == 0
    assert result["semantic_methods"] == "not_run"
    output = options["destination"]
    seal = json.loads((output / "artifact-manifest.json").read_text(encoding="utf-8"))
    for name, pin in seal["files"].items():
        data = (output / name).read_bytes()
        assert len(data) == pin["bytes"] and sha(data) == pin["sha256"]
    summary = json.loads((output / "private-summary.json").read_text(encoding="utf-8"))
    python = summary["methods"]["rules"]["metrics"]["fields"]["skills.python"]
    assert python["end_to_end_accuracy"]["value"] == 1
    assert python["calibration"]["result"] is None
    assert summary["methods"]["jev"]["metrics"] is None
    combined = public.getvalue() + "".join(p.read_text(encoding="utf-8") for p in output.iterdir())
    for private in (
        "Requirements: Python",
        "SYNTHETIC_SECRET_NEVER_A_REAL_KEY",
        "SYNTHETIC_PRIVATE_GOLD_PROVENANCE_CANARY",
        "a" * 64,
    ):
        assert private not in combined
    assert "NA" in (output / "private-metrics.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "fault",
    [
        "source_hash",
        "manifest_hash",
        "gold_hash",
        "manifest_binding",
        "source_missing",
        "source_extra",
        "source_heldout",
        "source_group",
        "source_sha",
        "source_whitespace",
        "human",
        "existing_output",
        "product_output",
        "secret_path",
    ],
)
def test_bad_dev_inputs_refuse_before_output_or_rules_execution(tmp_path, monkeypatch, fault):
    """Catches private/heldout/drift/overwriting input being executed or echoed in errors."""
    changes = {"source_changes": {"split": "heldout"}} if fault == "source_heldout" else {}
    if fault == "source_extra":
        changes = {"source_changes": {"gold": "SYNTHETIC_REJECTED_SOURCE_CANARY"}}
    if fault == "source_group":
        changes = {"source_changes": {"group_id": "c" * 64}}
    if fault == "source_sha":
        changes = {"source_changes": {"input_sha256": "f" * 64}}
    if fault == "source_whitespace":
        changes = {"text": " Requirements: Python "}
    if fault == "human":
        changes = {"gold_changes": {"label_source": "human"}}
    options = inputs(tmp_path / "input", **changes)
    if fault in {"source_hash", "manifest_hash"}:
        options["sources_sha256" if fault == "source_hash" else "manifest_sha256"] = "f" * 64
    elif fault == "source_missing":
        options["sources_path"].write_bytes(b"")
        options["sources_sha256"] = sha(b"")
    elif fault == "gold_hash":
        gold = options["manifest_path"].parent / "dev.jsonl"
        gold.write_bytes(gold.read_bytes() + b" ")
    elif fault == "manifest_binding":
        p = options["manifest_path"]
        document = json.loads(p.read_text(encoding="utf-8"))
        document["comparator_config"]["sha256"] = "f" * 64
        data = canonical_bytes(document)
        p.write_bytes(data)
        options["manifest_sha256"] = sha(data)
    elif fault == "existing_output":
        options["destination"].mkdir()
        (options["destination"] / "preserved.txt").write_text("preserve", encoding="utf-8")
    elif fault == "product_output":
        options["destination"] = w.PRODUCT_ROOT / "SYNTHETIC_REFUSED_TEST_OUTPUT"
    elif fault == "secret_path":
        options["sources_path"] = tmp_path / ".creds/synthetic-do-not-read.jsonl"
    monkeypatch.setattr(w.rules, "classify", lambda *a: pytest.fail("rules reached"))
    error = io.StringIO()
    with contextlib.redirect_stderr(error):
        assert cli.main(command(options)) == 2
    response = json.loads(error.getvalue())
    assert response["private_effects_possible"] is False
    assert "SYNTHETIC_REJECTED_SOURCE_CANARY" not in error.getvalue()
    assert "synthetic-do-not-read" not in error.getvalue()
    if fault == "existing_output":
        assert (options["destination"] / "preserved.txt").read_text() == "preserve"
    else:
        assert not options["destination"].exists()


def test_heldout_cli_option_and_no_input_refuse_before_data_access(tmp_path, monkeypatch):
    """Catches a default corpus run or a heldout flag silently selecting DEV/reading bodies."""
    monkeypatch.setattr(w, "execute_dev_rules", lambda *a, **k: pytest.fail("workflow reached"))
    with contextlib.redirect_stderr(io.StringIO()), pytest.raises(SystemExit) as failure:
        cli.main(["eval", "--offline", "--split", "heldout"])
    assert failure.value.code == 2
    error = io.StringIO()
    with contextlib.redirect_stderr(error):
        assert cli.main(["eval", "--offline"]) == 2
    assert json.loads(error.getvalue())["code"] == "workflow_not_implemented"
    assert list(tmp_path.iterdir()) == []


def test_actual_bindings_command_reads_only_product_metadata_and_is_explicit():
    """Catches a bindings command reading caller data or accepting mixed execution arguments."""
    public = io.StringIO()
    with contextlib.redirect_stdout(public):
        assert cli.main(["eval", "--offline", "--show-bindings"]) == 0
    actual = json.loads(public.getvalue())
    assert (
        len(actual["config_sha256"]) == 64 and actual["support_policy"] == "no_fit_or_intervals/1"
    )
    error = io.StringIO()
    with contextlib.redirect_stderr(error):
        assert cli.main(["eval", "--offline", "--show-bindings", "--manifest", "ignored.json"]) == 2
    assert json.loads(error.getvalue())["code"] == "bindings_command_requires_no_input"


def test_duplicate_source_keys_are_rejected_even_when_actual_byte_hash_matches(
    tmp_path, monkeypatch
):
    """Catches ambiguous JSON receiving different interpretations across intake and execution."""
    options = inputs(tmp_path / "input")
    data = options["sources_path"].read_bytes().replace(b"{", b'{"split":"heldout",', 1)
    options["sources_path"].write_bytes(data)
    options["sources_sha256"] = sha(data)
    monkeypatch.setattr(w.rules, "classify", lambda *a: pytest.fail("rules reached"))
    with pytest.raises(w.EvaluationError):
        w.execute_dev_rules(**options)
    assert not options["destination"].exists()


def test_cancelled_artifact_write_preserves_unsealed_partial_and_reports_possible_effects(
    tmp_path, monkeypatch
):
    """Catches interrupted private writes called complete or silently deleted/replaced."""
    options = inputs(tmp_path / "input")
    original = Path.open

    def stopped(path, *args, **kwargs):
        if path.name == "run.json" and args and args[0] == "xb":
            raise KeyboardInterrupt()
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", stopped)
    with pytest.raises(w.EvaluationError) as failure:
        w.execute_dev_rules(**options)
    assert failure.value.private_effects_possible is True
    assert options["destination"].exists()
    assert not (options["destination"] / "artifact-manifest.json").exists()
