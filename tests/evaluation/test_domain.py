"""Actual concrete comparison controls; tiny original dev examples, not a benchmark."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from test_labels import reference

from hiring_signals import contracts as c
from hiring_signals.adapters.rulings import SourceAuthority
from hiring_signals.annotation.models import SourcePin
from hiring_signals.evaluation import domain as d
from hiring_signals.shared.evalkit.corpus import FrozenCorpusError
from hiring_signals.shared.evalkit.identity import ordered_ids_digest
from hiring_signals.shared.evalkit.models import Manifest, SourceRef
from hiring_signals.shared.evalkit.runner import MethodConfig, compare
from hiring_signals.shared.providers.captures import FixtureIndex

ROOT = Path(__file__).resolve().parents[1]


def helper(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


JEV = helper("domain_public_jev_controls", ROOT / "adapters/test_providers.py")
GEN = helper("domain_public_generation_controls", ROOT / "adapters/test_generation.py")
H = "f" * 64


def item(text, *, pin=None, sources=None):
    source = c.TransientInput(input_sha256=hashlib.sha256(text.encode()).hexdigest(), text=text)
    if pin is None:
        pin = SourcePin(
            item_id="a" * 64,
            raw_source_sha256=source.input_sha256,
            input_sha256=source.input_sha256,
            evidence_revision_sha256="b" * 64,
            taxonomy_sha256="c" * 64,
            rubric_sha256="d" * 64,
        )
    sources = sources or SourceAuthority()
    sources.install(pin, source)
    return d.SourceItem(pin, source, "2026-10"), sources


def gold(source, *, field="skills.python", value=True, presence="present"):
    row = reference(field, value, presence)
    return row.model_copy(
        update={
            "item_id": source.pin.item_id,
            "input_sha256": source.pin.input_sha256,
            "source_ref": SourceRef(handle=source.pin.item_id, sha256=source.pin.input_sha256),
            "label_provenance_ref": "SYNTHETIC_PRIVATE_GOLD_PROVENANCE_CANARY",
        }
    )


def freeze(root, rows):
    root.mkdir(parents=True, exist_ok=True)
    data = b"".join(row.model_dump_json().encode() + b"\n" for row in rows)
    (root / "dev.jsonl").write_bytes(data)
    ids = tuple(row.item_id for row in rows)
    pinned = dict(status="available", ref="synthetic-domain-control/1", sha256=H)
    manifest = Manifest.model_validate_json(
        json.dumps(
            {
                "manifest_id": "synthetic-domain-control",
                "parent_manifest_sha256": None,
                "split_seed": 20261014,
                "partition_provenance": "seeded",
                "frozen_at": "2026-10-14T00:00:00Z",
                "scorer_version": "hiring-field-exact/1",
                "comparator_config": pinned,
                "domain_adapter_ref": pinned,
                "experiment_refs": {},
                "splits": [
                    {
                        "split": "dev",
                        "items_file": "dev.jsonl",
                        "item_count": len(rows),
                        "ordered_item_ids": ids,
                        "items_sha256": hashlib.sha256(data).hexdigest(),
                        "ordered_ids_sha256": ordered_ids_digest(ids),
                        "group_ids": list(dict.fromkeys(row.group_id for row in rows)),
                    }
                ],
                "group_split_map": {row.group_id: "dev" for row in rows},
                "group_members": {
                    group: [row.item_id for row in rows if row.group_id == group]
                    for group in dict.fromkeys(row.group_id for row in rows)
                },
                "source_artifacts": [
                    {
                        "namespace": "synthetic-control",
                        "status": "available",
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "count": len(ids),
                        "member_ids": ids,
                    }
                ],
                "publication_policy": {
                    "mode": "aggregate_only",
                    "allowed_dimensions": [],
                    "allowed_value_sets": {},
                    "allowed_numeric_metrics": [],
                    "synthetic_example_refs": [],
                },
                "run_history_ref": "synthetic-control-history",
            }
        )
    )
    return manifest


def test_actual_rules_comparison_fixed37_axes_gold_private_and_neverrun_no_fake_calls(tmp_path):
    """Catches fake baseline rows, missing fields or scorer labels leaking into method input."""
    source, authority = item("Requirements: Python")
    registry = d.ExecutionRegistry((source,), authority)
    adapter = d.HiringDomainAdapter(registry)
    runner = d.HiringMethodRunner(registry, "rules", config_sha256=H)
    row = gold(source)
    public = adapter.to_public_input(row, registry.source_view(row))
    assert public.public_payload == {"text": "Requirements: Python"}
    assert "SYNTHETIC_PRIVATE_GOLD" not in public.model_dump_json()
    manifest = freeze(tmp_path, (row,))
    result = d.compare_hiring(
        tmp_path,
        manifest,
        "dev",
        {"rules": runner.method_config(), "jev": MethodConfig("disabled", H, "synthetic", None)},
        adapter,
    )
    actual = result.methods["rules"]
    assert len(actual.actual_predictions) == 1 and len(actual.outcomes) == 37
    assert tuple((r.field, r.class_name) for r in actual.outcomes) == d.AXES
    python = next(r for r in actual.outcomes if r.field == "skills.python")
    assert python.correct is True and python.status == "ok"
    assert sum(r.eligibility == "eligible" for r in actual.outcomes) == 1
    never = result.methods["jev"]
    assert never.status == "not_run" and never.actual_predictions == never.outcomes == ()
    assert never.calls_observed == 0


@pytest.mark.parametrize("present_group", [0, 1])
def test_actual_split_jev_partial_envelope_retains_children_failures_and_complete37(
    tmp_path, present_group
):
    """Catches partial native execution promoted to success or erasing valid groups."""
    rig = JEV.AppRig(tmp_path / "jev.sqlite3", "split")
    source, _ = item("Requirements: Python", pin=rig.pin, sources=rig.sources)
    registry = d.ExecutionRegistry((source,), rig.sources)
    adapter = d.HiringDomainAdapter(registry)
    capture = rig.captures()[present_group]
    provider = rig.provider(
        "strict_replay", fixtures=FixtureIndex((capture,)), capture_mode="fixture_replay"
    )
    manifest = freeze(tmp_path / "corpus", (gold(source),))
    with rig.open(offline=True) as ledger:
        binding = d.JevBinding(
            rig.source,
            rig.bundle,
            rig.decisions,
            provider,
            ledger,
            rig.authority,
            rig.context(),
            rig.limits,
            rig.plan(offline=True, count=2),
        )
        runner = d.HiringMethodRunner(
            registry,
            "jev",
            config_sha256=rig.context().config_sha256,
            bindings={source.pin.item_id: binding},
        )
        result = d.compare_hiring(
            tmp_path / "corpus", manifest, "dev", {"jev": runner.method_config()}, adapter
        )
        execution = result.methods["jev"]
        prediction = execution.actual_predictions[0]
        assert prediction.status == "ok"  # Valid domain envelope, explicitly partial operation.
        assert prediction.domain_payload["controller_status"] == "partial"
        assert prediction.issues == ("partial_execution",)
        raw = prediction.machine_output["controller"]
        assert raw["status"] == "partial" and len(raw["native_children"]) == 2
        assert raw["lookup_statuses"][present_group] == "ok"
        assert len(execution.outcomes) == 37
        counts = {
            status: sum(r.status == status for r in execution.outcomes)
            for status in ("ok", "provider_error")
        }
        assert counts == (
            {"ok": 7, "provider_error": 30}
            if present_group == 0
            else {"ok": 30, "provider_error": 7}
        )
        assert ledger.totals()["dispatched_attempts"] == 0
        assert prediction.ledger_refs == tuple(
            dict.fromkeys(
                child["accounting_ref"]
                for child in raw["native_children"]
                if child["accounting_ref"] is not None
            )
        )
        assert all(child["counters"]["used_attempts"] == 0 for child in raw["native_children"])


def test_actual_generation_repair_prediction_has_synthetic_origin_and_physical_refs(tmp_path):
    """Catches simulation called live or lost actual repair attempt/capture references."""
    rig = GEN.Rig(tmp_path / "gen.sqlite3")
    source, _ = item("Requirements: Python\nSalary:100000-120000", pin=rig.pin, sources=rig.sources)
    registry = d.ExecutionRegistry((source,), rig.sources)
    adapter = d.HiringDomainAdapter(registry)
    manifest = freeze(tmp_path / "corpus", (gold(source),))
    transport = GEN.helper.Spy(
        rig, [GEN.helper.response(rig.body("bad JSON")), GEN.helper.response(rig.body())]
    )
    with rig.open() as ledger:
        binding = d.GenerationBinding(
            rig.source,
            rig.bundle,
            rig.repair,
            rig.provider(transport=transport),
            ledger,
            rig.authority,
            rig.context(),
            rig.limits,
            rig.plan(),
        )
        runner = d.HiringMethodRunner(
            registry,
            "generative",
            config_sha256=rig.repair.base_config_sha256,
            bindings={source.pin.item_id: binding},
        )
        result = d.compare_hiring(
            tmp_path / "corpus", manifest, "dev", {"generative": runner.method_config()}, adapter
        )
        prediction = result.methods["generative"].actual_predictions[0]
        raw = prediction.machine_output["controller"]
        assert prediction.origin == "synthetic" and raw["live_provider_evidence"] is False
        assert (
            raw["child_counters"]["used_attempts"] == 2
            and raw["child_counters"]["repairs_used"] == 1
        )
        assert (
            raw["source_capture"]["request_identity_sha256"] == raw["final_physical_request_sha256"]
        )
        assert set(raw["attempt_ids"]) <= set(prediction.ledger_refs)
        assert len(result.methods["generative"].outcomes) == 37


@pytest.mark.parametrize("mutation", ["status", "record", "origin", "config", "human", "child"])
def test_changed_or_unissued_prediction_cannot_gain_axis_authority(mutation):
    """Catches matching-looking hashes/typed payloads granting arbitrary field-status authority."""
    source, authority = item("Requirements: Python")
    registry = d.ExecutionRegistry((source,), authority)
    adapter = d.HiringDomainAdapter(registry)
    runner = d.HiringMethodRunner(registry, "rules", config_sha256=H)
    public = adapter.to_public_input(gold(source), registry.source_view(gold(source)))
    prediction = runner.predict(public)
    data = prediction.model_dump(mode="json")
    if mutation == "status":
        data["status"] = "provider_error"
    elif mutation == "record":
        data["machine_output"]["record"]["classification"]["skills"]["python"]["value"] = False
    elif mutation == "origin":
        data["origin"] = "live"
    elif mutation == "config":
        data["config_sha256"] = "e" * 64
    elif mutation == "human":
        data["human_effective_output"] = {"skills.python": True}
        data["human_provenance_ref"] = H
    else:
        data["machine_output"]["controller"]["native_children"] = []
    from hiring_signals.shared.evalkit.models import Prediction

    forged = Prediction.model_validate_json(json.dumps(data))
    with pytest.raises(d.DomainError):
        adapter.bind(forged)
    # A clean payload from another registry is also not an execution receipt here.
    empty = d.HiringDomainAdapter(d.ExecutionRegistry((source,), authority))
    with pytest.raises(d.DomainError):
        empty.bind(prediction)


@pytest.mark.parametrize("state", ["removed", "unavailable", "source_hash"])
def test_whole_source_failures_keep_all37_without_promoting_success(tmp_path, state):
    """Catches stale/unavailable cases disappearing or becoming successful absent fields."""
    source, authority = item("Requirements: Python")
    row = gold(source)
    items = () if state == "unavailable" else (source,)
    registry = d.ExecutionRegistry(items, authority)
    if state == "removed":
        authority.remove(source.pin.item_id)
    if state == "source_hash":
        row = row.model_copy(update={"input_sha256": H})
    adapter = d.HiringDomainAdapter(registry)
    runner = d.HiringMethodRunner(registry, "rules", config_sha256=H)
    manifest = freeze(tmp_path, (row,))
    result = d.compare_hiring(tmp_path, manifest, "dev", {"rules": runner.method_config()}, adapter)
    method = result.methods["rules"]
    assert method.actual_predictions == () and len(method.outcomes) == 37
    assert all(
        r.status in {"stale", "unavailable"} and r.correct is not True for r in method.outcomes
    )


def test_extra_gold_key_in_public_input_and_untrusted_runner_reject_before_dispatch(tmp_path):
    """Catches private source metadata or an arbitrary runner bypassing issuance."""
    source, authority = item("Requirements: Python")
    registry = d.ExecutionRegistry((source,), authority)
    adapter = d.HiringDomainAdapter(registry)
    row = gold(source)
    from hiring_signals.shared.evalkit.runner import SourceView

    with pytest.raises(d.DomainError):
        adapter.to_public_input(
            row,
            SourceView(
                "available",
                source.pin.input_sha256,
                {"text": source.source.text, "gold": "PRIVATE_GOLD_CANARY"},
            ),
        )

    class Untrusted:
        def predict(self, public):
            raise AssertionError("must never dispatch")

    manifest = freeze(tmp_path, (row,))
    with pytest.raises(d.DomainError, match="untrusted_or_changed"):
        d.compare_hiring(
            tmp_path,
            manifest,
            "dev",
            {"rules": MethodConfig("fake", H, "synthetic", Untrusted())},
            adapter,
        )


def test_frozen_source_bytes_tampering_rejects_before_method_dispatch(tmp_path):
    """Catches valid-looking records bypassing the actual frozen-file digest check."""
    source, authority = item("Requirements: Python")
    registry = d.ExecutionRegistry((source,), authority)
    adapter = d.HiringDomainAdapter(registry)
    manifest = freeze(tmp_path, (gold(source),))
    file = tmp_path / "dev.jsonl"
    file.write_bytes(file.read_bytes() + b" ")
    with pytest.raises(FrozenCorpusError, match="frozen_corpus_bytes_changed"):
        d.compare_hiring(
            tmp_path,
            manifest,
            "dev",
            {"rules": d.HiringMethodRunner(registry, "rules", config_sha256=H).method_config()},
            adapter,
        )
    assert registry._issued == {}


def test_default_canonical_whole_guard_still_rejects_mixed_fields_without_port(tmp_path):
    """Catches this consumer weakening the canonical default guard to make partial outputs pass."""
    source, authority = item("Salary: USD200-100 per year")
    registry = d.ExecutionRegistry((source,), authority)
    adapter = d.HiringDomainAdapter(registry)
    row = gold(source, field="salary", value=None, presence="unlabelled")
    manifest = freeze(tmp_path, (row,))
    runner = d.HiringMethodRunner(registry, "rules", config_sha256=H)
    with pytest.raises(FrozenCorpusError, match="adapter_status_mismatch"):
        compare(
            {"rules": runner.method_config()},
            manifest,
            "dev",
            (row,),
            adapter,
            "hiring-field-exact/1",
            registry.source_view,
        )


@pytest.mark.parametrize(
    "text,value,presence",
    [("No Python required.", False, "present"), ("Details pending.", None, "absent")],
)
def test_actual_field_outcomes_distinguish_false_and_absent(tmp_path, text, value, presence):
    """Catches the full comparison seam collapsing an explicit false into unstated or vice versa."""
    source, authority = item(text)
    registry = d.ExecutionRegistry((source,), authority)
    adapter = d.HiringDomainAdapter(registry)
    manifest = freeze(tmp_path, (gold(source, value=value, presence=presence),))
    runner = d.HiringMethodRunner(registry, "rules", config_sha256=H)
    result = d.compare_hiring(tmp_path, manifest, "dev", {"rules": runner.method_config()}, adapter)
    row = next(x for x in result.methods["rules"].outcomes if x.field == "skills.python")
    assert row.correct is True
    assert row.expected is False if presence == "present" else row.expected == "not_stated"


def test_source_removed_after_issuance_has_no_current_axis_authority():
    """Catches a historical successful execution being treated as a current source approval."""
    source, authority = item("Requirements: Python")
    registry = d.ExecutionRegistry((source,), authority)
    adapter = d.HiringDomainAdapter(registry)
    runner = d.HiringMethodRunner(registry, "rules", config_sha256=H)
    prediction = runner.predict(
        adapter.to_public_input(gold(source), registry.source_view(gold(source)))
    )
    authority.remove(source.pin.item_id)
    with pytest.raises(d.DomainError, match="issued_source_no_longer_current"):
        adapter.bind(prediction)


def test_forged_native_child_request_ref_cannot_issue_fields(tmp_path, monkeypatch):
    """Catches a well-shaped child receipt from a different physical request being trusted."""
    rig = JEV.AppRig(tmp_path / "jev.sqlite3")
    source, _ = item("Requirements: Python", pin=rig.pin, sources=rig.sources)
    registry = d.ExecutionRegistry((source,), rig.sources)
    adapter = d.HiringDomainAdapter(registry)
    provider = rig.provider(
        "strict_replay", fixtures=FixtureIndex(rig.captures()), capture_mode="fixture_replay"
    )
    manifest = freeze(tmp_path / "corpus", (gold(source),))
    with rig.open(offline=True) as ledger:
        packet = rig.run(ledger, provider=provider)
        forged = packet.model_copy(
            update={
                "native_children": (
                    packet.native_children[0].model_copy(update={"request_identity_sha256": H}),
                )
            }
        )
        monkeypatch.setattr(d.jev_adapter, "run_jev_offline", lambda *a, **kw: forged)
        binding = d.JevBinding(
            rig.source,
            rig.bundle,
            rig.decisions,
            provider,
            ledger,
            rig.authority,
            rig.context(),
            rig.limits,
            rig.plan(offline=True),
        )
        runner = d.HiringMethodRunner(
            registry,
            "jev",
            config_sha256=rig.context().config_sha256,
            bindings={source.pin.item_id: binding},
        )
        result = d.compare_hiring(
            tmp_path / "corpus", manifest, "dev", {"jev": runner.method_config()}, adapter
        )
    assert registry._issued == {} and result.methods["jev"].actual_predictions == ()
    assert all(x.status == "provider_error" for x in result.methods["jev"].outcomes)


def test_missing_heldout_authority_rejects_before_the_data_reader(tmp_path, monkeypatch):
    """Catches reading a heldout Gold body before checking that admission/history are supplied."""
    source, authority = item("Requirements: Python")
    registry = d.ExecutionRegistry((source,), authority)
    adapter = d.HiringDomainAdapter(registry)
    manifest = freeze(tmp_path, (gold(source),))
    called = []
    monkeypatch.setattr(d, "load_corpus", lambda *args: called.append(True))
    with pytest.raises(
        d.DomainError, match="heldout_admission_and_history_required_before_data_read"
    ):
        d.compare_hiring(tmp_path, manifest, "heldout", {}, adapter)
    assert called == []


def test_wholly_failed_native_execution_never_invokes_field_status_port(tmp_path, monkeypatch):
    """Catches whole native failure being reclassified as a successful domain envelope."""
    rig = JEV.AppRig(tmp_path / "missing-all.sqlite3", "split")
    source, _ = item("Requirements: Python", pin=rig.pin, sources=rig.sources)
    registry = d.ExecutionRegistry((source,), rig.sources)
    adapter = d.HiringDomainAdapter(registry)
    manifest = freeze(tmp_path / "corpus", (gold(source),))
    invoked = []
    monkeypatch.setattr(adapter, "bind", lambda *args: invoked.append(True))
    with rig.open(offline=True) as ledger:
        provider = rig.provider(
            "strict_replay", fixtures=FixtureIndex(()), capture_mode="fixture_replay"
        )
        binding = d.JevBinding(
            rig.source,
            rig.bundle,
            rig.decisions,
            provider,
            ledger,
            rig.authority,
            rig.context(),
            rig.limits,
            rig.plan(offline=True, count=2),
        )
        runner = d.HiringMethodRunner(
            registry,
            "jev",
            config_sha256=rig.context().config_sha256,
            bindings={source.pin.item_id: binding},
        )
        result = d.compare_hiring(
            tmp_path / "corpus", manifest, "dev", {"jev": runner.method_config()}, adapter
        )
    method = result.methods["jev"]
    assert invoked == [] and len(method.outcomes) == 37
    assert method.actual_predictions[0].status == "provider_error"
    assert method.actual_predictions[0].domain_payload["controller_status"] == "unavailable"
    assert all(
        row.status == "provider_error" and row.correct is not True for row in method.outcomes
    )
