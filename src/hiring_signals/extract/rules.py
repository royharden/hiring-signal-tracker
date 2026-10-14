"""Narrow declared baseline over bounded redacted transient text.

No source quotes, locations or company/person/link strings enter the result.
No rules confidence/calibration, real gold quality or semantic model is claimed.
"""

import re
from decimal import Decimal, InvalidOperation

from hiring_signals import contracts as c
from hiring_signals.ingest.private_state import Lease, PrivateState
from hiring_signals.shared.skill_dictionary import scan


def _reference(envelope: c.TransientInput, start: int, end: int) -> c.CandidateReference:
    return c.CandidateReference(
        input_sha256=envelope.input_sha256,
        start_byte=len(envelope.text[:start].encode()),
        end_byte=len(envelope.text[:end].encode()),
    )


def _base(*, evidence="absent", status="ok", candidates=(), code=None):
    return {
        "evidence_state": evidence,
        "process_status": status,
        "certainty": None,
        "candidates": tuple(candidates)[:8],
        "error_code": code,
    }


def _boolean(status: str, references=()) -> c.BooleanJudgment:
    if status == "requested":
        return c.BooleanJudgment(
            value=True, **_base(evidence="explicit_positive", candidates=references)
        )
    if status == "excluded":
        return c.BooleanJudgment(
            value=False, **_base(evidence="explicit_negative", candidates=references)
        )
    if status in {"conflicting", "uncertain"}:
        return c.BooleanJudgment(
            value=None, **_base(evidence=status, status="abstained", candidates=references)
        )
    return c.BooleanJudgment(value=None, **_base())


def _find(envelope, expression):
    return tuple(
        _reference(envelope, match.start(), match.end())
        for match in re.finditer(expression, envelope.text, re.I)
    )[:8]


def _headline(envelope, positive, negative):
    positives, negatives = _find(envelope, positive), _find(envelope, negative)
    if positives and negatives:
        return _boolean("conflicting", (*positives[:4], *negatives[:4]))
    if positives:
        return _boolean("requested", positives)
    if negatives:
        return _boolean("excluded", negatives)
    return _boolean("not_stated")


def _headers(envelope, heading):
    return tuple(re.finditer(r"(?im)^\s*(?:" + heading + r")\s*:\s*([^\n;]+)", envelope.text))


def _category(envelope, heading, classes, model, *, seniority=False):
    headers = _headers(envelope, heading)
    found, rejected, references = set(), set(), []
    uncertain = False
    for header in headers:
        value = re.split(
            r"\b(?:reporting to|mentoring|collaborating with)\b", header.group(1), flags=re.I
        )[0]
        matches = []
        for canonical, expression in classes.items():
            for match in re.finditer(expression, value, re.I):
                start = header.start(1) + match.start()
                end = header.start(1) + match.end()
                negative = bool(re.search(r"\b(?:not|no)\s+$", value[: match.start()], re.I))
                (rejected if negative else found).add(canonical)
                matches.append(_reference(envelope, start, end))
        references.extend(matches)
        if not matches and not re.fullmatch(r"\s*(?:not stated|unspecified)\s*", value, re.I):
            role_heading = header.group(0).split(":", 1)[0].strip().lower() in {"role", "title"}
            if not (seniority and role_heading and not re.search(r"\bprincipal\b", value, re.I)):
                uncertain = True
    extra = {"levels": ()} if seniority else {}
    if found & rejected or (len(found) > 1 and not seniority):
        return model(
            value=None,
            **extra,
            **_base(evidence="conflicting", status="abstained", candidates=references),
        )
    if uncertain or (rejected and not found):
        return model(
            value=None,
            **extra,
            **_base(evidence="uncertain", status="abstained", candidates=references),
        )
    if len(found) > 1:
        levels = tuple(level for level in classes if level in found)
        return model(
            value="multiple", levels=levels, **_base(evidence="multiple", candidates=references)
        )
    if found:
        return model(
            value=next(iter(found)),
            **extra,
            **_base(evidence="explicit_positive", candidates=references),
        )
    return model(value="not_stated", **extra, **_base())


def _location(envelope):
    positives, negatives, unknown = [], [], []
    for header in _headers(envelope, "Location"):
        value = header.group(1).strip()
        ref = _reference(envelope, header.start(), header.end())
        if value.lower() in {"none", "not applicable"}:
            negatives.append(ref)
        elif value.lower() in {"tbd", "unknown", "undecided"}:
            unknown.append(ref)
        elif value.lower() not in {"not stated", "unspecified"}:
            positives.append(ref)
    if positives and negatives:
        return _boolean("conflicting", (*positives, *negatives))
    if unknown:
        return _boolean("uncertain", unknown)
    if positives:
        return _boolean("requested", positives)
    if negatives:
        return _boolean("excluded", negatives)
    return _boolean("not_stated")


_NUMBER = r"(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]{1,4})?[kK]?"
_SALARY = re.compile(
    r"^\s*(?P<currency1>[A-Z]{3}|\$)?\s*(?P<minimum>" + _NUMBER + r")"
    r"(?:\s*[-–]\s*(?P<maximum>" + _NUMBER + r"))?\s*(?P<currency2>[A-Z]{3})?"
    r"(?:\s*(?:/|per\s+)(?P<period>[a-z]{1,16})|\s+(?P<annual>annually|yearly))?\s*$",
    re.I,
)


def _amount(value: str) -> Decimal:
    suffix = value.lower().endswith("k")
    result = Decimal((value[:-1] if suffix else value).replace(",", ""))
    if suffix:
        result *= 1000
    return result


def _empty_salary(presence, status):
    return c.SalaryJudgment(
        presence=presence,
        stated_minimum=None,
        stated_maximum=None,
        currency=None,
        period=None,
        normalization_status=status,
        normalized=None,
    )


def _salary(envelope):
    headers = _headers(envelope, "Salary|Compensation")
    if not headers:
        return _empty_salary(_boolean("not_stated"), "not_applicable")
    parsed = []
    refs = []
    for header in headers:
        value = header.group(1).strip()
        ref = _reference(envelope, header.start(), header.end())
        refs.append(ref)
        if value.lower() in {"none", "unpaid"}:
            parsed.append(("excluded", None))
            continue
        if value.lower() in {"not stated", "unspecified"}:
            parsed.append(("not_stated", None))
            continue
        match = _SALARY.fullmatch(value)
        if not match:
            parsed.append(("uncertain", None))
            continue
        try:
            minimum = _amount(match["minimum"])
            maximum = _amount(match["maximum"] or match["minimum"])
            if match["maximum"] and match["minimum"].lower().endswith("k") != match[
                "maximum"
            ].lower().endswith("k"):
                raise ValueError("ambiguous_range_scale")
            if minimum <= 0 or maximum < minimum:
                raise ValueError("invalid_range")
            prefix, suffix = match["currency1"], match["currency2"]
            if prefix and suffix and prefix.upper() != suffix.upper():
                raise ValueError("conflicting_currency")
            currency = (prefix or suffix or "").upper()
            currency = (
                currency
                if currency in {"USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "INR"}
                else None
            )
            period = (
                "year"
                if match["annual"]
                else (match["period"].lower() if match["period"] else None)
            )
            if period not in {"hour", "day", "week", "month", "year"}:
                period = None
            normalized = (
                c.NormalizedSalary(
                    minimum=minimum, maximum=maximum, currency=currency, period=period
                )
                if currency and period
                else None
            )
            result = c.SalaryJudgment(
                presence=_boolean("requested", (ref,)),
                stated_minimum=minimum,
                stated_maximum=maximum,
                currency=currency,
                period=period,
                normalization_status="ok" if normalized else "abstained",
                normalized=normalized,
            )
            parsed.append(("requested", result))
        except (ValueError, InvalidOperation):
            presence = c.BooleanJudgment(
                value=None, **_base(evidence="unavailable", status="error", code="invalid_output")
            )
            return _empty_salary(presence, "error")
    kinds = {kind for kind, _ in parsed}
    semantic_values = {
        (result.stated_minimum, result.stated_maximum, result.currency, result.period)
        for _, result in parsed
        if result
    }
    if len(kinds) > 1 or len(semantic_values) > 1:
        return _empty_salary(_boolean("conflicting", refs), "abstained")
    kind = parsed[0][0]
    if kind == "requested":
        return parsed[0][1]
    if kind == "excluded":
        return _empty_salary(_boolean("excluded", refs), "not_applicable")
    if kind == "not_stated":
        return _empty_salary(_boolean("not_stated"), "not_applicable")
    return _empty_salary(_boolean("uncertain", refs), "abstained")


def classify(envelope: c.TransientInput) -> c.Classification:
    """Classify only an actual digest-verified transient envelope; no file/network access."""
    if not isinstance(envelope, c.TransientInput):
        raise ValueError("rules require a transient envelope")
    envelope = c.TransientInput(input_sha256=envelope.input_sha256, text=envelope.text)
    skills = {}
    for signal in scan(envelope.text):
        if signal.input_sha256 != envelope.input_sha256:
            raise ValueError("dictionary source digest mismatch")
        refs = tuple(
            c.CandidateReference(
                input_sha256=envelope.input_sha256,
                start_byte=match.start_byte,
                end_byte=match.end_byte,
            )
            for match in signal.matches
        )
        skills[signal.skill_id] = _boolean(signal.status, refs)
    return c.Classification(
        ai_engineering_role=_headline(
            envelope,
            r"(?:Duties\s*:|Responsibilities\s*:|You will)\s*"
            r"(?:build|develop|train|evaluate|deploy)"
            r"(?: and (?:build|develop|train|evaluate|deploy))?\s+(?:the |production )?"
            r"(?:ML|LLM|machine learning|language model)"
            r"\s+(?:systems|models|pipelines|agents|applications|infrastructure)\b",
            r"(?:Duties|Responsibilities)\s*:\s*(?:sales calls|customer outreach|sell products|"
            r"account management|customer support|use an AI assistant for sales)\b",
        ),
        portfolio_requested=_headline(
            envelope,
            r"(?m)^\s*(?:(?:Apply|Application instructions|Applicants?)\s*:\s*)?(?:please\s+)?"
            r"(?:include|send|share|provide)\s+(?:your\s+)?"
            r"(?:portfolio|work samples|GitHub|something you built)\b",
            r"\b(?:no portfolio (?:is )?(?:required|requested)|portfolio (?:is )?not required)\b|"
            r"Application instructions\s*:\s*(?:send|email)\s+(?:your\s+)?(?:resume|CV)\s+only\b",
        ),
        seniority=_category(
            envelope,
            "Role|Title|Seniority",
            {
                "junior": r"\bjunior\b",
                "mid": r"\bmid(?:-level)?\b",
                "senior": r"\bsenior\b",
                "staff_or_lead": r"\b(?:staff|lead)\b",
            },
            c.SeniorityJudgment,
            seniority=True,
        ),
        work_mode=_category(
            envelope,
            "Work mode",
            {
                "remote": r"\bremote\b",
                "hybrid": r"\bhybrid\b",
                "onsite": r"\bon[- ]?site\b",
            },
            c.WorkModeJudgment,
        ),
        employment=_category(
            envelope,
            "Employment",
            {
                "full_time": r"\bfull[- ]time\b",
                "part_time": r"\bpart[- ]time\b",
                "contract": r"\bcontract\b",
                "internship": r"\binternship\b",
            },
            c.EmploymentJudgment,
        ),
        skills=c.SkillJudgments(**skills),
        salary=_salary(envelope),
        location_stated=_location(envelope),
    )


def classify_and_store(
    envelope: c.TransientInput,
    *,
    state: PrivateState,
    lease: Lease,
    item_id: str,
    month: str,
    taxonomy_sha256: str,
    config_sha256: str,
    implementation_sha256: str,
) -> c.PrivateDerivedRecord:
    """Use the actual WP02 generation-validating port, without retaining source text."""
    if state.lookup_source(item_id, lease=lease) is None:
        raise ValueError("rules require a registered private source")
    record = c.PrivateDerivedRecord(
        schema_version=1,
        item_id=item_id,
        month=month,
        input_sha256=envelope.input_sha256,
        taxonomy_sha256=taxonomy_sha256,
        config_sha256=config_sha256,
        implementation_sha256=implementation_sha256,
        method="rules",
        model_sha256=None,
        provenance=c.LabelProvenance(source="unprovided", actor_ref=None, attestation_sha256=None),
        classification=classify(envelope),
    )
    state.write_record(record, lease=lease)
    return record
