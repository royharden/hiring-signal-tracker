"""Private hiring projections over canonical arithmetic; no data, calls or release authority.

Comparison/registry objects are trusted in-process inputs, not signed evidence.
This module never opens a corpus, selects thresholds or publishes its private rows.
"""

from collections import Counter
from dataclasses import dataclass, replace

from hiring_signals import contracts as c
from hiring_signals.extract import rules
from hiring_signals.shared.evalkit import statistics as stats
from hiring_signals.shared.evalkit.calibration import (
    BinaryCalibrationPoint,
    CalibrationSpec,
    binary_calibration,
)
from hiring_signals.shared.evalkit.identity import canonical_bytes
from hiring_signals.shared.evalkit.models import Outcome, ResamplingSpec
from hiring_signals.shared.evalkit.resampling import paired_group_resample
from hiring_signals.shared.evalkit.runner import Comparison

from .domain import DomainError, HiringDomainAdapter, _field_status, project_record

STATUSES = (
    "ok",
    "abstained",
    "invalid",
    "provider_error",
    "blocked",
    "stale",
    "unavailable",
    "not_run",
)
CATEGORIES = {
    "seniority": ("junior", "mid", "senior", "staff_or_lead", "multiple", "not_stated"),
    "work_mode": ("remote", "hybrid", "onsite", "not_stated"),
    "employment": ("full_time", "part_time", "contract", "internship", "not_stated"),
    "salary": ("stated", "none", "not_stated"),
}


def _class(field, value):
    if field == "salary" and type(value) is dict:
        return "stated"
    if field == "seniority" and type(value) is dict:
        return value["category"]
    return value


def _class_rows(rows):
    return tuple(
        row.model_copy(
            update={
                "expected": _class(row.field, row.expected),
                "predicted": _class(row.field, row.predicted),
            }
        )
        for row in rows
    )


def field_summary(rows: tuple[Outcome, ...]) -> dict:
    """Pure private arithmetic. Authored controls passed here are not measured evidence."""
    if not rows or len({row.field for row in rows}) != 1:
        raise DomainError("one_nonempty_field_population_required")
    if any(row.human_touched_prediction for row in rows):
        raise DomainError("human_effective_not_machine")
    field = rows[0].field
    declared = CATEGORIES.get(field, (True, False, "not_stated"))
    projected = _class_rows(rows)
    classes = []
    for label in declared:
        counts = stats.confusion_counts(projected, label)
        classes.append(
            {"label": label, "counts": counts, "rates": stats.classification_rates(counts)}
        )
    eligible = tuple(row for row in rows if row.eligibility == "eligible")
    return {
        "field": field,
        "population": len(rows),
        "eligibility": dict(Counter(row.eligibility for row in rows)),
        "statuses": {name: sum(row.status == name for row in rows) for name in STATUSES},
        "origins": dict(Counter(row.evidence_origin for row in rows)),
        "answered_coverage": stats.rate(sum(row.status == "ok" for row in eligible), len(eligible)),
        "end_to_end_accuracy": stats.accuracy(rows, machine_automation_only=True),
        "accuracy_on_answered": stats.accuracy(
            rows, answered_only=True, machine_automation_only=True
        ),
        "classes": tuple(classes),
    }


def skill_summary(outcomes: tuple[Outcome, ...]) -> dict:
    """Positive-set scores; complete30-field Gold required for posting-level exact set."""
    fields = tuple("skills." + skill for skill in c.SKILL_IDS)
    rows = tuple(row for row in outcomes if row.field in fields)
    confusions = {
        field: stats.confusion_counts(tuple(row for row in rows if row.field == field), True)
        for field in fields
    }
    by_id = {}
    for row in rows:
        per_item = by_id.setdefault(row.item_id, {})
        if row.field in per_item:
            raise DomainError("duplicate_skill_axis")
        per_item[row.field] = row
    sets, incomplete = [], 0
    for per_item in by_id.values():
        if set(per_item) != set(fields):
            raise DomainError("incomplete_skill_axes")
        ordered = tuple(per_item[field] for field in fields)
        if any(row.eligibility != "eligible" for row in ordered):
            incomplete += 1
            continue
        answered = all(row.status == "ok" for row in ordered)
        sets.append(
            ordered[0].model_copy(
                update={
                    "field": "skill_set",
                    "expected": [row.field for row in ordered if row.expected is True],
                    "predicted": [row.field for row in ordered if row.predicted is True]
                    if answered
                    else None,
                    "status": "ok"
                    if answered
                    else next(row.status for row in ordered if row.status != "ok"),
                    "correct": None,
                }
            )
        )
    return {
        "positive_micro": stats.classification_summary(confusions, "micro"),
        "positive_macro_supported_classes": stats.classification_summary(confusions, "macro"),
        "positive_confusions": confusions,
        "exact_positive_set": stats.exact_set_accuracy(tuple(sets)),
        "exact_set_ineligible_posts": incomplete,
        "exact_set_population_policy": "all30eligible; failure_is_miss; unlabelled_not_absent/1",
    }


def _population(comparison: Comparison):
    if type(comparison) is not Comparison or (
        len(set(comparison.frozen_item_ids)) != len(comparison.frozen_item_ids)
        or comparison.corpus_count != len(comparison.frozen_item_ids)
        or not comparison.methods
    ):
        raise DomainError("invalid_fixed_comparison")
    expected = {(item, field) for item in comparison.frozen_item_ids for field in c.FIELD_IDS}
    reference = None
    for name, result in comparison.methods.items():
        if result.requested_item_ids != comparison.frozen_item_ids:
            raise DomainError("requested_population_changed")
        if result.status == "not_run":
            if result.outcomes or result.actual_predictions or result.calls_observed != 0:
                raise DomainError("never_run_has_fake_evidence")
            continue
        if result.status != "executed":
            raise DomainError("invalid_method_execution_state")
        actual, population = set(), {}
        for raw in result.outcomes:
            try:
                row = Outcome.model_validate_json(raw.model_dump_json(warnings="error"))
            except Exception:
                raise DomainError("invalid_private_outcome_wire") from None
            axis = (row.item_id, row.field)
            if (
                axis in actual
                or row.class_name is not None
                or row.method != name
                or row.status == "not_run"
                or row.human_touched_prediction
                or row.split != comparison.split
            ):
                raise DomainError("invalid_or_duplicate_machine_axis")
            actual.add(axis)
            population[axis] = (
                row.group_id,
                row.dataset,
                row.split,
                row.eligibility,
                canonical_bytes(row.expected),
            )
            if row.eligibility == "eligible" and row.status == "ok":
                if row.correct is not stats.typed_equal(row.expected, row.predicted):
                    raise DomainError("correctness_changed")
        if actual != expected:
            raise DomainError("missing_or_extra_fixed_axes")
        if reference is not None and reference != population:
            raise DomainError("paired_reference_population_changed")
        reference = population


def _machine_rows(result, adapter, method):
    projected = {}
    predictions = {}
    for prediction in result.actual_predictions:
        if prediction.method != method or prediction.item_id not in result.requested_item_ids:
            raise DomainError("actual_prediction_population_changed")
        if prediction.item_id in predictions:
            raise DomainError("duplicate_actual_prediction")
        # A canonical invalid demotion can preserve raw output, but gets no field authority.
        if prediction.status == "invalid":
            issued = adapter.registry._issued.get((prediction.method, prediction.item_id))
            if issued is None:
                raise DomainError("unissued_invalid_output")
            from hiring_signals.shared.evalkit.axis_status import raw_machine_digest

            if raw_machine_digest(prediction) != raw_machine_digest(issued[0]):
                raise DomainError("changed_failed_raw_output")
            record = issued[1]
        else:
            adapter.validate_prediction(prediction)
            record = adapter.registry._lookup(prediction)[1]
        predictions[prediction.item_id] = prediction
        for row in project_record(record):
            projected[prediction.item_id, row.field_id] = row
    for row in result.outcomes:
        prediction = predictions.get(row.item_id)
        machine = projected.get((row.item_id, row.field))
        if prediction is None:
            if (
                row.status not in {"stale", "unavailable", "provider_error"}
                or row.predicted is not None
            ):
                raise DomainError("outcome_without_actual_execution")
        elif prediction.status == "ok":
            if (
                row.status != _field_status(machine)
                or not stats.typed_equal(row.predicted, machine.value)
                or row.ledger_refs != prediction.ledger_refs
                or row.evidence_origin != prediction.origin
            ):
                raise DomainError("outcome_raw_execution_changed")
        elif row.status != prediction.status or row.predicted is not None:
            raise DomainError("whole_failure_promoted")
    return projected, predictions


def salary_summary(rows, machines, registry, *, extraction=True):
    eligible = tuple(row for row in rows if row.eligibility == "eligible")
    stated = tuple(row for row in eligible if type(row.expected) is dict)
    predicted = sum(row.status == "ok" and type(row.predicted) is dict for row in eligible)
    candidates, normalized, exact = 0, 0, 0
    for row in stated:
        item = registry._items.get(row.item_id)
        if extraction and item is not None and registry._current(item):
            baseline = rules.classify(item.source)
            salary = baseline.salary
            if salary.presence.value is True:
                # The shared semantic candidate grammar selects at most this same narrow range.
                from hiring_signals.annotation.models import SalaryValue

                from .labels import _salary

                candidate = _salary(
                    SalaryValue(
                        minimum=salary.stated_minimum,
                        maximum=salary.stated_maximum,
                        currency=salary.currency,
                        period=salary.period,
                    )
                )
                candidates += stats.typed_equal(candidate, row.expected)
        machine = machines.get((row.item_id, "salary"))
        normalized += bool(
            row.status == "ok" and machine is not None and machine.normalization_status == "ok"
        )
        exact += bool(row.status == "ok" and row.correct is True)
    return {
        "stated_prediction_rate": stats.rate(predicted, len(eligible)),
        "stated_gold_support": len(stated),
        "exact_candidate_recall_on_gold_stated": stats.rate(candidates, len(stated))
        if extraction
        else None,
        "accepted_normalization_coverage_on_gold_stated": stats.rate(normalized, len(stated))
        if extraction
        else None,
        "exact_range_correctness_on_gold_stated": stats.rate(exact, len(stated)),
        "unknown_unit_gold_count": sum(
            row.expected["currency"] is None or row.expected["period"] is None for row in stated
        ),
        "candidate_policy": "same_narrow_rules_single_candidate/1"
        if extraction
        else "not_applicable_learned_reference_baseline/1",
    }


def _calibration(rows, machines, predictions, spec):
    if spec is not None and type(spec) is not CalibrationSpec:
        raise DomainError("actual_canonical_calibration_spec_required")
    eligible = tuple(row for row in rows if row.eligibility == "eligible")
    answered = tuple(row for row in eligible if row.status == "ok")
    points = []
    for row in answered:
        machine = machines.get((row.item_id, row.field))
        prediction = predictions.get(row.item_id)
        if machine is None or machine.certainty_kind is None or machine.certainty_value is None:
            continue
        if spec is None or (spec.score_kind, spec.score_version) != (
            machine.certainty_kind,
            prediction.method_version,
        ):
            raise DomainError("missing_or_mixed_calibration_signal_spec")
        points.append(
            BinaryCalibrationPoint(
                machine.certainty_value, row.correct, spec.score_kind, spec.score_version
            )
        )
    return {
        "eligible": len(eligible),
        "answered": len(answered),
        "scored": len(points),
        "score_coverage_of_eligible": stats.rate(len(points), len(eligible)),
        "score_coverage_of_answered": stats.rate(len(points), len(answered)),
        "result": binary_calibration(tuple(points), spec) if spec is not None else None,
        "interpretation": "uncalibrated_score_vs_observed_correctness; not_threshold_authority/1",
    }


def private_summary(comparison, adapter, *, calibration_specs=None):
    """Summarize a trusted actual comparison; returns private structures, no public serializer."""
    if type(adapter) is not HiringDomainAdapter:
        raise DomainError("actual_hiring_domain_adapter_required")
    _population(comparison)
    specs = dict(calibration_specs or {})
    if set(specs) - {(method, field) for method in comparison.methods for field in c.FIELD_IDS}:
        raise DomainError("unrequested_calibration_spec")
    methods = {}
    for method, result in comparison.methods.items():
        if result.status == "not_run":
            methods[method] = {
                "execution": "not_run",
                "requested": len(result.requested_item_ids),
                "actual_predictions": 0,
                "metrics": None,
            }
            continue
        machines, predictions = _machine_rows(result, adapter, method)
        partial = any(row.status != "ok" and row.status != "abstained" for row in result.outcomes)
        partial |= any(
            "partial_execution" in prediction.issues for prediction in predictions.values()
        )
        fields = {}
        for field in c.FIELD_IDS:
            rows = tuple(row for row in result.outcomes if row.field == field)
            fields[field] = field_summary(rows)
            fields[field]["calibration"] = _calibration(
                rows, machines, predictions, specs.get((method, field))
            )
        methods[method] = {
            "execution": "partial" if partial else "outcomes_complete",
            "requested": len(result.requested_item_ids),
            "actual_predictions": len(predictions),
            "calls_observed": result.calls_observed,
            "metrics": {
                "fields": fields,
                "skills": skill_summary(result.outcomes),
                "salary": salary_summary(
                    tuple(row for row in result.outcomes if row.field == "salary"),
                    machines,
                    adapter.registry,
                    extraction=method != "dev_majority",
                ),
            },
        }
    return {
        "kind": "private-hiring-statistics/1",
        "split": comparison.split,
        "frozen_population": len(comparison.frozen_item_ids),
        "methods": methods,
        "public_release": "not_authorized",
        "quality_claim": "none_from_library_controls",
    }


@dataclass(frozen=True)
class PairedMetric:
    spec: ResamplingSpec
    result: object
    stratification: str


def paired_field_intervals(
    comparison, *, field, label=None, metric="accuracy", month_by_item, seed=20261014
):
    """Private canonical2000-draw common-stream adapter. No corpus/history access.

    Multi-month families stay whole and use explicit unstratified resampling.
    Class support below15 keeps its point/counts but no claimed supported interval.
    """
    _population(comparison)
    if field not in c.FIELD_IDS or metric not in {"accuracy", "precision", "recall", "f1"}:
        raise DomainError("declared_field_metric_required")
    if set(month_by_item) != set(comparison.frozen_item_ids):
        raise DomainError("complete_month_population_required")
    from pydantic import TypeAdapter

    for month in month_by_item.values():
        TypeAdapter(c.Month).validate_python(month, strict=True)
    methods = {
        name: tuple(row for row in result.outcomes if row.field == field)
        for name, result in comparison.methods.items()
        if result.status == "executed"
    }
    if not methods:
        raise DomainError("no_executed_methods_for_intervals")
    group_months = {}
    for row in next(iter(methods.values())):
        group_months.setdefault(row.group_id, set()).add(month_by_item[row.item_id])
    stratified = all(len(months) == 1 for months in group_months.values())
    strata = (
        {group: next(iter(months)) for group, months in group_months.items()}
        if stratified
        else None
    )
    spec = ResamplingSpec(
        version="hiring-paired/1",
        unit="group_id",
        seed=seed,
        draws=2000,
        level=0.95,
        method="percentile",
        group_order=tuple(sorted(group_months)),
        stratum_map=strata,
        min_support=15,
        min_valid_draws=1900,
        statistic_version="hiring-field-target-support/1",
        rng_version="Python3.12/random",
    )
    if metric != "accuracy" and not any(
        stats.typed_equal(label, value)
        for value in CATEGORIES.get(field, (True, False, "not_stated"))
    ):
        raise DomainError("declared_class_required")

    def callback(rows):
        if metric == "accuracy":
            return stats.accuracy(rows, machine_automation_only=True)
        rates = stats.classification_rates(stats.confusion_counts(_class_rows(rows), label))
        # Required15 refers to target Gold class, including failures; never predicted support.
        return replace(getattr(rates, metric), support=rates.actual_support)

    result = paired_group_resample(methods, spec, callback)
    return PairedMetric(
        spec, result, "month_whole_groups" if stratified else "unstratified_cross_month_families"
    )
