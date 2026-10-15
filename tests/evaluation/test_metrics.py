"""Hand-computed arithmetic and concrete execution controls, not an empirical corpus."""

from dataclasses import replace

import pytest
import test_domain as h

from hiring_signals import contracts as c
from hiring_signals.evaluation import domain as d
from hiring_signals.evaluation import metrics as m
from hiring_signals.shared.evalkit.calibration import CalibrationSpec
from hiring_signals.shared.evalkit.models import Outcome
from hiring_signals.shared.evalkit.runner import Comparison, MethodConfig, MethodEvaluation
from hiring_signals.shared.providers.captures import FixtureIndex


def row(
    item,
    expected,
    predicted,
    *,
    field="skills.python",
    status="ok",
    method="rules",
    eligibility="eligible",
    group=None,
):
    return Outcome(
        item_id=str(item),
        group_id=group or str(item),
        dataset="arithmetic-control",
        split="dev",
        method=method,
        field=field,
        **{"class": None},
        eligibility=eligibility,
        status=status,
        correct=(
            m.stats.typed_equal(expected, predicted)
            if status == "ok" and eligibility == "eligible"
            else None
        ),
        expected=expected,
        predicted=predicted,
        human_touched_prediction=False,
        evidence_origin="synthetic",
        issues=(),
        ledger_refs=(),
    )


def arithmetic_comparison(count=16, *, paired=True, group=None):
    ids = tuple(str(i) for i in range(count))
    methods = {}
    for name in ("rules", "jev") if paired else ("rules",):
        rows = tuple(
            row(
                i,
                True,
                name == "rules",
                method=name,
                field=field,
                group=group(i) if group else None,
            )
            for i in ids
            for field in c.FIELD_IDS
        )
        methods[name] = MethodEvaluation("executed", ids, (), rows, None)
    return Comparison(ids, count, methods, "dev")


def test_class_counts_failures_denominators_and_answered_accuracy_are_hand_computed():
    """Catches excluding failed positives from recall or calling answered accuracy end-to-end."""
    rows = (
        row(1, True, True),
        row(2, True, None, status="provider_error"),
        row(3, False, True),
        row(4, False, False),
        row(5, None, True, eligibility="unlabelled"),
    )
    result = m.field_summary(rows)
    positive = result["classes"][0]
    assert positive["counts"].model_dump() == {
        "schema_version": 1,
        "true_positive": 1,
        "false_positive": 1,
        "false_negative": 1,
        "true_negative": 1,
    }
    assert positive["rates"].precision.value == positive["rates"].recall.value == 0.5
    assert positive["rates"].f1.value == 0.5
    assert result["end_to_end_accuracy"].value == 0.5
    assert result["accuracy_on_answered"].value == pytest.approx(2 / 3)
    assert result["answered_coverage"].value == 0.75
    assert result["population"] == 5 and result["statuses"]["provider_error"] == 1


def test_zero_support_and_false_versus_absence_are_not_perfect_or_collapsed():
    """Catches zero-class perfect scores and False silently treated as not_stated."""
    report = m.field_summary((row(1, False, "not_stated"),))
    assert report["classes"][0]["rates"].f1.value is None
    assert report["classes"][1]["rates"].recall.value == 0
    assert report["classes"][2]["counts"].false_positive == 1


def test_multiple_seniority_class_does_not_replace_exact_level_set_correctness():
    """Catches a category match misreported as correct exact multiple-level extraction."""
    rows = (
        row(
            1,
            {"category": "multiple", "levels": ["junior", "senior"]},
            {"category": "multiple", "levels": ["mid", "senior"]},
            field="seniority",
        ),
    )
    report = m.field_summary(rows)
    multiple = next(x for x in report["classes"] if x["label"] == "multiple")
    assert multiple["rates"].recall.value == 1
    assert report["end_to_end_accuracy"].value == 0


def test_skill_micro_macro_and_exact_set_keep_failed_and_unlabelled_posts_distinct():
    """Catches incomplete Gold becoming an empty set and model failures disappearing."""
    rows = []
    for item in range(3):
        for index, skill in enumerate(c.SKILL_IDS):
            positive = index == 0
            status = "provider_error" if item == 1 and positive else "ok"
            rows.append(
                row(
                    item,
                    positive,
                    positive if status == "ok" else None,
                    field="skills." + skill,
                    status=status,
                    eligibility="unlabelled" if item == 2 and positive else "eligible",
                )
            )
    report = m.skill_summary(tuple(rows))
    assert report["positive_micro"].recall.value == 0.5
    assert report["positive_micro"].precision.value == 1
    assert report["positive_macro_supported_classes"].f1.value == pytest.approx(2 / 3)
    assert report["exact_positive_set"].value == 0.5
    assert report["exact_set_ineligible_posts"] == 1
    with pytest.raises(d.DomainError, match="duplicate_skill_axis"):
        m.skill_summary(tuple(rows) + (rows[0],))


def actual_rules(tmp_path, text="Requirements: Python", *, salary=None):
    source, authority = h.item(text)
    registry = d.ExecutionRegistry((source,), authority)
    adapter = d.HiringDomainAdapter(registry)
    runner = d.HiringMethodRunner(registry, "rules", config_sha256=h.H)
    gold = h.gold(source) if salary is None else h.gold(source, field="salary", value=salary)
    manifest = h.freeze(tmp_path / "corpus", (gold,))
    result = d.compare_hiring(
        tmp_path / "corpus",
        manifest,
        "dev",
        {"rules": runner.method_config(), "jev": MethodConfig("not-run/1", h.H, "synthetic", None)},
        adapter,
    )
    return result, adapter


def test_actual_rules_summary_has_all37_fields_and_explicit_neverrun_method(tmp_path):
    """Catches fake semantic metrics, per-field count drift or source/Gold strings in aggregates."""
    result, adapter = actual_rules(tmp_path)
    report = m.private_summary(result, adapter)
    assert tuple(report["methods"]["rules"]["metrics"]["fields"]) == c.FIELD_IDS
    assert report["methods"]["rules"]["execution"] == "outcomes_complete"
    assert report["methods"]["jev"] == {
        "execution": "not_run",
        "requested": 1,
        "actual_predictions": 0,
        "metrics": None,
    }
    assert (
        report["methods"]["rules"]["metrics"]["fields"]["skills.python"]["calibration"]["result"]
        is None
    )
    assert "SYNTHETIC_PRIVATE_GOLD" not in repr(report)
    assert "Requirements: Python" not in repr(report)
    assert report["public_release"] == "not_authorized"
    calibration = report["methods"]["rules"]["metrics"]["fields"]["skills.python"]["calibration"]
    assert calibration["eligible"] == calibration["answered"] == 1
    assert calibration["scored"] == 0 and calibration["score_coverage_of_answered"].value == 0


@pytest.mark.parametrize("units", [True, False])
def test_actual_salary_candidate_and_normalization_coverage_have_separate_denominators(
    tmp_path, units
):
    """Catches stated unknown units called absence or accepted annual normalization."""
    text = "Salary: USD100000-120000 per year" if units else "Salary:100000-120000"
    salary = {
        "minimum": "100000",
        "maximum": "120000",
        "currency": "USD" if units else None,
        "period": "year" if units else None,
    }
    result, adapter = actual_rules(tmp_path, text, salary=salary)
    report = m.private_summary(result, adapter)["methods"]["rules"]["metrics"]["salary"]
    assert report["exact_candidate_recall_on_gold_stated"].value == 1
    assert report["accepted_normalization_coverage_on_gold_stated"].value == int(units)
    assert report["exact_range_correctness_on_gold_stated"].value == 1
    assert report["unknown_unit_gold_count"] == int(not units)


def test_candidate_omission_remains_a_miss_on_actual_gold_stated_population(tmp_path):
    """Catches the narrow candidate grammar selecting its denominator from successes."""
    result, adapter = actual_rules(
        tmp_path,
        "Compensation is one hundred thousand yearly.",
        salary={"minimum": "100000", "maximum": "100000", "currency": "USD", "period": "year"},
    )
    report = m.private_summary(result, adapter)["methods"]["rules"]["metrics"]["salary"]
    assert report["stated_gold_support"] == 1
    assert report["exact_candidate_recall_on_gold_stated"].value == 0
    assert report["exact_range_correctness_on_gold_stated"].value == 0


def test_actual_partial_jev_calibration_uses_only_answered_scored_fields(tmp_path):
    """Catches dropped failedA9, imputed confidence, or native probability relabelled generative."""
    rig = h.JEV.AppRig(tmp_path / "jev.sqlite3", "split")
    source, _ = h.item(rig.source._source.text, pin=rig.pin, sources=rig.sources)
    registry = d.ExecutionRegistry((source,), rig.sources)
    provider = rig.provider(
        "strict_replay", fixtures=FixtureIndex(rig.captures()[1:]), capture_mode="fixture_replay"
    )
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
            bindings={rig.pin.item_id: binding},
        )
        adapter = d.HiringDomainAdapter(registry)
        manifest = h.freeze(tmp_path / "corpus", (h.gold(source),))
        comparison = d.compare_hiring(
            tmp_path / "corpus", manifest, "dev", {"jev": runner.method_config()}, adapter
        )
        specs = {
            ("jev", field): CalibrationSpec(
                "native_probability", runner.version, (0.0, 0.5, 1.0), "fixed-bins/1"
            )
            for field in c.FIELD_IDS
        }
        result = m.private_summary(comparison, adapter, calibration_specs=specs)["methods"]["jev"]
        assert result["execution"] == "partial"
        fields = result["metrics"]["fields"]
        assert fields["ai_engineering_role"]["calibration"]["scored"] == 0
        assert (
            fields["ai_engineering_role"]["calibration"]["score_coverage_of_eligible"].value is None
        )
        python = fields["skills.python"]["calibration"]
        assert python["scored"] == python["answered"] == python["eligible"] == 1
        assert python["result"].brier.value == 0
        assert python["result"].ece.value == 0
        assert ledger.totals()["dispatched_attempts"] == 0
        specs["jev", "skills.python"] = CalibrationSpec(
            "self_reported_confidence", runner.version, (0.0, 1.0), "fixed-bins/1"
        )
        with pytest.raises(d.DomainError, match="missing_or_mixed"):
            m.private_summary(comparison, adapter, calibration_specs=specs)


def test_actual_generation_self_confidence_is_separate_and_missing_specs_fail(tmp_path):
    """Catches self-confidence called native probability or missing scores silently imputed."""
    rig = h.GEN.Rig(tmp_path / "generation.sqlite3")
    source, _ = h.item(
        "Requirements: Python\nSalary:100000-120000", pin=rig.pin, sources=rig.sources
    )
    registry = d.ExecutionRegistry((source,), rig.sources)
    adapter = d.HiringDomainAdapter(registry)
    manifest = h.freeze(tmp_path / "corpus", (h.gold(source),))
    transport = h.GEN.helper.Spy(rig, [h.GEN.helper.response(rig.body())])
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
        comparison = d.compare_hiring(
            tmp_path / "corpus", manifest, "dev", {"generative": runner.method_config()}, adapter
        )
        with pytest.raises(d.DomainError, match="missing_or_mixed"):
            m.private_summary(comparison, adapter)
        spec = CalibrationSpec(
            "self_reported_confidence", runner.version, (0.0, 0.5, 1.0), "fixed-bins/1"
        )
        result = m.private_summary(
            comparison, adapter, calibration_specs={("generative", "skills.python"): spec}
        )
        calibration = result["methods"]["generative"]["metrics"]["fields"]["skills.python"][
            "calibration"
        ]
        assert calibration["result"].brier.value == pytest.approx(0.01)
        assert calibration["result"].ece.value == pytest.approx(0.1)
        assert calibration["result"].spec.score_kind == "self_reported_confidence"
        assert len(transport.calls) == 1


@pytest.mark.parametrize("fault", ["missing", "duplicate", "correctness", "predicted", "human"])
def test_changed_canonical_comparison_cannot_claim_actual_machine_statistics(tmp_path, fault):
    """Catches missing IDs, duplicated axes or edited raw-machine outcomes before reporting."""
    comparison, adapter = actual_rules(tmp_path)
    method = comparison.methods["rules"]
    rows = list(method.outcomes)
    if fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows.append(rows[0])
    else:
        index = next(index for index, row in enumerate(rows) if row.field == "skills.python")
        row = rows[index]
        changes = (
            {"correct": not row.correct}
            if fault == "correctness"
            else (
                {"predicted": False, "correct": False}
                if fault == "predicted"
                else {"human_touched_prediction": True}
            )
        )
        rows[index] = row.model_copy(update=changes)
    changed = replace(comparison, methods={"rules": replace(method, outcomes=tuple(rows))})
    with pytest.raises(d.DomainError):
        m.private_summary(changed, adapter)


def test_actual2000_common_group_draws_and_paired_difference_are_reproducible():
    """Catches unpaired streams and failures excluded from target support."""
    comparison = arithmetic_comparison()
    months = {
        item: "2026-06" if int(item) < 8 else "2026-07" for item in comparison.frozen_item_ids
    }
    result = m.paired_field_intervals(
        comparison, field="skills.python", label=True, metric="recall", month_by_item=months
    )
    again = m.paired_field_intervals(
        comparison, field="skills.python", label=True, metric="recall", month_by_item=months
    )
    assert result.spec.draws == 2000 and result.stratification == "month_whole_groups"
    assert result.result.draws_sha256 == again.result.draws_sha256
    assert result.result.methods["rules"].point.value == 1
    assert result.result.methods["jev"].point.value == 0
    difference = result.result.differences["rules", "jev"]
    assert difference.point.value == difference.interval.low == difference.interval.high == 1
    assert difference.valid_draws == 2000
    assert result.result.methods["rules"].interval.draw_ids_sha256 == result.result.draws_sha256


def test_cross_month_duplicate_families_stay_whole_and_low_support_intervals_are_na():
    """Catches splitting a repost family for month strata or claiming supported rare-class CIs."""
    comparison = arithmetic_comparison(4, group=lambda item: str(int(item) // 2))
    months = {
        item: "2026-06" if int(item) % 2 == 0 else "2026-07" for item in comparison.frozen_item_ids
    }
    result = m.paired_field_intervals(
        comparison, field="skills.python", label=True, metric="f1", month_by_item=months
    )
    assert result.stratification == "unstratified_cross_month_families"
    assert result.spec.stratum_map is None and result.result.group_count == 2
    assert result.result.methods["rules"].interval is None
    assert result.result.methods["rules"].null_reason == "insufficient_support"


def test_paired_reference_changes_reject_before_resampling(monkeypatch):
    """Catches independently sampled or changed Gold populations compared as paired evidence."""
    comparison = arithmetic_comparison(2)
    jev = comparison.methods["jev"]
    changed = replace(
        comparison,
        methods=comparison.methods
        | {
            "jev": replace(
                jev,
                outcomes=(
                    jev.outcomes[0].model_copy(update={"expected": False, "correct": True}),
                    *jev.outcomes[1:],
                ),
            )
        },
    )
    monkeypatch.setattr(m, "paired_group_resample", lambda *args: pytest.fail("resampler reached"))
    with pytest.raises(d.DomainError, match="paired_reference_population_changed"):
        m.paired_field_intervals(
            changed,
            field="skills.python",
            label=True,
            metric="recall",
            month_by_item={"0": "2026-06", "1": "2026-06"},
        )
