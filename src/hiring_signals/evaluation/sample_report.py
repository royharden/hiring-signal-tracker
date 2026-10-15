"""Closed sample-prediction aggregates, separate from private Gold/quality statistics."""

from hiring_signals.reporting import population, render
from hiring_signals.shared.aggregate_privacy import models as privacy

from .domain import DomainError, ExecutionRegistry


def validate_window(month_ids, policy):
    if policy not in (privacy.POLICY_V1, privacy.POLICY_V2):
        raise DomainError("declared_sample_release_policy_required")
    try:
        return render.ReportWindow(
            schema_version=1,
            month_ids=month_ids,
            method="rules",
            source_scope="gold_sample",
            quality_status="not_measured",
            months=(),
        )
    except Exception:
        raise DomainError("four_consecutive_sample_months_required") from None


def build(registry, *, expected_item_ids, predictions, month_ids, policy=privacy.POLICY_V1):
    """Use actual raw issuance only; never accept reference labels or private metric summaries.

    This is trusted in-process construction, not independent data or release authority.
    Missing predictions stay in the full requested monthly population as failures.
    """
    window = validate_window(month_ids, policy)
    if (
        type(registry) is not ExecutionRegistry
        or type(expected_item_ids) is not tuple
        or not expected_item_ids
        or len(expected_item_ids) > 512
        or len(set(expected_item_ids)) != len(expected_item_ids)
        or set(expected_item_ids) != set(registry._items)
    ):
        raise DomainError("complete_requested_sample_population_required")
    items = tuple(registry._items[item_id] for item_id in expected_item_ids)
    if any(item.month not in window.month_ids for item in items):
        raise DomainError("sample_source_outside_declared_window")
    records, seen = [], set()
    for prediction in predictions:
        if (
            prediction.item_id not in expected_item_ids
            or prediction.item_id in seen
            or prediction.method != "rules"
        ):
            raise DomainError("wrong_or_duplicate_sample_prediction")
        seen.add(prediction.item_id)
        _, record = registry._lookup(prediction)
        records.append(record)
    if not records:
        raise DomainError("sample_has_no_actual_execution")
    version = population.record_version(records[0])
    if any(population.record_version(record) != version for record in records):
        raise DomainError("mixed_sample_method_versions")
    months = []
    for month_id in window.month_ids:
        expected = tuple(item.pin.item_id for item in items if item.month == month_id)
        if not expected:
            continue  # no supplied sample for this slot is a gap, never a zero cohort
        cohort = population.MonthlyCohort(
            month=month_id,
            method="rules",
            version_sha256=version,
            source_scope="gold_sample",
            source_coverage="complete",
            method_status="run",
            missing_status="error",
            policy=policy,
            expected_ids=expected,
            records=tuple(record for record in records if record.month == month_id),
        )
        months.append(population.aggregate_month(cohort))
    return render.ReportWindow(**(window.model_dump() | {"months": tuple(months)}))


def limitations(window):
    """Compatibility entrypoint; reporting owns the canonical prose generator."""
    from hiring_signals.reporting.limitations import sample_limitations

    try:
        return sample_limitations(window)
    except ValueError:
        raise DomainError("closed_rules_sample_window_required") from None
