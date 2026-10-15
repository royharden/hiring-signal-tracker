"""Two/three-row dev fitting controls, not independent Gold or benchmark results."""

import hashlib
import json
from pathlib import Path

import pytest
from test_labels import reference

from hiring_signals.contracts import FIELD_IDS
from hiring_signals.evaluation.majority import MajorityFitError, fit_dev_majority
from hiring_signals.shared.evalkit.identity import ordered_ids_digest
from hiring_signals.shared.evalkit.models import Manifest

H = "a" * 64


def freeze(root, rows):
    root.mkdir(parents=True, exist_ok=True)
    rows = tuple(
        row.model_copy(update={"item_id": f"case:{index}", "group_id": f"g{index}"})
        for index, row in enumerate(rows)
    )
    data = b"".join(row.model_dump_json().encode() + b"\n" for row in rows)
    path = root / "dev.jsonl"
    path.write_bytes(data)
    ids = tuple(row.item_id for row in rows)
    pin = dict(status="available", ref="synthetic-control/1", sha256=H)
    manifest = Manifest.model_validate_json(
        json.dumps(
            {
                "manifest_id": "original-synthetic-dev-control",
                "parent_manifest_sha256": None,
                "split_seed": 20261014,
                "partition_provenance": "seeded",
                "frozen_at": "2026-10-14T00:00:00Z",
                "scorer_version": "synthetic-control/1",
                "comparator_config": pin,
                "domain_adapter_ref": pin,
                "experiment_refs": {},
                "splits": [
                    {
                        "split": "dev",
                        "items_file": "dev.jsonl",
                        "item_count": len(rows),
                        "ordered_item_ids": ids,
                        "items_sha256": hashlib.sha256(data).hexdigest(),
                        "ordered_ids_sha256": ordered_ids_digest(ids),
                        "group_ids": [row.group_id for row in rows],
                    }
                ],
                "group_split_map": {row.group_id: "dev" for row in rows},
                "group_members": {row.group_id: [row.item_id] for row in rows},
                "source_artifacts": [
                    {
                        "namespace": "original-synthetic-control",
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
    return manifest, path


def choices(fit):
    return {row.field_id: row for row in fit.choices}


def test_false_absent_and_unlabelled_populations_do_not_merge_or_invent_defaults(tmp_path):
    """Catches unlabelled training negatives or unsupported fields gaining defaults."""
    manifest, path = freeze(
        tmp_path,
        (
            reference("skills.python", False),
            reference("skills.python", False),
            reference("skills.python", presence="absent"),
        ),
    )
    fit = fit_dev_majority(tmp_path, manifest, min_support=2)
    rows = choices(fit)
    assert tuple(rows) == FIELD_IDS and fit.dev_N == 3
    assert rows["skills.python"].value() is False
    assert (rows["skills.python"].eligible_N, rows["skills.python"].chosen_N) == (3, 2)
    assert rows["employment"].status == "unsupported"
    assert rows["employment"].value() is rows["employment"].chosen_N is None
    assert rows["employment"].eligible_N == 0
    assert fit.dev_items_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert fit.label_sources == ("synthetic",)


def test_canonical_tie_policy_and_support_are_explicit_and_frozen(tmp_path):
    """Catches unstable tied choices or changed support policy reusing a model hash."""
    manifest, _ = freeze(
        tmp_path, (reference("skills.python", True), reference("skills.python", False))
    )
    fit = fit_dev_majority(tmp_path, manifest, min_support=2)
    assert choices(fit)["skills.python"].value() is False
    assert fit.tie_policy == "canonical-json-lexicographic-v1"
    assert fit == fit_dev_majority(tmp_path, manifest, min_support=2)
    stricter = fit_dev_majority(tmp_path, manifest, min_support=3)
    assert stricter.model_sha256 != fit.model_sha256
    row = choices(stricter)["skills.python"]
    assert row.eligible_N == 2 and row.value() is row.chosen_N is None


def test_fitted_composite_values_are_detached_and_keep_unknown_units(tmp_path):
    """Catches mutating a returned label changing the frozen baseline or guessing money units."""
    value = {"minimum": "100.00", "maximum": "120.0", "currency": None, "period": None}
    manifest, _ = freeze(tmp_path, (reference("salary", value),))
    row = choices(fit_dev_majority(tmp_path, manifest, min_support=1))["salary"]
    selected = row.value()
    assert selected == {"minimum": "100", "maximum": "120", "currency": None, "period": None}
    selected["currency"] = "USD"
    assert row.value()["currency"] is None


@pytest.mark.parametrize("support", [True, False, 0, -1, 1.0, "2"])
def test_invalid_support_rejects_before_any_corpus_access(tmp_path, monkeypatch, support):
    """Catches boolean/coerced/zero minimum-support policies touching data before admission."""
    manifest, _ = freeze(tmp_path, ())

    def denied(*args, **kwargs):
        raise AssertionError("corpus must not open")

    monkeypatch.setattr("hiring_signals.evaluation.majority.load_corpus", denied)
    with pytest.raises(MajorityFitError, match="^majority_invalid_or_unavailable_dev$"):
        fit_dev_majority(tmp_path, manifest, min_support=support)


@pytest.mark.parametrize("mutation", ["bytes", "order", "group", "missing_label"])
def test_actual_frozen_loader_refuses_changed_bytes_order_group_or_labels(tmp_path, mutation):
    """Catches changed or incomplete dev populations bypassing pinned source checks."""
    rows = (reference("skills.python", True), reference("skills.python", False))
    if mutation == "missing_label":
        del rows[0].label_payload.labels["salary"]
    manifest, path = freeze(tmp_path, rows)
    if mutation == "bytes":
        path.write_bytes(path.read_bytes() + b" ")
    elif mutation == "order":
        entry = manifest.splits[0]
        ids = tuple(reversed(entry.ordered_item_ids))
        manifest = manifest.model_copy(
            update={
                "splits": (
                    entry.model_copy(
                        update={
                            "ordered_item_ids": ids,
                            "ordered_ids_sha256": ordered_ids_digest(ids),
                        }
                    ),
                )
            }
        )
    elif mutation == "group":
        manifest = manifest.model_copy(update={"group_split_map": {"g0": "heldout", "g1": "dev"}})
    with pytest.raises(MajorityFitError, match="^majority_invalid_or_unavailable_dev$"):
        fit_dev_majority(tmp_path, manifest, min_support=1)


def test_heldout_metadata_never_causes_a_heldout_body_read(tmp_path, monkeypatch):
    """Catches a dev fitter consulting another split's body, even without using its labels."""
    manifest, _ = freeze(tmp_path, (reference("skills.python", True),))
    data = manifest.model_dump(mode="json")
    data["splits"].append(
        {
            "split": "heldout",
            "items_file": "do-not-open-heldout.jsonl",
            "item_count": 1,
            "ordered_item_ids": ["held:0"],
            "items_sha256": H,
            "ordered_ids_sha256": ordered_ids_digest(("held:0",)),
            "group_ids": ["held-group"],
        }
    )
    data["group_split_map"]["held-group"] = "heldout"
    data["group_members"]["held-group"] = ["held:0"]
    manifest = Manifest.model_validate_json(json.dumps(data))
    original = Path.read_bytes

    def guarded(path):
        assert path.name != "do-not-open-heldout.jsonl", "heldout body must not open"
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", guarded)
    assert (
        choices(fit_dev_majority(tmp_path, manifest, min_support=1))["skills.python"].value()
        is True
    )


def test_human_authority_is_required_once_per_actual_dev_record(tmp_path):
    """Catches provenance strings granting trust or authority invoked twice per row."""
    manifest, _ = freeze(
        tmp_path,
        (
            reference(
                "skills.python", False, label_source="human_corrected", label_provenance_ref=H
            ),
        ),
    )
    with pytest.raises(MajorityFitError):
        fit_dev_majority(tmp_path, manifest, min_support=1)
    observed = []
    fit = fit_dev_majority(
        tmp_path,
        manifest,
        min_support=1,
        human_authority=lambda record: observed.append(record.item_id) is None,
    )
    assert observed == ["case:0"] and fit.label_sources == ("human_corrected",)
    # The callback above is an original synthetic spy, not actual human validation.


def test_mixed_label_versions_do_not_fit_an_unstated_common_rubric(tmp_path):
    """Catches combining incompatible label versions under one majority baseline freeze."""
    manifest, _ = freeze(
        tmp_path, (reference(), reference().model_copy(update={"label_version": "other"}))
    )
    with pytest.raises(MajorityFitError, match="^majority_label_version_mismatch$"):
        fit_dev_majority(tmp_path, manifest, min_support=1)


def test_protected_agent_or_credential_directory_is_not_a_corpus_root(tmp_path):
    """Catches a protected metadata/secret directory being opened as training data."""
    root = tmp_path / ".creds"
    manifest, _ = freeze(root, (reference(),))
    with pytest.raises(MajorityFitError, match="^majority_invalid_or_unavailable_dev$"):
        fit_dev_majority(root, manifest, min_support=1)
