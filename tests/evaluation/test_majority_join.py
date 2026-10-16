"""Three owned syntax controls only; not independent Gold, Human labels or quality."""

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest
import test_domain as h
import test_workflow as wiring

from hiring_signals import cli
from hiring_signals.evaluation import domain, majority, workflow
from hiring_signals.shared.evalkit.identity import canonical_bytes

TEXTS = ("Excluded skills: Python", "Do not require Python", "Requirements not stated")


def controls(root):
    root.mkdir()
    bindings = workflow.bindings(dev_majority_min_support=2)
    items, rows, sources = [], [], []
    authority = h.SourceAuthority()
    for index, text in enumerate(TEXTS):
        item, _ = h.item(text)
        pin = item.pin.model_copy(
            update={"item_id": hashlib.sha256(f"owned-{index}".encode()).hexdigest()}
        )
        item, _ = h.item(text, pin=pin, sources=authority)
        row = h.gold(
            item,
            value=False if index < 2 else None,
            presence="present" if index < 2 else "absent",
        )
        group = hashlib.sha256(f"group-{index}".encode()).hexdigest()
        row = row.model_copy(update={"group_id": group})
        label = row.label_payload.labels["portfolio_requested"]
        row.label_payload.labels["portfolio_requested"] = label.model_copy(
            update={
                "presence": "present" if index == 0 else "absent" if index == 1 else "unlabelled",
                "value": False if index == 0 else None,
            }
        )
        items.append(item)
        rows.append(row)
        sources.append(
            {
                "item_id": pin.item_id,
                "source_id": index + 1,
                "month": item.month,
                "group_id": group,
                "split": "dev",
                "text": text,
                "input_sha256": pin.input_sha256,
            }
        )
    manifest = h.freeze(root / "corpus", tuple(rows))

    def ref(name):
        return {
            "schema_version": 1,
            "status": "available",
            "ref": "owned-syntax/1",
            "sha256": bindings[name],
        }

    manifest = manifest.model_copy(
        update={
            "domain_adapter_ref": type(manifest.domain_adapter_ref).model_validate(
                ref("domain_adapter_sha256")
            ),
            "comparator_config": type(manifest.comparator_config).model_validate(
                ref("config_sha256")
            ),
            "experiment_refs": {
                "taxonomy": type(manifest.comparator_config).model_validate(ref("taxonomy_sha256")),
                "rubric": type(manifest.comparator_config).model_validate(ref("rubric_sha256")),
            },
        }
    )
    data = canonical_bytes(manifest.model_dump(mode="json"))
    manifest_path = root / "corpus/manifest.json"
    manifest_path.write_bytes(data)
    source_data = b"".join(canonical_bytes(row) + b"\n" for row in sources)
    source_path = root / "sources.jsonl"
    source_path.write_bytes(source_data)
    assert len(data) + len(source_data) + (root / "corpus/dev.jsonl").stat().st_size <= 262144
    options = dict(
        manifest_path=manifest_path,
        manifest_sha256=hashlib.sha256(data).hexdigest(),
        sources_path=source_path,
        sources_sha256=hashlib.sha256(source_data).hexdigest(),
        destination=root / "results",
    )
    return options, manifest, tuple(items), tuple(rows), authority


def test_actual_optin_cli_three_control_rules_and_majority_join(tmp_path):
    """Catches a fake baseline row, omitted axes, per-item label leakage or invented evidence."""
    options, _, _, _, _ = controls(tmp_path / "input")
    guard = """
import runpy, sys
from pathlib import Path
def audit(event,args):
    if event.startswith('socket.'):
        raise RuntimeError('network_forbidden')
    if event=='open' and isinstance(args[0],str):
        denied={'.creds','heldout','private-scratch','.thinking','.chatexports'}
        if any(p.casefold() in denied for p in Path(args[0]).parts):
            raise RuntimeError('private_input_forbidden')
sys.addaudithook(audit)
runpy.run_module('hiring_signals',run_name='__main__')
"""
    args = wiring.command(options) + ["--dev-majority-min-support", "2"]
    run = subprocess.run(
        [sys.executable, "-B", "-c", guard, *args],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(workflow.PRODUCT_ROOT / "src")},
        capture_output=True,
        timeout=60,
    )
    (tmp_path / "normal.stdout").write_bytes(run.stdout)
    (tmp_path / "normal.stderr").write_bytes(run.stderr)
    assert run.returncode == 0, run.stderr.decode()
    result = json.loads(run.stdout)
    assert result["reference_baseline"] == "run"
    assert result["count"] == 3 and result["reference_baseline_field_outcomes"] == 111
    summary = json.loads((options["destination"] / "private-summary.json").read_bytes())
    metrics = summary["methods"]["dev_majority"]["metrics"]
    assert len(metrics["fields"]) == 37
    assert metrics["salary"]["candidate_policy"] == "not_applicable_learned_reference_baseline/1"
    assert metrics["salary"]["exact_candidate_recall_on_gold_stated"] is None
    assert metrics["fields"]["skills.python"]["end_to_end_accuracy"]["numerator"] == 2
    assert metrics["fields"]["ai_engineering_role"]["answered_coverage"]["numerator"] == 0
    assert summary["methods"]["jev"]["metrics"] is None
    combined = b"".join(p.read_bytes() for p in options["destination"].iterdir())
    assert all(text.encode() not in combined for text in TEXTS)
    assert b"SYNTHETIC_PRIVATE_GOLD_PROVENANCE_CANARY" not in combined
    assert sum(p.stat().st_size for p in options["destination"].iterdir()) <= 4194304


@pytest.mark.parametrize("fault", ["copy", "bytes", "implementation"])
def test_unissued_or_stale_fit_refuses_without_predictions(tmp_path, monkeypatch, fault):
    """Catches hash-shaped copies or changed training/code bytes gaining fit authority."""
    options, manifest, _, _, _ = controls(tmp_path / "input")
    fit = majority.fit_dev_majority(options["manifest_path"].parent, manifest, min_support=2)
    if fault == "copy":
        fit = replace(fit)
    elif fault == "bytes":
        p = options["manifest_path"].parent / "dev.jsonl"
        p.write_bytes(p.read_bytes() + b" ")
    else:
        p = tmp_path / "changed-source.py"
        p.write_bytes(b"# Deliberately changed code fingerprint control\n")
        monkeypatch.setattr(majority, "__file__", str(p))
    with pytest.raises(majority.MajorityFitError, match="unissued_changed_or_stale"):
        majority.validate_fit(fit)


def test_baseline_issuance_has_learned_values_not_fabricated_candidate_references(tmp_path):
    """Catches converting learned guesses into false extraction/source observations."""
    options, manifest, items, rows, authority = controls(tmp_path / "input")
    fit = majority.fit_dev_majority(options["manifest_path"].parent, manifest, min_support=2)
    registry = domain.ExecutionRegistry(items, authority)
    adapter = domain.HiringDomainAdapter(registry)
    runner = domain.HiringMethodRunner(
        registry, "dev_majority", config_sha256=h.H, majority_fit=fit
    )
    public = adapter.to_public_input(rows[0], registry.source_view(rows[0]))
    assert public.public_payload == {"text": TEXTS[0]}
    prediction = runner.predict(public)
    adapter.validate_prediction(prediction)
    assert prediction.machine_output["kind"] == "learned-dev-constant-values/1"
    record = registry._lookup(prediction)[1]
    assert domain.project_record(record) is not domain.project_record(record)
    fields = {r.field_id: r for r in domain.project_record(registry._lookup(prediction)[1])}
    assert fields["skills.python"].value is False
    assert fields["portfolio_requested"].value == "not_stated"
    assert fields["ai_engineering_role"].process_status == "abstained"
    assert all(row.certainty_value is None for row in fields.values())
    assert "candidates" not in json.dumps(prediction.machine_output)
    with pytest.raises(domain.DomainError, match="unissued_or_changed"):
        adapter.validate_prediction(prediction.model_copy(update={"config_sha256": "e" * 64}))
    authority.remove(items[0].pin.item_id)
    with pytest.raises(domain.DomainError, match="no_longer_current"):
        adapter.validate_prediction(prediction)


@pytest.mark.parametrize("fault", ["manifest", "support"])
def test_bad_cli_pins_or_support_refuse_before_fitter_or_extractor(tmp_path, monkeypatch, fault):
    """Catches changed admission/support triggering a fit or silently running rules alone."""
    options, _, _, _, _ = controls(tmp_path / "input")
    if fault == "manifest":
        options["manifest_sha256"] = "0" * 64

    def denied(*a, **k):
        pytest.fail("method reached before refused input")

    monkeypatch.setattr(majority, "fit_dev_majority", denied)
    monkeypatch.setattr(workflow.rules, "classify", denied)
    error = io.StringIO()
    with contextlib.redirect_stderr(error):
        assert (
            cli.main(
                wiring.command(options)
                + ["--dev-majority-min-support", "0" if fault == "support" else "2"]
            )
            == 2
        )
    assert json.loads(error.getvalue())["private_effects_possible"] is False
    assert not options["destination"].exists()
