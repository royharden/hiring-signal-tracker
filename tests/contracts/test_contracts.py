"""Original synthetic boundary controls, not human labels or model evaluation."""

import copy
import dataclasses
import hashlib
import json
import pickle
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from hiring_signals import contracts as c

ROOT = Path(__file__).resolve().parents[2]
HASH = "a" * 64
CANARY = "SYNTHETIC_PRIVATE_TEXT Canary Company https://example.invalid/person"


def boolean(value=None, evidence="absent", status="ok"):
    return {
        "value": value,
        "evidence_state": evidence,
        "process_status": status,
        "certainty": None,
        "candidates": [],
        "error_code": None,
    }


def reference():
    return {"input_sha256": HASH, "start_byte": 0, "end_byte": 5}


def explicit(value=True):
    result = boolean(value, "explicit_positive" if value else "explicit_negative")
    result["candidates"] = [reference()]
    return result


def classification():
    seniority = boolean("not_stated")
    seniority["levels"] = []
    return {
        "ai_engineering_role": boolean(),
        "portfolio_requested": boolean(),
        "seniority": seniority,
        "work_mode": boolean("not_stated"),
        "employment": boolean("not_stated"),
        "skills": {skill: boolean() for skill in c.SKILL_IDS},
        "salary": {
            "presence": boolean(),
            "stated_minimum": None,
            "stated_maximum": None,
            "currency": None,
            "period": None,
            "normalization_status": "not_applicable",
            "normalized": None,
        },
        "location_stated": boolean(),
    }


def record():
    return {
        "schema_version": 1,
        "item_id": "b" * 64,
        "month": "2026-10",
        "input_sha256": HASH,
        "taxonomy_sha256": "c" * 64,
        "config_sha256": "d" * 64,
        "implementation_sha256": "e" * 64,
        "method": "rules",
        "model_sha256": None,
        "provenance": {"source": "unprovided", "actor_ref": None, "attestation_sha256": None},
        "classification": classification(),
    }


def validate(model, data):
    return model.model_validate_json(json.dumps(data))


def test_inventory_and_all_fields_required():
    """Catches missing skill, headline or salary metadata silently defaulting."""
    assert len(c.SKILL_IDS) == len(set(c.SKILL_IDS)) == 30
    assert len(c.FIELD_IDS) == len(set(c.FIELD_IDS)) == 37
    assert tuple(c.SkillJudgments.model_fields) == c.SKILL_IDS
    for model in c.SCHEMA_MODELS.values():
        assert all(field.is_required() for field in model.model_fields.values())
    result = validate(c.Classification, classification())
    assert result.work_mode.value == "not_stated"
    assert result.employment.value == "not_stated"
    assert result.ai_engineering_role.value is None
    assert len(result.judgments()) == 37


@pytest.mark.parametrize("skill", c.SKILL_IDS)
def test_each_omitted_skill_rejected(skill):
    """Catches incomplete providers omitting any one of the thirty independent judgments."""
    data = classification()
    del data["skills"][skill]
    with pytest.raises(ValidationError):
        validate(c.Classification, data)


@pytest.mark.parametrize("field", tuple(c.Classification.model_fields))
def test_each_omitted_classification_field_rejected(field):
    """Catches missing mandatory category/candidate/presence envelopes."""
    data = classification()
    del data[field]
    with pytest.raises(ValidationError):
        validate(c.Classification, data)


@pytest.mark.parametrize(
    "value,evidence", [(True, "explicit_positive"), (False, "explicit_negative")]
)
def test_explicit_booleans_distinct_from_absence(value, evidence):
    """Catches explicit negative evidence collapsing into missing evidence."""
    result = validate(c.BooleanJudgment, explicit(value))
    assert result.value is value and result.evidence_state == evidence
    absent = validate(c.BooleanJudgment, boolean())
    assert absent.value is None and absent.process_status == "ok"


@pytest.mark.parametrize("value", [0, 1, "false", "true", "not_stated", [], {}])
def test_boolean_coercions_rejected(value):
    """Catches numeric/string booleans accepted from malformed model output."""
    data = explicit()
    data["value"] = value
    with pytest.raises(ValidationError):
        validate(c.BooleanJudgment, data)


@pytest.mark.parametrize("status", ["abstained", "error", "blocked"])
@pytest.mark.parametrize("field,default", [("work_mode", "onsite"), ("employment", "full_time")])
def test_failed_categories_never_default(field, default, status):
    """Catches abstention/provider/screen failure becoming a confident default class."""
    data = classification()[field]
    data.update(value=None, process_status=status)
    data["evidence_state"] = "uncertain" if status == "abstained" else "unavailable"
    data["error_code"] = {"abstained": None, "error": "provider_error", "blocked": "screen_hold"}[
        status
    ]
    model = c.WorkModeJudgment if field == "work_mode" else c.EmploymentJudgment
    assert validate(model, data).value is None
    data["value"] = default
    with pytest.raises(ValidationError):
        validate(model, data)


@pytest.mark.parametrize("field", ["work_mode", "employment"])
def test_absence_cannot_be_onsite_or_fulltime(field):
    """Catches the absence-to-default bug independent of failed processing."""
    data = classification()[field]
    data["value"] = "onsite" if field == "work_mode" else "full_time"
    with pytest.raises(ValidationError):
        validate(c.WorkModeJudgment if field == "work_mode" else c.EmploymentJudgment, data)


def test_multiple_seniority_and_unresolved_conflict_are_separate():
    """Catches valid multiple levels classified as failure or conflict classified as multiple."""
    data = boolean("multiple", "multiple")
    data.update(levels=["junior", "senior"], candidates=[reference()])
    assert validate(c.SeniorityJudgment, data).process_status == "ok"
    conflict = boolean(None, "conflicting", "abstained")
    conflict.update(levels=[], candidates=[reference()])
    assert validate(c.SeniorityJudgment, conflict).value is None
    for levels in (["senior"], ["senior", "senior"], ["senior", "not_stated"]):
        data["levels"] = levels
        with pytest.raises(ValidationError):
            validate(c.SeniorityJudgment, data)
    conflict["value"] = "multiple"
    with pytest.raises(ValidationError):
        validate(c.SeniorityJudgment, conflict)


@pytest.mark.parametrize(
    "change",
    [
        {"value": False, "evidence_state": "absent"},
        {"value": True, "evidence_state": "explicit_negative"},
        {"value": False, "evidence_state": "explicit_positive"},
        {"process_status": "error", "evidence_state": "absent"},
        {
            "process_status": "blocked",
            "evidence_state": "unavailable",
            "error_code": "provider_error",
        },
        {"process_status": "error", "evidence_state": "unavailable", "error_code": None},
        {"error_code": "provider_error"},
        {"value": True, "evidence_state": "explicit_positive", "candidates": []},
        {"candidates": [reference()]},
    ],
)
def test_invalid_process_evidence_combinations(change):
    """Catches status/evidence/answer contradictions and unsupported error defaults."""
    data = boolean()
    data.update(change)
    with pytest.raises(ValidationError):
        validate(c.BooleanJudgment, data)


def stated_salary():
    data = classification()["salary"]
    data.update(
        presence=explicit(),
        stated_minimum="100000",
        stated_maximum="120000",
        currency="USD",
        period="year",
        normalization_status="ok",
    )
    data["normalized"] = {
        "minimum": "100000",
        "maximum": "120000",
        "currency": "USD",
        "period": "year",
    }
    return data


def test_salary_explicit_units_and_stated_unknown_units():
    """Catches a stated amount with unknown units turning into missing or annual salary."""
    result = validate(c.SalaryJudgment, stated_salary())
    assert str(result.normalized.minimum) == "100000"
    for missing in ("currency", "period"):
        data = stated_salary()
        data.update(normalization_status="abstained", normalized=None)
        data[missing] = None
        result = validate(c.SalaryJudgment, data)
        assert result.presence.value is True and result.normalized is None


@pytest.mark.parametrize(
    "change",
    [
        {"currency": None},
        {"period": None},
        {"stated_minimum": "130000"},
        {"stated_maximum": None},
        {"stated_minimum": "NaN"},
        {"stated_minimum": "Infinity"},
        {"stated_minimum": "-1"},
        {"currency": "$"},
        {"period": "annual_guess"},
        {"normalization_status": "abstained"},
        {"normalized": None},
        {"presence": boolean()},
        {"stated_minimum": "0.00001"},
    ],
)
def test_invalid_salary_units_ranges_and_states(change):
    """Catches fabricated units, impossible ranges, nonfinite amounts and state contradictions."""
    data = stated_salary()
    data.update(change)
    with pytest.raises(ValidationError):
        validate(c.SalaryJudgment, data)


@pytest.mark.parametrize(
    "field,value",
    [("minimum", "90000"), ("maximum", "140000"), ("currency", "EUR"), ("period", "month")],
)
def test_normalized_salary_cannot_fabricate_candidate_value(field, value):
    """Catches a model replacing a selected candidate with a different amount/unit."""
    data = stated_salary()
    data["normalized"][field] = value
    with pytest.raises(ValidationError):
        validate(c.SalaryJudgment, data)


@pytest.mark.parametrize(
    "change",
    [
        {"start_byte": -1},
        {"end_byte": 0},
        {"start_byte": 5, "end_byte": 5},
        {"end_byte": 32769},
        {"start_byte": True},
        {"input_sha256": "source-name"},
        {"snippet": CANARY},
        {"url": "https://example.invalid"},
    ],
)
def test_candidate_reference_rejects_unsafe_or_invalid_coordinates(change):
    """Catches free source text/URLs and invalid/unbounded candidate coordinates."""
    data = reference()
    data.update(change)
    with pytest.raises(ValidationError):
        validate(c.CandidateReference, data)


@pytest.mark.parametrize("value", [-0.1, 1.01, "0.5", True, "NaN"])
def test_certainty_bounded_strict_and_finite(value):
    """Catches unbounded, coerced or nonfinite answer certainty."""
    with pytest.raises(ValidationError):
        validate(c.Certainty, {"kind": "native_probability", "value": value})


def test_private_record_roundtrip_method_and_input_binding():
    """Catches fake model certainty/source references surviving the private boundary."""
    data = record()
    data["classification"]["ai_engineering_role"] = explicit()
    result = validate(c.PrivateDerivedRecord, data)
    assert c.PrivateDerivedRecord.model_validate_json(result.model_dump_json()) == result
    data["classification"]["ai_engineering_role"]["candidates"][0]["input_sha256"] = "f" * 64
    with pytest.raises(ValidationError):
        validate(c.PrivateDerivedRecord, data)
    for method, kind in (("jev", "native_probability"), ("generative", "self_reported_confidence")):
        data = record()
        data.update(method=method, model_sha256="f" * 64)
        data["classification"]["portfolio_requested"] = explicit(False)
        data["classification"]["portfolio_requested"]["certainty"] = {"kind": kind, "value": 0.7}
        assert validate(c.PrivateDerivedRecord, data).method == method
        data["classification"]["portfolio_requested"]["certainty"]["kind"] = (
            "self_reported_confidence" if method == "jev" else "native_probability"
        )
        with pytest.raises(ValidationError):
            validate(c.PrivateDerivedRecord, data)


@pytest.mark.parametrize(
    "path",
    [
        (),
        ("classification",),
        ("classification", "skills"),
        ("classification", "salary"),
        ("classification", "ai_engineering_role"),
        ("provenance",),
    ],
)
@pytest.mark.parametrize("key", ["raw_text", "company", "person", "apply_url"])
def test_private_projection_rejects_injected_text_at_every_layer(path, key):
    """Privacy control: planted owned canaries must fail at nested persistent boundaries."""
    data = record()
    target = data
    for segment in path:
        target = target[segment]
    target[key] = CANARY
    with pytest.raises(ValidationError) as failure:
        validate(c.PrivateDerivedRecord, data)
    assert CANARY not in str(failure.value)
    # Do not log errors(). It can contain rejected inputs even with hidden display values.


@pytest.mark.parametrize(
    "field",
    ["item_id", "input_sha256", "taxonomy_sha256", "config_sha256", "implementation_sha256"],
)
def test_safe_metadata_cannot_replace_hash_with_private_text(field):
    """Catches private company/person/link text smuggled into metadata strings."""
    data = record()
    data[field] = CANARY
    with pytest.raises(ValidationError):
        validate(c.PrivateDerivedRecord, data)


def test_human_provenance_unprovided_and_self_attestation_not_authentication():
    """Catches an agent expectation or actor label silently treated as corrected human gold."""
    assert validate(c.PrivateDerivedRecord, record()).provenance.source == "unprovided"
    for source in ("unprovided", "synthetic_expectation"):
        with pytest.raises(ValidationError):
            validate(
                c.LabelProvenance, {"source": source, "actor_ref": HASH, "attestation_sha256": HASH}
            )
    with pytest.raises(ValidationError):
        validate(
            c.LabelProvenance,
            {"source": "human_self_attested", "actor_ref": None, "attestation_sha256": None},
        )
    data = record()
    data["provenance"] = {
        "source": "human_self_attested",
        "actor_ref": HASH,
        "attestation_sha256": HASH,
    }
    with pytest.raises(ValidationError):
        validate(c.PrivateDerivedRecord, data)
    data["method"] = "human"
    assert validate(c.PrivateDerivedRecord, data).method == "human"
    data["provenance"]["actor_ref"] = "Roy"
    with pytest.raises(ValidationError):
        validate(c.PrivateDerivedRecord, data)


def test_transient_text_not_serializable_or_echoed_and_digest_checked():
    """Catches raw processing text entering JSON/pickle/dict-based persistent envelopes."""
    digest = hashlib.sha256(CANARY.encode()).hexdigest()
    envelope = c.TransientInput(input_sha256=digest, text=CANARY)
    assert CANARY not in repr(envelope)
    for operation in (json.dumps, pickle.dumps, vars, dataclasses.asdict):
        with pytest.raises(TypeError):
            operation(envelope)
    with pytest.raises(ValueError):
        c.TransientInput(input_sha256=HASH, text=CANARY)
    # Two-byte characters catch character-count bounds mistaken for UTF-8 bytes.
    text = "é" * 16385
    with pytest.raises(ValueError):
        c.TransientInput(input_sha256=hashlib.sha256(text.encode()).hexdigest(), text=text)


@pytest.mark.parametrize(
    "model,name", [(c.TaxonomyConfig, "taxonomy-v1"), (c.ExperimentConfig, "experiment")]
)
def test_committed_configs_exact_closed_inventory(model, name):
    """Catches inventory drift and config claims of authorized providers/human evaluation."""
    data = json.loads((ROOT / "config" / f"{name}.json").read_text(encoding="utf-8"))
    assert validate(model, data)
    key = "skills" if name == "taxonomy-v1" else "field_ids"
    for replacement in (data[key][:-1], list(reversed(data[key])), [CANARY] * len(data[key])):
        changed = copy.deepcopy(data)
        changed[key] = replacement
        with pytest.raises(ValidationError):
            validate(model, changed)
    data["raw_text"] = CANARY
    with pytest.raises(ValidationError):
        validate(model, data)


def test_generated_schema_matches_models_and_closes_every_object():
    """Catches stale schemas or a nested open/free-text object hidden in schema closure."""
    for name, schema in c.schema_documents().items():
        assert (
            json.loads((ROOT / "config" / "schemas" / f"{name}.schema.json").read_text()) == schema
        )
        assert schema["x-runtime-validators-required"] is True
        objects = [schema, *schema.get("$defs", {}).values()]
        for obj in objects:
            if obj.get("type") == "object":
                assert obj["additionalProperties"] is False
                assert set(obj["required"]) == set(obj["properties"])


def test_detached_model_and_schema_generator_closure(tmp_path):
    """Catches source/package/workspace imports or a schema generator needing parent artifacts."""
    detached = tmp_path / "detached"
    source = detached / "src" / "hiring_signals"
    source.mkdir(parents=True)
    # Only the model module and minimal package marker are copied; no workspace/config dependency.
    shutil.copy2(ROOT / "src" / "hiring_signals" / "contracts.py", source / "contracts.py")
    (source / "__init__.py").write_text("", encoding="utf-8")
    scripts = detached / "scripts"
    scripts.mkdir()
    for name in ("_bootstrap.py", "generate_schemas.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    completed = subprocess.run(
        [sys.executable, "-I", str(scripts / "generate_schemas.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    for name, schema in c.schema_documents().items():
        path = detached / "config" / "schemas" / f"{name}.schema.json"
        assert json.loads(path.read_text()) == schema
    # Isolated process validates a record using only detached models and installed Pydantic.
    consumer = detached / "consumer.py"
    consumer.write_text(
        "import json, sys\nfrom pathlib import Path\n"
        "sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))\n"
        "from hiring_signals.contracts import PrivateDerivedRecord\n"
        "result = PrivateDerivedRecord.model_validate_json(sys.stdin.read())\n"
        "assert result.provenance.source == 'unprovided'\n"
        "assert len(result.classification.judgments()) == 37\n"
        "print('detached-derived-record-valid')\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-I", str(consumer)],
        input=json.dumps(record()),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "detached-derived-record-valid"


@pytest.mark.parametrize(
    "model,data",
    [
        (c.BooleanJudgment, boolean()),
        (c.SeniorityJudgment, classification()["seniority"]),
        (c.WorkModeJudgment, classification()["work_mode"]),
        (c.EmploymentJudgment, classification()["employment"]),
        (c.SalaryJudgment, classification()["salary"]),
        (c.NormalizedSalary, stated_salary()["normalized"]),
        (c.PrivateDerivedRecord, record()),
        (c.LabelProvenance, record()["provenance"]),
    ],
)
def test_omitted_nested_metadata_never_gets_defaults(model, data):
    """Catches missing nullable/status/provenance fields being treated as supplied metadata."""
    for field in model.model_fields:
        changed = copy.deepcopy(data)
        del changed[field]
        with pytest.raises(ValidationError):
            validate(model, changed)


@pytest.mark.parametrize(
    "model,values",
    [
        (c.SeniorityJudgment, ["junior", "mid", "senior", "staff_or_lead"]),
        (c.WorkModeJudgment, ["remote", "hybrid", "onsite"]),
        (c.EmploymentJudgment, ["full_time", "part_time", "contract", "internship"]),
    ],
)
def test_stated_category_controls(model, values):
    """Catches a strict validator accidentally rejecting supported stated classes."""
    for value in values:
        data = boolean(value, "explicit_positive")
        data["candidates"] = [reference()]
        if model is c.SeniorityJudgment:
            data["levels"] = []
        assert validate(model, data).value == value


@pytest.mark.parametrize("status", ["abstained", "error", "blocked"])
def test_salary_failure_remains_unanswered(status):
    """Catches semantic failures converted into a stated or successfully normalized salary."""
    data = classification()["salary"]
    data["presence"] = boolean(
        None, "uncertain" if status == "abstained" else "unavailable", status
    )
    data["presence"]["error_code"] = {
        "abstained": None,
        "error": "invalid_output",
        "blocked": "screen_hold",
    }[status]
    data["normalization_status"] = status
    assert validate(c.SalaryJudgment, data).normalized is None
    data["normalization_status"] = "ok"
    with pytest.raises(ValidationError):
        validate(c.SalaryJudgment, data)


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": True},
        {"schema_version": "1"},
        {"month": "2026-13"},
        {"month": "2026-1"},
        {"method": "provider_fallback"},
        {"model_sha256": HASH},
        {"method": "jev"},
        {"method": "human"},
    ],
)
def test_invalid_record_identity_version_and_method_metadata(change):
    """Catches scalar coercion and missing/contradictory method-version/provenance identity."""
    data = record()
    data.update(change)
    with pytest.raises(ValidationError):
        validate(c.PrivateDerivedRecord, data)


def test_mutation_and_constructed_invalid_instances_revalidated():
    """Catches bypassed model construction accepted without boundary revalidation."""
    result = validate(c.BooleanJudgment, explicit())
    with pytest.raises(ValidationError):
        result.value = False
    unchecked = result.model_copy(update={"value": "false"})
    with pytest.raises(ValidationError):
        c.BooleanJudgment.model_validate(unchecked)
