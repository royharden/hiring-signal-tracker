"""Original numeric policy boundaries, not a data corpus or anonymity proof."""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from pydantic import ValidationError

from hiring_signals import contracts as c
from hiring_signals.reporting import population as pop
from hiring_signals.reporting import render as r
from hiring_signals.shared.aggregate_privacy import models as p

MONTHS = ("2026-07", "2026-08", "2026-09", "2026-10")


def partition(counts, metric="ai_engineering_role", month="2026-10"):
    return p.Partition(
        month=month,
        metric=metric,
        method="rules",
        version_sha256="a" * 64,
        evidence_category="prediction",
        coverage="complete",
        denominator=sum(counts),
        cells=tuple(
            p.Cell(label=label, numerator=count, uncertainty=p.Interval(lower=0.0, upper=1.0))
            for label, count in zip(p.class_inventory(metric), counts, strict=True)
        ),
    )


def test_zero_is_released_only_with_explicit_v2_and_supported_whole_partition():
    """Catches default V1 changing or V2 treating true zero as unknown/suppressed."""
    private = partition([40, 40, 20, 0, 0, 0, 0])
    assert p.release_partition(private).suppressed
    released = p.release_partition(private, policy=p.POLICY_V2)
    assert released.policy == p.POLICY_V2 and released.trend_eligible
    assert [cell.numerator for cell in released.cells] == [40, 40, 20, 0, 0, 0, 0]
    assert [cell.share for cell in released.cells] == [0.4, 0.4, 0.2, 0.0, 0.0, 0.0, 0.0]
    for name in ("json", "table", "chart", "html"):
        assert p.format_projection(released, name) == released.model_dump(mode="json")


@pytest.mark.parametrize("rare", [1, 9])
def test_positive_rare_cell_hides_every_sibling_including_zero_and_intervals(rare):
    """Catches a V2 zero exception weakening positive-cell suppression."""
    result = p.release_partition(partition([50, 50 - rare, rare, 0, 0, 0, 0]), policy=p.POLICY_V2)
    assert result.suppressed and not result.trend_eligible and result.denominator == 100
    assert all(cell.numerator is cell.share is cell.uncertainty is None for cell in result.cells)


@pytest.mark.parametrize("total", [0, 1, 9])
def test_v2_small_whole_cohort_always_hides_denominator_and_zero_cells(total):
    """Catches empty/all-zero division or release of a small cohort through zeros."""
    result = p.release_partition(partition([total, 0, 0, 0, 0, 0, 0]), policy=p.POLICY_V2)
    assert result.denominator is None and result.suppressed
    assert all(cell.numerator is cell.share is cell.uncertainty is None for cell in result.cells)


def test_v2_revalidation_cannot_relabel_zeros_as_v1_or_publish_positive_rare():
    """Catches bypassing policy invariants with an already released JSON payload."""
    result = p.release_partition(partition([40, 40, 20, 0, 0, 0, 0]), policy=p.POLICY_V2)
    data = result.model_dump(mode="json")
    data["policy"] = p.POLICY_V1
    with pytest.raises(ValidationError):
        p.ReleasedPartition.model_validate_json(json.dumps(data))
    data = result.model_dump(mode="json")
    data["cells"][0].update(numerator=49, share=0.49)
    data["cells"][1].update(numerator=50, share=0.50)
    data["cells"][2].update(numerator=1, share=0.01)
    with pytest.raises(ValidationError):
        p.ReleasedPartition.model_validate_json(json.dumps(data))
    with pytest.raises(ValueError, match="unsupported"):
        p.release_partition(partition([10] * 7), policy="unreviewed")


def month(month_id, policy=p.POLICY_V2, positive=40):
    parts = []
    for metric in c.FIELD_IDS:
        labels = p.class_inventory(metric)
        counts = [positive, 100 - positive, *([0] * (len(labels) - 2))]
        parts.append(p.release_partition(partition(counts, metric, month_id), policy=policy))
    return pop.PublicMonth(
        month=month_id,
        method="rules",
        version_sha256="a" * 64,
        source_scope="original_synthetic_population",
        source_coverage="complete",
        method_status="outcomes_complete",
        quality_status="not_measured",
        policy=policy,
        eligible_denominator=100,
        partitions=tuple(parts),
    )


def window(months):
    return r.ReportWindow(
        schema_version=1,
        month_ids=MONTHS,
        method="rules",
        source_scope="original_synthetic_population",
        quality_status="not_measured",
        months=tuple(months),
    )


def test_month_policy_must_bind_every_released_partition():
    """Catches the reporting envelope lying about a nested release policy."""
    data = month(MONTHS[0]).model_dump(mode="json")
    data["policy"] = p.POLICY_V1
    with pytest.raises(ValidationError, match="mixed release"):
        pop.PublicMonth.model_validate_json(json.dumps(data))


def test_series_never_compares_different_policies_and_marks_true_zero():
    """Catches pp comparisons across policy changes and observed zero becoming a gap."""
    # Both policies can release strictly supported cells, so a policy change alone is a barrier.
    first = month(MONTHS[0])
    v1parts = []
    for metric in c.FIELD_IDS:
        n = len(p.class_inventory(metric))
        v1parts.append(
            p.release_partition(
                partition([100 - 10 * (n - 1), *([10] * (n - 1))], metric, MONTHS[1])
            )
        )
    second = pop.PublicMonth(
        **{
            **first.model_dump(),
            "month": MONTHS[1],
            "policy": p.POLICY_V1,
            "partitions": tuple(v1parts),
        }
    )
    third, fourth = month(MONTHS[2], positive=0), month(MONTHS[3], positive=20)
    report = window([first, second, third, fourth])
    points = r.series(report, "ai_engineering_role", "positive")
    assert points[1].change_pp is points[2].change_pp is None
    assert points[2].state == "observed" and points[2].share == 0
    assert points[3].change_pp == 20
    assert [point.policy for point in points] == [
        p.POLICY_V2,
        p.POLICY_V1,
        p.POLICY_V2,
        p.POLICY_V2,
    ]


def test_all_real_renderers_export_exact_policy_scope_version_and_zero(tmp_path):
    """Catches V2 policy metadata or true zero lost in a real exported format."""
    report = window([month(MONTHS[3], positive=0)])
    destination = tmp_path / "new-report"
    r.export_report(report, destination)
    assert r.verify_report(destination) == report
    for asset in r.ASSETS:
        content = (destination / asset).read_text(encoding="utf-8")
        assert p.POLICY_V2 in content and "a" * 64 in content
        assert "original_synthetic_population" in content
    assert "0/100" in (destination / "aggregates.md").read_text()
    svg = ET.fromstring((destination / "trends.svg").read_text())
    assert (
        len([node for node in svg.iter() if node.attrib.get("data-role") == "observed-point"]) == 2
    )


def test_generated_released_schema_contains_both_policies():
    """Catches runtime/schema drift when V2 is added without the closed artifact."""
    path = Path(p.__file__).with_name("schemas.json")
    assert json.loads(path.read_text()) == p.schema_documents()


@pytest.mark.parametrize("size", [0, 100])
def test_explicit_monthly_v2_flows_through_actual_aggregation(size):
    """Catches monthly accounting silently using default V1 despite an explicit V2 input."""
    # Missing outcomes remain accounted; an empty cohort still cannot release zero.
    private = pop.MonthlyCohort(
        month="2026-10",
        method="rules",
        version_sha256="a" * 64,
        source_scope="original_synthetic_population",
        source_coverage="complete",
        method_status="run",
        missing_status="error",
        policy=p.POLICY_V2,
        expected_ids=tuple(f"{index:064x}" for index in range(size)),
        records=(),
    )
    public = pop.aggregate_month(private)
    assert public.policy == p.POLICY_V2 and len(public.partitions) == 37
    assert all(
        part.policy == p.POLICY_V2 and part.suppressed == (size == 0) for part in public.partitions
    )
    if size:
        assert public.method_status == "partial"
        for part in public.partitions:
            assert not part.trend_eligible
            assert next(cell for cell in part.cells if cell.label == "error").numerator == 100
            assert all(cell.numerator == 0 for cell in part.cells if cell.label != "error")
