"""Tiny domain codec controls; no independently authored dataset or measured quality."""

import hashlib
import json
from decimal import localcontext

import pytest

from hiring_signals import contracts as c
from hiring_signals.evaluation.labels import (
    DOMAIN_KIND,
    LabelCodecError,
    project_machine,
    project_reference,
)
from hiring_signals.extract import rules
from hiring_signals.shared.evalkit.models import FieldLabel, FieldLabels, GoldRecord, SourceRef

H = "a" * 64


def reference(field=None, value=None, presence="present", **updates):
    labels = {name: FieldLabel(presence="unlabelled", value=None) for name in c.FIELD_IDS}
    if field:
        labels[field] = FieldLabel(presence=presence, value=value)
    return GoldRecord(
        item_id=H,
        dataset="original-synthetic-control",
        group_id="b" * 64,
        split="dev",
        label_version="synthetic-labels/1",
        source_ref=SourceRef(handle="original-synthetic-control", sha256=H),
        input_sha256=H,
        label_source=updates.get("label_source", "synthetic"),
        label_provenance_ref=updates.get("label_provenance_ref"),
        domain_kind=DOMAIN_KIND,
        label_payload=FieldLabels(kind="field_labels", labels=labels),
    )


def machine(text="Details pending."):
    source = c.TransientInput(input_sha256=hashlib.sha256(text.encode()).hexdigest(), text=text)
    return c.PrivateDerivedRecord(
        schema_version=1,
        item_id=H,
        month="2026-10",
        input_sha256=source.input_sha256,
        taxonomy_sha256=H,
        config_sha256=H,
        implementation_sha256=H,
        method="rules",
        model_sha256=None,
        provenance=c.LabelProvenance(source="unprovided", actor_ref=None, attestation_sha256=None),
        classification=rules.classify(source),
    )


def by_id(rows):
    return {row.field_id: row for row in rows}


@pytest.mark.parametrize("field", c.FIELD_IDS)
def test_every_field_keeps_absent_eligible_and_unlabelled_ineligible(field):
    """Catches omitted feature axes or treating unlabelled references as negative examples."""
    absent = project_reference(reference(field, presence="absent"))
    assert tuple(row.field_id for row in absent) == c.FIELD_IDS
    assert len(absent) == 37
    row = by_id(absent)[field]
    assert row.eligible and row.value == "not_stated" and row.presence == "absent"
    unknown = by_id(project_reference(reference()))[field]
    assert not unknown.eligible and unknown.value is None


@pytest.mark.parametrize("value", [True, False, "not_stated"])
def test_boolean_reference_classes_preserve_explicit_false(value):
    """Catches false becoming absence or integer-zero truthiness becoming a class."""
    row = by_id(project_reference(reference("skills.python", value)))["skills.python"]
    assert row.presence == "present" and row.eligible and type(row.value) is type(value)
    assert row.value == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("skills.python", 0),
        ("ai_engineering_role", 1),
        ("portfolio_requested", "false"),
        ("location_stated", "somewhere"),
        ("work_mode", "full_time"),
        ("employment", "onsite"),
        ("seniority", "multiple"),
        ("seniority", {"category": "multiple", "levels": ["senior", "senior"]}),
        ("salary", {"minimum": 1, "maximum": "2", "currency": None, "period": None}),
        ("salary", {"minimum": "2", "maximum": "1", "currency": None, "period": None}),
        ("salary", {"minimum": "NaN", "maximum": "2", "currency": None, "period": None}),
        ("salary", {"minimum": "1", "maximum": "2", "currency": "BTC", "period": None}),
        ("salary", {"minimum": "1", "maximum": "2", "currency": None, "period": "fortnight"}),
        ("salary", {"minimum": "1", "maximum": "2", "currency": None, "period": None, "x": 1}),
    ],
)
def test_invalid_domain_values_reject_without_echo(field, value):
    """Catches schema-valid generic JSON slipping through a hiring-specific reference codec."""
    with pytest.raises(LabelCodecError, match="^invalid_domain_reference$"):
        project_reference(reference(field, value))


def test_salary_exact_decimal_unknown_units_and_explicit_none_stay_distinct():
    """Catches guessed units, floating-point money drift or absence replacing explicit none."""
    value = {"minimum": "100.00", "maximum": "1.20E+2", "currency": None, "period": None}
    row = by_id(project_reference(reference("salary", value)))["salary"]
    assert row.value == {"minimum": "100", "maximum": "120", "currency": None, "period": None}
    assert by_id(project_reference(reference("salary", "none")))["salary"].value == "none"
    assert by_id(project_reference(reference("salary", presence="absent")))["salary"].value == (
        "not_stated"
    )


def test_multiple_seniority_keeps_actual_distinct_levels_with_fixed_order():
    """Catches genuine multiple levels being reduced to one class or order creating false misses."""
    row = by_id(
        project_reference(
            reference("seniority", {"category": "multiple", "levels": ["staff_or_lead", "junior"]})
        )
    )["seniority"]
    assert row.value == {"category": "multiple", "levels": ["junior", "staff_or_lead"]}


@pytest.mark.parametrize("mutation", ["missing", "extra", "domain", "mutated_type"])
def test_full_reference_closure_revalidates_mutable_model_contents(mutation):
    """Catches frozen models' nested dictionaries bypassing required field/domain checks."""
    record = reference()
    if mutation == "missing":
        del record.label_payload.labels["salary"]
    elif mutation == "extra":
        record.label_payload.labels["other"] = FieldLabel(presence="unlabelled", value=None)
    elif mutation == "domain":
        record = record.model_copy(update={"domain_kind": "unrelated-domain"})
    else:
        record.label_payload.labels["skills.python"] = FieldLabel(presence="present", value=0)
    with pytest.raises(LabelCodecError, match="^invalid_domain_reference$"):
        project_reference(record)


@pytest.mark.parametrize("origin", ["human", "human_corrected"])
def test_human_reference_requires_injected_authority_even_with_provenance_string(origin):
    """Catches a self-attested string being treated as actual human Gold authority."""
    record = reference("skills.python", False, label_source=origin, label_provenance_ref=H)
    for authority in (None, lambda _: False, lambda _: 1):
        with pytest.raises(LabelCodecError, match="^human_reference_authority_required$"):
            project_reference(record, human_authority=authority)
    # A synthetic authority spy checks the injection seam; it authenticates no actual human.
    observed = []
    row = project_reference(record, human_authority=lambda r: observed.append(r) is None)
    assert observed[0] is not record and by_id(row)["skills.python"].value is False


def test_raw_machine_absence_and_explicit_skill_exclusion_are_different():
    """Catches excluded requirements being scored as unstated or false being lost in projection."""
    absent = by_id(project_machine(machine()))
    excluded = by_id(project_machine(machine("No Python required.")))
    assert absent["skills.python"].value == "not_stated"
    assert excluded["skills.python"].value is False
    assert all(row.process_status == "ok" for row in absent.values())
    assert len(absent) == 37


def test_invalid_reference_does_not_invoke_human_authority():
    """Catches an invalid domain value triggering an authority callback before validation."""
    record = reference("skills.python", 0, label_source="human", label_provenance_ref=H)
    observed = []
    with pytest.raises(LabelCodecError, match="^invalid_domain_reference$"):
        project_reference(record, human_authority=lambda r: observed.append(r) is None)
    assert observed == []


def test_bypassed_nested_type_never_emits_serializer_warning_with_private_value(recwarn, capsys):
    """Catches a nested frozen-model bypass leaking its rejected value through a warning."""
    canary = "SYNTHETIC_PRIVATE_REFERENCE_CANARY"
    record = reference().model_copy(update={"source_ref": canary})
    with pytest.raises(LabelCodecError, match="^invalid_domain_reference$") as error:
        project_reference(record)
    output = capsys.readouterr()
    assert not recwarn and canary not in str(error.value) + output.out + output.err


def test_unknown_salary_units_remain_answered_presence_with_normalization_abstention():
    """Catches valid stated money with unknown units being erased as a processing failure."""
    row = by_id(project_machine(machine("Salary:100000-120000")))["salary"]
    assert row.process_status == "ok" and row.normalization_status == "abstained"
    assert row.value == {"minimum": "100000", "maximum": "120000", "currency": None, "period": None}


def test_money_projection_does_not_round_under_ambient_decimal_context():
    """Catches Decimal.normalize silently rounding exact source money at low precision."""
    value = {"minimum": "100001.20", "maximum": "120005.10", "currency": None, "period": None}
    record = reference("salary", value)
    with localcontext() as context:
        context.prec = 2
        row = by_id(project_reference(record))["salary"]
    assert row.value == {
        "minimum": "100001.2",
        "maximum": "120005.1",
        "currency": None,
        "period": None,
    }


def test_raw_machine_mixed_field_statuses_remain_independent_without_invented_scores():
    """Catches successful fields hiding errors/blocks or being discarded with unrelated failures."""
    data = json.loads(machine("Requirements: Python").model_dump_json())
    values = data["classification"]
    common = dict(certainty=None, candidates=[], value=None)
    values["work_mode"] = dict(
        common, process_status="error", evidence_state="unavailable", error_code="provider_error"
    )
    values["skills"]["python"] = dict(
        common, process_status="blocked", evidence_state="unavailable", error_code="screen_hold"
    )
    values["portfolio_requested"] = dict(
        common, process_status="abstained", evidence_state="uncertain", error_code=None
    )
    rows = by_id(project_machine(c.PrivateDerivedRecord.model_validate_json(json.dumps(data))))
    assert rows["employment"].process_status == "ok"
    assert rows["work_mode"].process_status == "error"
    assert rows["work_mode"].error_code == "provider_error"
    assert rows["skills.python"].process_status == "blocked"
    assert rows["portfolio_requested"].process_status == "abstained"
    assert rows["work_mode"].value is rows["portfolio_requested"].value is None


@pytest.mark.parametrize("kind", ["human", "synthetic_expectation"])
def test_effective_human_or_reference_expectations_cannot_replace_machine_output(kind):
    """Catches reference/corrected labels being scored as raw machine automation output."""
    data = json.loads(machine().model_dump_json())
    if kind == "human":
        data["method"] = "human"
        data["provenance"] = dict(source="human_self_attested", actor_ref=H, attestation_sha256=H)
    else:
        data["provenance"]["source"] = "synthetic_expectation"
    record = c.PrivateDerivedRecord.model_validate_json(json.dumps(data))
    with pytest.raises(LabelCodecError, match="^raw_machine_record_required$"):
        project_machine(record)
