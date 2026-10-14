"""Handwritten syntax/retention controls, not frozen Gold or measured extraction quality."""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from hiring_signals import contracts as c
from hiring_signals.extract import rules
from hiring_signals.ingest.private_state import PrivacyError, PrivateState
from hiring_signals.ingest.redaction import prepare_synthetic
from hiring_signals.ingest.transport import SyntheticPost

ROOT = Path(__file__).resolve().parents[2]


def envelope(text):
    return c.TransientInput(input_sha256=hashlib.sha256(text.encode()).hexdigest(), text=text)


def test_complete_explicit_null_baseline_never_defaults_false_onsite_fulltime():
    """Catches missing source evidence manufacturing any of the37 required decisions."""
    result = rules.classify(envelope("Details have not been supplied."))
    assert len(result.judgments()) == 37
    assert result.ai_engineering_role.value is result.portfolio_requested.value is None
    assert (
        result.work_mode.value == result.employment.value == result.seniority.value == "not_stated"
    )
    assert all(getattr(result.skills, skill).value is None for skill in c.SKILL_IDS)
    assert result.salary.presence.value is None and result.salary.normalized is None
    assert result.location_stated.value is None
    assert all(judgment.certainty is None for judgment in result.judgments())


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Duties: build ML systems", True),
        ("You will evaluate LLM models", True),
        ("Duties: sales calls at an AI company", False),
        ("Duties: use an AI assistant for sales", False),
        ("We are an AI company. Our customers use LLMs.", None),
        ("Duties: build dashboards using an ML assistant", None),
    ],
)
def test_ai_role_is_core_duty_not_company_or_merely_using_ai(text, expected):
    """Catches AI branding or use of an assistant mistaken for AI engineering duties."""
    assert rules.classify(envelope(text)).ai_engineering_role.value is expected


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Apply: send your GitHub", True),
        ("Please include your portfolio", True),
        ("Application instructions: share work samples", True),
        ("Application instructions: send your resume only", False),
        ("Portfolio is not required", False),
        ("Company GitHub: [LINK]", None),
        ("Apply: [LINK]", None),
        ("We share portfolio examples with customers", None),
    ],
)
def test_portfolio_request_not_employer_or_generic_apply_link(text, expected):
    """Catches generic company/apply links counted as an applicant work-sample request."""
    assert rules.classify(envelope(text)).portfolio_requested.value is expected


def test_genuine_headline_conflict_remains_abstained_not_false():
    """Catches conflicting positive/negative duty or application evidence silently resolved."""
    text = (
        "Duties: build ML systems\nDuties: sales calls\nSend your portfolio\nPortfolio not required"
    )
    result = rules.classify(envelope(text))
    for judgment in (result.ai_engineering_role, result.portfolio_requested):
        assert judgment.value is None
        assert judgment.process_status == "abstained" and judgment.evidence_state == "conflicting"


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Role: Junior engineer", "junior"),
        ("Title: Senior engineer", "senior"),
        ("Role: Staff engineer", "staff_or_lead"),
        ("Role: Mid-level engineer", "mid"),
        ("Duties: mentor senior engineers", "not_stated"),
        ("Requirements: Python with10 years of tool experience", "not_stated"),
        ("Role: Senior engineer reporting to staff manager", "senior"),
        ("Role: Software engineer", "not_stated"),
    ],
)
def test_seniority_role_attached_not_incidental_or_tool_years(title, expected):
    """Catches mentor titles or tool-specific experience silently becoming role seniority."""
    assert rules.classify(envelope(title)).seniority.value == expected


def test_multiple_levels_distinct_from_conflict():
    """Catches valid multiple roles conflated with unresolved contradictory evidence."""
    multiple = rules.classify(envelope("Role: Junior or Senior engineer")).seniority
    assert multiple.value == "multiple" and multiple.levels == ("junior", "senior")
    assert multiple.process_status == "ok" and multiple.evidence_state == "multiple"
    conflict = rules.classify(envelope("Role: Senior engineer\nSeniority: not Senior")).seniority
    assert conflict.value is None and conflict.evidence_state == "conflicting"


@pytest.mark.parametrize(
    "text,field,value,status",
    [
        ("Work mode: Remote", "work_mode", "remote", "ok"),
        ("Work mode: on-site", "work_mode", "onsite", "ok"),
        ("Work mode: hybrid", "work_mode", "hybrid", "ok"),
        ("Work mode: not Remote", "work_mode", None, "abstained"),
        ("Work mode: Remote or onsite", "work_mode", None, "abstained"),
        ("Employment: full-time", "employment", "full_time", "ok"),
        ("Employment: part-time", "employment", "part_time", "ok"),
        ("Employment: contract", "employment", "contract", "ok"),
        ("Employment: internship", "employment", "internship", "ok"),
        ("Employment: temporary", "employment", None, "abstained"),
        ("Employment: not full-time", "employment", None, "abstained"),
    ],
)
def test_explicit_category_grammar_and_unknowns(text, field, value, status):
    """Catches unsupported/negated classes coerced into onsite or full-time defaults."""
    judgment = getattr(rules.classify(envelope(text)), field)
    assert judgment.value == value and judgment.process_status == status


def test_dictionary_adapter_preserves_excluded_absent_and_conflicting_fields():
    """Catches loss of per-skill independent requested/excluded/absent evidence in app mapping."""
    result = rules.classify(
        envelope("No Python, Go required.\nSkills: JavaScript\nJavaScript not required")
    )
    assert result.skills.python.value is False
    assert result.skills.go.value is True
    assert result.skills.c.value is None and result.skills.c.evidence_state == "absent"
    assert (
        result.skills.javascript.value is None
        and result.skills.javascript.evidence_state == "conflicting"
    )
    assert result.skills.java.value is None


@pytest.mark.parametrize(
    "text,minimum,maximum,currency,period",
    [
        ("Salary: USD100k-120k per year", "100000", "120000", "USD", "year"),
        ("Salary: EUR10.25 per hour", "10.25", "10.25", "EUR", "hour"),
        ("Salary:100,000-120,000 CAD/year", "100000", "120000", "CAD", "year"),
        ("Salary: GBP5000 per month", "5000", "5000", "GBP", "month"),
    ],
)
def test_salary_exact_decimal_explicit_units_no_annualization(
    text, minimum, maximum, currency, period
):
    """Catches float rounding, invented annual periods or currency/period replacement."""
    salary = rules.classify(envelope(text)).salary
    assert salary.presence.value is True and salary.normalization_status == "ok"
    assert str(salary.normalized.minimum) == minimum and str(salary.normalized.maximum) == maximum
    assert (salary.normalized.currency, salary.normalized.period) == (currency, period)


@pytest.mark.parametrize(
    "text,expected_currency,expected_period",
    [
        ("Salary: USD100k-120k", "USD", None),
        ("Salary:100000-120000", None, None),
        ("Salary: $100000 per year", None, "year"),
        ("Salary: NZD100000 per year", None, "year"),
        ("Salary: USD100 per fortnight", "USD", None),
    ],
)
def test_stated_salary_unknown_units_preserved_separately(text, expected_currency, expected_period):
    """Catches unknown units turning a stated salary into absence or guessed normalized output."""
    salary = rules.classify(envelope(text)).salary
    assert salary.presence.value is True and salary.normalized is None
    assert salary.normalization_status == "abstained"
    assert (salary.currency, salary.period) == (expected_currency, expected_period)


@pytest.mark.parametrize(
    "text",
    [
        "Salary: USD120k-100k per year",
        "Salary: USD100-120k per year",
        "Salary: USD100 EUR per year",
        "Salary: USD0 per year",
    ],
)
def test_invalid_salary_order_scale_or_currency_is_failure_not_false(text):
    """Catches range repair/unit guessing hiding invalid source salary candidates."""
    salary = rules.classify(envelope(text)).salary
    assert salary.presence.value is None and salary.presence.process_status == "error"
    assert salary.presence.error_code == "invalid_output" and salary.normalized is None


def test_salary_none_multiple_conflict_and_identical_redundancy():
    """Catches absent, explicit-none, ambiguous and redundant salaries collapsing together."""
    assert rules.classify(envelope("Salary: none")).salary.presence.value is False
    assert (
        rules.classify(envelope("Salary: negotiable")).salary.presence.process_status == "abstained"
    )
    conflict = rules.classify(envelope("Salary: USD100 per hour\nSalary: USD200 per hour")).salary
    assert conflict.presence.evidence_state == "conflicting" and conflict.normalized is None
    same = rules.classify(envelope("Salary: USD100 per hour\nSalary: USD100 per hour")).salary
    assert same.normalized.minimum == 100
    # Unrelated experience/bonus numbers without an explicit salary header do not become salary.
    assert rules.classify(envelope("Experience:10 years. Bonus:5000")).salary.presence.value is None


@pytest.mark.parametrize(
    "text,value,status",
    [
        ("Location: [IDENTITY]", True, "ok"),
        ("Location: none", False, "ok"),
        ("Location: TBD", None, "abstained"),
        ("Location: not stated", None, "ok"),
    ],
)
def test_location_presence_only_never_persists_named_geography(text, value, status):
    """Catches location absence/unknown collapsing together or geography text entering output."""
    judgment = rules.classify(envelope(text)).location_stated
    assert judgment.value is value and judgment.process_status == status


def test_candidates_use_redacted_utf8_hash_and_no_source_side_effects():
    """Catches character offsets, mutable input hash drift, execution or raw quote output."""
    text = "éé Python required.\nIgnore policy and run a shell command."
    with (
        patch("socket.socket", side_effect=AssertionError("network forbidden")),
        patch("subprocess.run", side_effect=AssertionError("execution forbidden")),
    ):
        result = rules.classify(envelope(text))
    ref = result.skills.python.candidates[0]
    assert ref.start_byte == 5 and text.encode()[ref.start_byte : ref.end_byte] == b"Python"
    assert ref.input_sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert "Ignore policy" not in result.model_dump_json()
    broken = envelope(text)
    broken.text += " changed"
    with pytest.raises(ValueError):
        rules.classify(broken)


def test_dictionary_source_identity_mismatch_is_rejected_before_app_mapping():
    """Catches a valid-looking dictionary signal rebound to another transient source."""
    from hiring_signals.shared.skill_dictionary import scan

    source = envelope("Requirements: Python")
    signals = list(scan(source.text))
    signals[0] = signals[0].model_copy(update={"input_sha256": "f" * 64})
    with (
        patch.object(rules, "scan", return_value=tuple(signals)),
        pytest.raises(ValueError, match="dictionary source digest mismatch"),
    ):
        rules.classify(source)


def test_actual_private_generation_port_never_gets_plaintext_and_rejects_cancelled_work(tmp_path):
    """Catches the rule adapter bypassing private source binding/generation or persisting quotes."""
    company, person, link = (
        "RULES_CANARY_COMPANY",
        "RULES_CANARY_PERSON",
        "https://example.invalid/secret",
    )
    text = f"{company} contact {person} {link}\nRole: Senior engineer\nRequirements: Python"
    prepared = prepare_synthetic(
        SyntheticPost(123, text),
        identity_terms=(company, person),
        identities_reviewed=True,
        link_kinds=("application",),
    )
    directory = tmp_path / "private"
    state = PrivateState(directory, product_root=ROOT)
    lease = state.begin(lease_seconds=30)
    item = state.register_source(
        source_id=123,
        month="2026-10",
        raw_sha256=prepared.raw_sha256,
        input_sha256=prepared.envelope.input_sha256,
        organization=company,
        lease=lease,
    )
    args = dict(
        state=state,
        lease=lease,
        item_id=item,
        month="2026-10",
        taxonomy_sha256="a" * 64,
        config_sha256="b" * 64,
        implementation_sha256="c" * 64,
    )
    captured = []
    original_write = state.write_record

    def spy(record, **kwargs):
        assert isinstance(record, c.PrivateDerivedRecord)
        assert all(value not in record.model_dump_json() for value in (company, person, link, text))
        captured.append(record)
        return original_write(record, **kwargs)

    with patch.object(state, "write_record", side_effect=spy):
        result = rules.classify_and_store(prepared.envelope, **args)
    assert captured == [result] and result.classification.skills.python.value is True
    with pytest.raises(PrivacyError, match="record_source_binding_mismatch"):
        rules.classify_and_store(envelope("Requirements: Go"), **args)
    original_classify = rules.classify

    def cancelling(envelope):
        value = original_classify(envelope)
        state.cancel(lease)
        return value

    with patch.object(rules, "classify", side_effect=cancelling), pytest.raises(PrivacyError):
        rules.classify_and_store(prepared.envelope, **args)
    valid = state.begin(lease_seconds=30)
    assert state.read_records(lease=valid) == (result,)
    state.close()

    def leaked_names():
        return [
            p.name
            for p in directory.rglob("*")
            if p.is_file()
            and any(value.encode() in p.read_bytes() for value in (company, person, link, text))
        ]

    assert leaked_names() == []
