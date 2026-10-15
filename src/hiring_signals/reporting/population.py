"""Own domain accounting; expected private IDs never enter a public projection.

Counts describe monthly predictions, not extraction accuracy or a Gold benchmark.
No additional source/company/organization marginal cuts are accepted.
"""

import hashlib
import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from hiring_signals import contracts as c
from hiring_signals.shared.aggregate_privacy import models as p

Scope = Literal["population_predictions", "original_synthetic_population", "gold_sample"]
Method = Literal["rules", "jev", "generative", "dev_majority", "human"]
Coverage = Literal["complete", "partial", "failed"]


class Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
        revalidate_instances="always",
    )


def record_version(record: c.PrivateDerivedRecord) -> str:
    record = c.PrivateDerivedRecord.model_validate(record)
    version = {
        key: getattr(record, key)
        for key in (
            "method",
            "model_sha256",
            "taxonomy_sha256",
            "config_sha256",
            "implementation_sha256",
        )
    }
    return hashlib.sha256(
        json.dumps(version, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class MonthlyCohort(Closed):
    """Private source-bound admission, supplied by an authorized workflow."""

    month: c.Month
    method: Method
    version_sha256: c.Digest
    source_scope: Scope
    source_coverage: Coverage
    method_status: Literal["run", "not_run"]
    missing_status: Literal["error", "blocked"]
    policy: p.Policy = p.POLICY_V1
    expected_ids: Annotated[tuple[c.Digest, ...], Field(max_length=600)]
    records: Annotated[tuple[c.PrivateDerivedRecord, ...], Field(max_length=600)]

    @model_validator(mode="after")
    def admitted(self) -> Self:
        expected = set(self.expected_ids)
        if len(expected) != len(self.expected_ids):
            raise ValueError("duplicate expected IDs")
        observed = set()
        if self.method_status == "not_run" and self.records:
            raise ValueError("not-run method cannot contain predictions")
        for record in self.records:
            if record.item_id not in expected or record.item_id in observed:
                raise ValueError("foreign or duplicate prediction ID")
            if record.month != self.month or record.method != self.method:
                raise ValueError("prediction month/method mismatch")
            if record_version(record) != self.version_sha256:
                raise ValueError("mixed or stale method/config versions")
            observed.add(record.item_id)
        return self


class PublicMonth(Closed):
    """Only public-safe released partitions and closed readiness/scope metadata."""

    month: c.Month
    method: Method
    version_sha256: c.Digest
    source_scope: Scope
    source_coverage: Coverage
    method_status: Literal["outcomes_complete", "partial", "not_run"]
    quality_status: Literal["not_measured"]
    policy: p.Policy = p.POLICY_V1
    eligible_denominator: Annotated[int, Field(ge=10, le=600)] | None
    partitions: Annotated[tuple[p.ReleasedPartition, ...], Field(max_length=37)]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if self.method_status == "not_run":
            if self.partitions:
                raise ValueError("not-run public method cannot contain fabricated field rows")
            return self
        if tuple(part.metric for part in self.partitions) != c.FIELD_IDS:
            raise ValueError("all thirty-seven public field partitions required")
        effective = self.source_coverage
        if effective == "complete" and self.method_status == "partial":
            effective = "partial"
        for part in self.partitions:
            if part.policy != self.policy:
                raise ValueError("mixed release policies within a monthly cohort")
            if part.evidence_category != "prediction":
                raise ValueError("population reports require prediction evidence")
            if (part.month, part.method, part.version_sha256, part.coverage) != (
                self.month,
                self.method,
                self.version_sha256,
                effective,
            ):
                raise ValueError("released partition identity/coverage mismatch")
            if part.denominator != self.eligible_denominator:
                raise ValueError("public denominators must refer to the same whole cohort")
        return self


def _judgment_label(judgment: c.Judgment) -> str:
    if judgment.process_status in {"error", "blocked"}:
        return judgment.process_status
    if judgment.process_status == "abstained":
        return judgment.evidence_state
    if isinstance(judgment, c.BooleanJudgment):
        return (
            "positive"
            if judgment.value is True
            else "negative"
            if judgment.value is False
            else "not_stated"
        )
    return judgment.value


def _field_label(classification: c.Classification, metric: str) -> str:
    if metric.startswith("skills."):
        return _judgment_label(getattr(classification.skills, metric.split(".")[1]))
    if metric == "salary":
        salary = classification.salary
        if salary.presence.value is True:
            return "stated_normalized" if salary.normalized is not None else "stated_unknown_units"
        return _judgment_label(salary.presence)
    return _judgment_label(getattr(classification, metric))


def aggregate_month(cohort: MonthlyCohort) -> PublicMonth:
    try:
        cohort = MonthlyCohort.model_validate(cohort)
    except (ValidationError, TypeError):
        raise ValueError("invalid_private_monthly_cohort") from None
    denominator = len(cohort.expected_ids)
    metadata = dict(
        month=cohort.month,
        method=cohort.method,
        version_sha256=cohort.version_sha256,
        source_scope=cohort.source_scope,
        source_coverage=cohort.source_coverage,
        quality_status="not_measured",
        policy=cohort.policy,
        eligible_denominator=denominator if denominator >= 10 else None,
    )
    if cohort.method_status == "not_run":
        return PublicMonth(**metadata, method_status="not_run", partitions=())
    indexed = {record.item_id: record for record in cohort.records}
    missing = denominator - len(indexed)
    processing_failure = any(
        judgment.process_status in {"error", "blocked"}
        for record in cohort.records
        for judgment in record.classification.judgments()
    )
    status = "partial" if missing or processing_failure else "outcomes_complete"
    coverage = (
        "partial"
        if status == "partial" and cohort.source_coverage == "complete"
        else cohort.source_coverage
    )
    parts = []
    for metric in c.FIELD_IDS:
        counts = dict.fromkeys(p.class_inventory(metric), 0)
        for item in cohort.expected_ids:
            record = indexed.get(item)
            label = _field_label(record.classification, metric) if record else cohort.missing_status
            counts[label] += 1
        private = p.Partition(
            month=cohort.month,
            metric=metric,
            method=cohort.method,
            version_sha256=cohort.version_sha256,
            evidence_category="prediction",
            coverage=coverage,
            denominator=denominator,
            cells=tuple(
                p.Cell(label=label, numerator=count, uncertainty=None)
                for label, count in counts.items()
            ),
        )
        parts.append(
            p.release_partition(private)
            if cohort.policy == p.POLICY_V1
            else p.release_partition(private, policy=cohort.policy)
        )
    return PublicMonth(**metadata, method_status=status, partitions=tuple(parts))
