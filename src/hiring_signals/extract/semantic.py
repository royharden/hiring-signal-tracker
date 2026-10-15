"""Own domain mappings shared by typed/generative extraction, with no execution.

Whole-source review coordinates are explicit; they are not localized evidence
accuracy. The narrow existing salary grammar supplies at most one candidate.
Missing/failed model fields never fall back to a fabricated deterministic label.
"""

from itertools import combinations
from typing import Annotated, Literal

from pydantic import Field

from hiring_signals import contracts as c
from hiring_signals.adapters.screen import POLICY, ScreenGate
from hiring_signals.extract.rules import classify
from hiring_signals.shared.screen import PreparedText, UntrustedText, prepare_text
from hiring_signals.shared.screen.prepare import wrap_untrusted

LEVELS = ("junior", "mid", "senior", "staff_or_lead")
MULTIPLE = {
    "multiple_" + "__".join(levels): levels
    for size in (2, 3, 4)
    for levels in combinations(LEVELS, size)
}
TAIL = ("not_stated", "conflicting", "uncertain")
BOOLEAN_OPTIONS = ("requested", "excluded", *TAIL)


class DecisionPolicy(c.ClosedModel):
    high_probability: Annotated[float, Field(gt=0.5, le=1, allow_inf_nan=False)]
    provenance: Literal["synthetic_control", "dev_calibrated"]
    evidence_ref: c.Digest


class SemanticInput:
    __slots__ = ("_source", "_gate", "_generation", "_salary", "_reference", "_wrapped")

    def __init__(self, source: c.TransientInput, *, gate: ScreenGate, generation: str):
        if not gate.permits(source, generation=generation):
            raise ValueError("semantic_input_screen_hold_or_stale")
        self._source = c.TransientInput(input_sha256=source.input_sha256, text=source.text)
        self._gate, self._generation = gate, generation
        self._reference = c.CandidateReference(
            input_sha256=source.input_sha256, start_byte=0, end_byte=len(source.text.encode())
        )
        baseline = classify(self._source)
        self._salary = baseline.salary if baseline.salary.presence.value is True else None
        prepared = prepare_text(UntrustedText(gate.item_id, generation, self._source.text), POLICY)
        if not isinstance(prepared, PreparedText):
            raise ValueError("semantic_input_preparation_unavailable")
        self._wrapped = wrap_untrusted(prepared)

    def __repr__(self):
        return "SemanticInput(<transient text omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("semantic_input_serialization_forbidden")

    def check(self):
        if not self._gate.permits(self._source, generation=self._generation):
            raise ValueError("semantic_input_source_changed")

    @property
    def input_sha256(self):
        return self._source.input_sha256

    @property
    def item_id(self):
        return self._gate.item_id

    @property
    def generation(self):
        return self._generation

    def state(self):
        self.check()
        salary = self._salary
        candidates = (
            []
            if salary is None
            else [
                {
                    "candidate_id": "candidate_0",
                    "minimum": str(salary.stated_minimum),
                    "maximum": str(salary.stated_maximum),
                    "currency": salary.currency,
                    "period": salary.period,
                }
            ]
        )
        return {**dict(self._wrapped.state), "salary_candidates": candidates}

    def options(self, field):
        if field == "seniority":
            return (*LEVELS, *MULTIPLE, *TAIL)
        if field == "work_mode":
            return ("remote", "hybrid", "onsite", *TAIL)
        if field == "employment":
            return ("full_time", "part_time", "contract", "internship", *TAIL)
        if field == "salary":
            return (*(("candidate_0",) if self._salary is not None else ()), "none", *TAIL)
        return BOOLEAN_OPTIONS

    def judgment(self, field, label, *, certainty=None):
        self.check()
        if field not in c.FIELD_IDS or label not in self.options(field):
            raise ValueError("invalid_semantic_domain_label")
        salary = field == "salary"
        boolean = field.startswith("skills.") or field in {
            "ai_engineering_role",
            "portfolio_requested",
            "location_stated",
            "salary",
        }
        selected = (
            "requested" if label == "candidate_0" else "excluded" if label == "none" else label
        )
        abstained = selected in {"conflicting", "uncertain"}
        absent = selected == "not_stated"
        multiple = field == "seniority" and selected in MULTIPLE
        evidence = (
            selected
            if abstained
            else "absent"
            if absent
            else "multiple"
            if multiple
            else "explicit_negative"
            if selected == "excluded"
            else "explicit_positive"
        )
        kwargs = dict(
            evidence_state=evidence,
            process_status="abstained" if abstained else "ok",
            certainty=None if abstained else certainty,
            candidates=() if absent else (self._reference,),
            error_code=None,
        )
        if boolean:
            value = True if selected == "requested" else False if selected == "excluded" else None
            result = c.BooleanJudgment(value=value, **kwargs)
            if not salary:
                return result
            if value is True:
                return c.SalaryJudgment(**{**self._salary.model_dump(), "presence": result})
            return c.SalaryJudgment(
                presence=result,
                stated_minimum=None,
                stated_maximum=None,
                currency=None,
                period=None,
                normalized=None,
                normalization_status="abstained" if abstained else "not_applicable",
            )
        value = None if abstained else "multiple" if multiple else selected
        if field == "seniority":
            return c.SeniorityJudgment(
                value=value, levels=MULTIPLE[selected] if multiple else (), **kwargs
            )
        model = c.WorkModeJudgment if field == "work_mode" else c.EmploymentJudgment
        return model(value=value, **kwargs)


def failed_field(field, *, code="provider_error", blocked=False):
    common = dict(
        evidence_state="unavailable",
        process_status="blocked" if blocked else "error",
        certainty=None,
        candidates=(),
        error_code="screen_hold" if blocked else code,
    )
    if field.startswith("skills.") or field in {
        "ai_engineering_role",
        "portfolio_requested",
        "location_stated",
    }:
        return c.BooleanJudgment(value=None, **common)
    if field == "salary":
        return c.SalaryJudgment(
            presence=c.BooleanJudgment(value=None, **common),
            stated_minimum=None,
            stated_maximum=None,
            currency=None,
            period=None,
            normalized=None,
            normalization_status="blocked" if blocked else "error",
        )
    model = {
        "seniority": c.SeniorityJudgment,
        "work_mode": c.WorkModeJudgment,
        "employment": c.EmploymentJudgment,
    }[field]
    return model(value=None, **({"levels": ()} if field == "seniority" else {}), **common)


def assemble(fields):
    if set(fields) != set(c.FIELD_IDS):
        raise ValueError("all37_semantic_fields_required")
    return c.Classification(
        **{field: fields[field] for field in c.FIELD_IDS if not field.startswith("skills.")},
        skills=c.SkillJudgments(**{skill: fields["skills." + skill] for skill in c.SKILL_IDS}),
    )


def failure(*, code="provider_error", blocked=False):
    return assemble(
        {field: failed_field(field, code=code, blocked=blocked) for field in c.FIELD_IDS}
    )
