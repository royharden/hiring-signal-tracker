"""Pure domain projections, not a scorer, Gold authority, dataset or experiment runner."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import get_args

from pydantic import TypeAdapter, ValidationError

from hiring_signals import contracts as c
from hiring_signals.annotation.models import MultipleLevels, SalaryValue
from hiring_signals.shared.evalkit.models import FieldLabels, GoldRecord

DOMAIN_KIND = "hiring-signals/1"
_CATEGORY_MODELS = {
    "seniority": c.SeniorityJudgment,
    "work_mode": c.WorkModeJudgment,
    "employment": c.EmploymentJudgment,
}
_LEVEL_ORDER = get_args(c.Level)


class LabelCodecError(ValueError):
    """Closed failure code; never include rejected reference values in an exception."""


@dataclass(frozen=True)
class ReferenceField:
    field_id: str
    presence: str
    value: object

    @property
    def eligible(self) -> bool:
        return self.presence != "unlabelled"


@dataclass(frozen=True)
class MachineField:
    field_id: str
    value: object
    process_status: str
    evidence_state: str
    error_code: str | None
    certainty_kind: str | None
    certainty_value: float | None
    normalization_status: str | None


def _decimal(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _salary(value: SalaryValue) -> dict:
    return {
        "minimum": _decimal(value.minimum),
        "maximum": _decimal(value.maximum),
        "currency": value.currency,
        "period": value.period,
    }


def _multiple(value: MultipleLevels) -> dict:
    return {
        "category": "multiple",
        "levels": [level for level in _LEVEL_ORDER if level in value.levels],
    }


def _label_value(field: str, value: object) -> object:
    """Domain normalization only. No generic comparison or statistical formulas."""
    if field == "salary":
        if type(value) is str and value in {"none", "not_stated"}:
            return value
        if type(value) is not dict or any(
            type(value.get(key)) is not str for key in ("minimum", "maximum")
        ):
            raise ValueError()
        return _salary(SalaryValue.model_validate_json(json.dumps(value, allow_nan=False)))
    if field == "seniority" and type(value) is dict:
        return _multiple(MultipleLevels.model_validate_json(json.dumps(value, allow_nan=False)))
    if field in _CATEGORY_MODELS:
        if value is None or value == "multiple":
            raise ValueError()
        return TypeAdapter(
            _CATEGORY_MODELS[field].model_fields["value"].annotation
        ).validate_python(value, strict=True)
    if type(value) is bool or value == "not_stated":
        return value
    raise ValueError()


def project_reference(
    record: GoldRecord,
    *,
    human_authority: Callable[[GoldRecord], bool] | None = None,
) -> tuple[ReferenceField, ...]:
    """Actual human validation is injected; a callback or matching digest is not evidence itself.

    This validates domain values only. It does not establish rights, split independence,
    heldout exposure history, label/version ratification or a trustworthy source body.
    """
    try:
        if type(record) is not GoldRecord:
            raise ValueError()
        # Frozen models still contain mutable dictionaries. Revalidate a detached wire view.
        record = GoldRecord.model_validate_json(record.model_dump_json(warnings="error"))
        if record.domain_kind != DOMAIN_KIND or type(record.label_payload) is not FieldLabels:
            raise ValueError()
        labels = record.label_payload.labels
        if set(labels) != set(c.FIELD_IDS):
            raise ValueError()
        result = tuple(
            ReferenceField(
                field,
                labels[field].presence,
                _label_value(field, labels[field].value)
                if labels[field].presence == "present"
                else "not_stated"
                if labels[field].presence == "absent"
                else None,
            )
            for field in c.FIELD_IDS
        )
        if record.label_source in {"human", "human_corrected"} and (
            human_authority is None or human_authority(record) is not True
        ):
            raise LabelCodecError("human_reference_authority_required")
        return result
    except LabelCodecError:
        raise
    except Exception:
        raise LabelCodecError("invalid_domain_reference") from None


def project_machine(record: c.PrivateDerivedRecord) -> tuple[MachineField, ...]:
    """Project the actual raw machine record, retaining independent field processing metadata.

    No canonical Outcome/Prediction/compare adapter is supplied here: that join awaits
    the source-owned mixed-field status contract. This creates no experiment result.
    """
    try:
        if type(record) is not c.PrivateDerivedRecord:
            raise ValueError()
        record = c.PrivateDerivedRecord.model_validate(record)
        if record.method == "human" or record.provenance.source != "unprovided":
            raise LabelCodecError("raw_machine_record_required")
        result = []
        for field, judgment in zip(c.FIELD_IDS, record.classification.judgments(), strict=True):
            value = judgment.value
            normalization = None
            if field == "salary":
                salary = record.classification.salary
                normalization = salary.normalization_status
                value = (
                    _salary(
                        SalaryValue(
                            minimum=salary.stated_minimum,
                            maximum=salary.stated_maximum,
                            currency=salary.currency,
                            period=salary.period,
                        )
                    )
                    if judgment.value is True
                    else "none"
                    if judgment.value is False
                    else None
                )
            elif field == "seniority" and value == "multiple":
                value = _multiple(
                    MultipleLevels(
                        category="multiple", levels=record.classification.seniority.levels
                    )
                )
            if judgment.process_status == "ok" and value is None:
                value = "not_stated"
            certainty = judgment.certainty
            result.append(
                MachineField(
                    field,
                    value,
                    judgment.process_status,
                    judgment.evidence_state,
                    judgment.error_code,
                    certainty.kind if certainty else None,
                    certainty.value if certainty else None,
                    normalization,
                )
            )
        return tuple(result)
    except LabelCodecError:
        raise
    except (ValueError, TypeError, AttributeError, ValidationError):
        raise LabelCodecError("invalid_raw_machine_record") from None
