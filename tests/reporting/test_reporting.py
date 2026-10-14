"""Small original numeric/accounting controls; no Gold, population accuracy or visual QA."""

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from hiring_signals import contracts as c
from hiring_signals.extract.rules import classify
from hiring_signals.reporting import population as pop
from hiring_signals.reporting import render as r
from hiring_signals.shared.aggregate_privacy import models as p

MONTHS = ("2026-07", "2026-08", "2026-09", "2026-10")


def prediction(number, text="Requirements: Python", month="2026-10"):
    envelope = c.TransientInput(input_sha256=hashlib.sha256(text.encode()).hexdigest(), text=text)
    return c.PrivateDerivedRecord(
        schema_version=1,
        item_id=hashlib.sha256(f"original-numeric-control-{number}".encode()).hexdigest(),
        month=month,
        input_sha256=envelope.input_sha256,
        taxonomy_sha256="a" * 64,
        config_sha256="b" * 64,
        implementation_sha256="c" * 64,
        method="rules",
        model_sha256=None,
        provenance=c.LabelProvenance(source="unprovided", actor_ref=None, attestation_sha256=None),
        classification=classify(envelope),
    )


def cohort(records, expected=None, **changes):
    records = tuple(records)
    first = records[0] if records else prediction(0)
    data = dict(
        month="2026-10",
        method="rules",
        version_sha256=pop.record_version(first),
        source_scope="original_synthetic_population",
        source_coverage="complete",
        method_status="run",
        missing_status="error",
        records=records,
        expected_ids=tuple(record.item_id for record in records)
        if expected is None
        else tuple(expected),
    )
    data.update(changes)
    return pop.MonthlyCohort(**data)


def public_month(
    month, positive=10, coverage="complete", version="d" * 64, scope="original_synthetic_population"
):
    # Numeric renderer input only, deliberately not generated posting labels or Gold.
    parts = []
    for metric in c.FIELD_IDS:
        labels = p.class_inventory(metric)
        counts = [100 - 10 * (len(labels) - 1), *([10] * (len(labels) - 1))]
        if metric in {"ai_engineering_role", "portfolio_requested"}:
            counts[1] += counts[0] - positive
            counts[0] = positive
        part = p.Partition(
            month=month,
            metric=metric,
            method="rules",
            version_sha256=version,
            evidence_category="prediction",
            coverage=coverage,
            denominator=100,
            cells=tuple(
                p.Cell(label=label, numerator=count, uncertainty=None)
                for label, count in zip(labels, counts, strict=True)
            ),
        )
        parts.append(p.release_partition(part))
    return pop.PublicMonth(
        month=month,
        method="rules",
        version_sha256=version,
        source_scope=scope,
        source_coverage=coverage,
        method_status="outcomes_complete",
        quality_status="not_measured",
        eligible_denominator=100,
        partitions=tuple(parts),
    )


def window(months=None, scope="original_synthetic_population"):
    return r.ReportWindow(
        schema_version=1,
        month_ids=MONTHS,
        method="rules",
        source_scope=scope,
        quality_status="not_measured",
        months=tuple(
            months
            if months is not None
            else [
                public_month(month, positive=(index + 1) * 10, scope=scope)
                for index, month in enumerate(MONTHS)
            ]
        ),
    )


def test_all_expected_ids_and_all37_field_denominators_retain_missing_outcomes():
    """Catches missing predictions disappearing from every field's denominator."""
    yes = prediction(
        1, "Requirements: Python\nSalary:USD100 per fortnight\nRole:Junior or Senior engineer"
    )
    no = prediction(2, "Python not required.\nSalary:none")
    missing = prediction(3).item_id
    private = cohort([yes, no], expected=[yes.item_id, no.item_id, missing])
    captured = []
    original = p.release_partition

    def spy(part):
        captured.append(part)
        return original(part)

    with patch.object(pop.p, "release_partition", side_effect=spy):
        result = pop.aggregate_month(private)
    assert len(captured) == len(result.partitions) == 37
    assert all(
        part.denominator == 3 and sum(cell.numerator for cell in part.cells) == 3
        for part in captured
    )

    def counts(metric):
        return {
            cell.label: cell.numerator
            for cell in next(v for v in captured if v.metric == metric).cells
        }

    assert (
        counts("skills.python")["positive"]
        == counts("skills.python")["negative"]
        == counts("skills.python")["error"]
        == 1
    )
    assert counts("salary")["stated_unknown_units"] == counts("salary")["negative"] == 1
    assert counts("seniority")["multiple"] == counts("seniority")["not_stated"] == 1
    assert result.method_status == "partial" and result.eligible_denominator is None
    assert all(not part.trend_eligible and part.coverage == "partial" for part in result.partitions)
    text = result.model_dump_json()
    assert all(item not in text for item in private.expected_ids)


@pytest.mark.parametrize(
    "mutation", ["duplicate_expected", "duplicate_record", "foreign", "month", "method", "version"]
)
def test_closed_cohort_rejects_duplicate_foreign_wrong_month_method_or_stale_version(mutation):
    """Catches apparently valid records silently joining the wrong frozen monthly cohort."""
    first = prediction(1)
    data = cohort([first]).model_dump(mode="json")
    if mutation == "duplicate_expected":
        data["expected_ids"].append(first.item_id)
    elif mutation == "duplicate_record":
        data["records"].append(data["records"][0])
    elif mutation == "foreign":
        data["expected_ids"] = ["f" * 64]
    elif mutation == "month":
        data["records"][0]["month"] = "2026-09"
    elif mutation == "method":
        data["method"] = "dev_majority"
    else:
        data["records"][0]["config_sha256"] = "f" * 64
    with pytest.raises(ValidationError):
        pop.MonthlyCohort.model_validate_json(json.dumps(data))


def test_not_run_is_not_a_fake_error_prediction_or_zero_rate():
    """Catches unrun methods manufactured as predictions or a successful zero share."""
    source = prediction(1)
    result = pop.aggregate_month(cohort([], expected=[source.item_id], method_status="not_run"))
    assert result.method_status == "not_run" and result.partitions == ()
    point = r.series(window([result]), "ai_engineering_role", "positive")[-1]
    assert point.share is None and point.state == "not_run"


def test_four_month_percentage_points_use_same_version_and_no_gap_interpolation():
    """Catches wrong percentage-point arithmetic or comparisons over gaps/versions."""
    points = r.series(window(), "ai_engineering_role", "positive")
    assert [point.share for point in points] == [0.1, 0.2, 0.3, 0.4]
    assert points[0].change_pp is None
    assert all(point.change_pp == pytest.approx(10) for point in points[1:])
    changed = window(
        [
            public_month(MONTHS[0]),
            public_month(MONTHS[1], 20, version="e" * 64),
            public_month(MONTHS[2], 30, coverage="partial"),
            public_month(MONTHS[3], 40),
        ]
    )
    points = r.series(changed, "ai_engineering_role", "positive")
    assert points[1].change_pp is None and points[2].share is None and points[3].change_pp is None
    svg = ET.fromstring(r.render_svg(changed))
    assert (
        len([node for node in svg.iter() if node.attrib.get("data-role") == "observed-segment"])
        == 0
    )


def test_suppression_propagates_to_real_json_markdown_svg_and_html():
    """Catches a real renderer leaking the rare count after the core withheld it."""
    rare = public_month("2026-10", positive=1)
    report = window([rare])
    encoded = r._assets(report)
    loaded = r.ReportWindow.model_validate_json(encoded["aggregates.json"])
    hidden = next(
        part for part in loaded.months[0].partitions if part.metric == "ai_engineering_role"
    )
    assert hidden.suppressed and all(
        cell.numerator is None and cell.share is None for cell in hidden.cells
    )
    assert "suppressed" in encoded["report.html"] and "suppressed" in encoded["aggregates.md"]
    assert "1/100" not in encoded["report.html"] and "1/100" not in encoded["aggregates.md"]
    svg = ET.fromstring(encoded["trends.svg"])
    assert not [node for node in svg.iter() if node.attrib.get("data-role") == "observed-point"]


def test_svg_geometry_and_sample_scope_are_explicit():
    """Catches fake zero plots or Gold-sample predictions presented as population measurements."""
    report = window(scope="gold_sample")
    svg = ET.fromstring(r.render_svg(report))
    points = [node for node in svg.iter() if node.attrib.get("data-role") == "observed-point"]
    assert len(points) == 8
    assert [float(node.attrib["cy"]) for node in points[:4]] == [198, 183, 168, 153]
    assert "sample estimates, not population trends" in r.render_html(report)
    assert "not measured" in r.render_markdown(report)


@pytest.mark.parametrize(
    "key", ["raw_text", "company", "person", "source_id", "group_digest", "url", "accuracy"]
)
def test_public_report_rejects_identity_text_and_unprovided_performance_fields(key):
    """Positive controls catch private fields or fake quality metrics in the public wire."""
    data = window().model_dump(mode="json")
    data[key] = "ORIGINAL_PRIVATE_CANARY https://example.invalid/name"
    with pytest.raises(ValidationError):
        r.ReportWindow.model_validate_json(json.dumps(data))


def test_manifest_verifies_all_bytes_and_cannot_legitimize_a_tampered_renderer(tmp_path):
    """Catches cross-format drift or self-updated hashes mistaken for safe-content proof."""
    target = tmp_path / "report"
    report = window()
    manifest = r.export_report(report, target)
    assert r.verify_report(target) == report
    assert (
        manifest.window_sha256
        == hashlib.sha256((target / "aggregates.json").read_bytes()).hexdigest()
    )
    (target / "report.html").write_text("ORIGINAL_PRIVATE_CANARY", encoding="utf-8")
    data = manifest.model_dump(mode="json")
    data["files"][-1]["sha256"] = hashlib.sha256((target / "report.html").read_bytes()).hexdigest()
    (target / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="closed released projection"):
        r.verify_report(target)


def test_existing_report_preserved_and_interrupted_output_remains_unsealed(tmp_path):
    """Catches overwriting unrelated output or a partial multi-format write claimed complete."""
    target = tmp_path / "existing"
    target.mkdir()
    (target / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        r.export_report(window(), target)
    assert (target / "keep.txt").read_text() == "keep"
    original = Path.open

    def fail_svg(path, *args, **kwargs):
        if path.name == "trends.svg" and args and args[0] == "xb":
            raise OSError("original synthetic IO failure")
        return original(path, *args, **kwargs)

    partial = tmp_path / "partial"
    with patch.object(Path, "open", new=fail_svg), pytest.raises(OSError):
        r.export_report(window(), partial)
    assert not (partial / "manifest.json").exists()
    with pytest.raises(ValueError, match="manifest unavailable"):
        r.verify_report(partial)


def test_window_refuses_mixed_scope_duplicate_month_and_nonconsecutive_axes():
    """Catches mixing sampled and population estimates or silently relabelling month order."""
    for changed in (
        {"months": (public_month(MONTHS[0]), public_month(MONTHS[0]))},
        {"months": (public_month(MONTHS[0], scope="gold_sample"),)},
        {"month_ids": ("2026-07", "2026-09", "2026-10", "2026-11")},
    ):
        data = window().model_dump()
        data.update(changed)
        with pytest.raises(ValidationError):
            r.ReportWindow.model_validate(data)


def test_invalid_private_keys_not_echoed_by_public_render_or_aggregate_api(tmp_path):
    """Catches rejected identity-bearing JSON property names leaking into public errors/output."""
    canary = "ORIGINAL_PRIVATE_PERSON https://example.invalid/name"
    data = window().model_dump()
    data[canary] = "original synthetic text"
    with pytest.raises(ValueError) as failure:
        r.export_report(data, tmp_path / "no-write")
    assert str(failure.value) == "invalid_closed_report_input" and canary not in str(failure.value)
    assert not (tmp_path / "no-write").exists()
    data = cohort([prediction(1)]).model_dump()
    data[canary] = "original synthetic text"
    with pytest.raises(ValueError) as failure:
        pop.aggregate_month(data)
    assert str(failure.value) == "invalid_private_monthly_cohort"
