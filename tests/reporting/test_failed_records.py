"""Original numeric trend diagnostics; not a corpus, model or Gold benchmark."""

import hashlib
import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest

from hiring_signals import contracts as c
from hiring_signals.extract.rules import classify
from hiring_signals.extract.semantic import failure
from hiring_signals.reporting import population as pop
from hiring_signals.reporting import render
from hiring_signals.shared.aggregate_privacy import models as p


def records(case, month="2026-10"):
    text = "Duties: sales calls\nSalary: USD100 per fortnight"
    source = c.TransientInput(input_sha256=hashlib.sha256(text.encode()).hexdigest(), text=text)
    good = classify(source)
    result = []
    for index in range(20):
        classification = good
        if case == "all_error":
            classification = failure()
        elif case == "blocked":
            classification = failure(blocked=True)
        elif case == "one_error" and index == 0:
            classification = good.model_copy(
                update={"ai_engineering_role": failure().ai_engineering_role}
            )
        elif case in {"uncertain", "conflicting"}:
            classification = good.model_copy(
                update={
                    "ai_engineering_role": c.BooleanJudgment(
                        value=None,
                        evidence_state=case,
                        process_status="abstained",
                        certainty=None,
                        candidates=(),
                        error_code=None,
                    )
                }
            )
        result.append(
            c.PrivateDerivedRecord(
                schema_version=1,
                item_id=f"{index:064x}",
                month=month,
                input_sha256=source.input_sha256,
                taxonomy_sha256="b" * 64,
                config_sha256="c" * 64,
                implementation_sha256="d" * 64,
                method="rules",
                model_sha256=None,
                provenance=c.LabelProvenance(
                    source="unprovided", actor_ref=None, attestation_sha256=None
                ),
                classification=classification,
            )
        )
    return tuple(result)


def aggregate(case):
    values = records(case)
    return pop.aggregate_month(
        pop.MonthlyCohort(
            month="2026-10",
            method="rules",
            version_sha256=pop.record_version(values[0]),
            source_scope="original_synthetic_population",
            source_coverage="complete",
            method_status="run",
            missing_status="error",
            policy=p.POLICY_V2,
            expected_ids=tuple(v.item_id for v in values),
            records=values,
        )
    )


def window(month):
    return render.ReportWindow(
        schema_version=1,
        month_ids=("2026-07", "2026-08", "2026-09", "2026-10"),
        method="rules",
        source_scope="original_synthetic_population",
        quality_status="not_measured",
        months=(month,),
    )


@pytest.mark.parametrize(
    "case,count,label",
    [("all_error", 20, "error"), ("one_error", 1, "error"), ("blocked", 20, "blocked")],
)
def test_processing_failures_keep_all_ids_counts_but_break_complete_trends(case, count, label):
    """Catches fully present failed records becoming an observed zero or losing denominators."""
    captured = []
    original = p.release_partition

    def spy(part, **kwargs):
        captured.append(part)
        return original(part, **kwargs)

    with patch.object(pop.p, "release_partition", side_effect=spy):
        public = aggregate(case)
    assert public.method_status == "partial" and public.source_coverage == "complete"
    assert public.eligible_denominator == 20
    assert all(
        part.denominator == 20 and sum(cell.numerator for cell in part.cells) == 20
        for part in captured
    )
    ai = next(part for part in captured if part.metric == "ai_engineering_role")
    assert next(cell.numerator for cell in ai.cells if cell.label == label) == count
    assert all(part.coverage == "partial" and not part.trend_eligible for part in public.partitions)
    point = render.series(window(public), "ai_engineering_role", "positive")[-1]
    assert point.state == "partial" and point.share is point.change_pp is None
    for asset in render._assets(window(public)).values():
        assert "partial" in asset
    svg = ET.fromstring(render.render_svg(window(public)))
    assert not [node for node in svg.iter() if node.attrib.get("data-role") == "observed-point"]


@pytest.mark.parametrize("case", ["uncertain", "conflicting"])
def test_abstention_only_is_not_a_processing_failure(case):
    """Catches uncertainty/conflicts collapsed into a provider error or omitted outcome."""
    public = aggregate(case)
    assert public.method_status == "outcomes_complete"
    part = public.partitions[0]
    assert next(cell.numerator for cell in part.cells if cell.label == case) == 20
    assert next(cell.numerator for cell in part.cells if cell.label == "error") == 0


def test_actual_valid_zero_and_unknown_salary_units_preserve_v2_complete_observation():
    """Catches suppressing a supported valid zero or treating unknown units as processing error."""
    public = aggregate("valid_zero")
    assert public.method_status == "outcomes_complete" and public.source_coverage == "complete"
    point = render.series(window(public), "ai_engineering_role", "positive")[-1]
    assert point.state == "observed" and point.share == 0.0
    salary = next(part for part in public.partitions if part.metric == "salary")
    assert (
        next(cell.numerator for cell in salary.cells if cell.label == "stated_unknown_units") == 20
    )
    svg = ET.fromstring(render.render_svg(window(public)))
    assert (
        len([node for node in svg.iter() if node.attrib.get("data-role") == "observed-point"]) == 2
    )
