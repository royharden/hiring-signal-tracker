"""App-owned classification boundaries; no extraction, persistence or provider execution.

Validate untrusted JSON with model_validate_json before accepting a derived record.
JSON Schema describes shape; the runtime validators also enforce cross-field rules.
Private pseudonymous derived records are not anonymous or public posting exports.
"""

from decimal import Decimal
from hashlib import sha256
from typing import Annotated, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SKILL_IDS = (
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
    "c",
    "cpp",
    "sql",
    "pytorch",
    "tensorflow",
    "jax",
    "llm_apis",
    "agents",
    "rag",
    "evals",
    "fine_tuning",
    "mcp",
    "vector_db",
    "prompt_engineering",
    "mlops",
    "data_pipelines",
    "kubernetes",
    "aws",
    "gcp",
    "react",
    "node",
    "postgres",
    "distributed_systems",
    "security",
)
FIELD_IDS = (
    "ai_engineering_role",
    "portfolio_requested",
    "seniority",
    "work_mode",
    "employment",
    *(f"skills.{skill}" for skill in SKILL_IDS),
    "salary",
    "location_stated",
)
MAX_INPUT_BYTES = 32768
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Month = Annotated[str, Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]
Version = Annotated[int, Field(ge=1, le=1)]
Evidence = Literal[
    "absent",
    "explicit_positive",
    "explicit_negative",
    "multiple",
    "conflicting",
    "uncertain",
    "unavailable",
]
Process = Literal["ok", "abstained", "error", "blocked"]
ErrorCode = Literal["provider_error", "invalid_output", "candidate_missing", "screen_hold"]
Currency = Literal["USD", "EUR", "GBP", "CAD", "AUD", "JPY", "CHF", "INR"]
Period = Literal["hour", "day", "week", "month", "year"]
Amount = Annotated[Decimal, Field(gt=0, allow_inf_nan=False, max_digits=16, decimal_places=4)]
Level = Literal["junior", "mid", "senior", "staff_or_lead"]
Method = Literal["rules", "jev", "generative", "dev_majority", "human"]


class ClosedModel(BaseModel):
    """Reject undeclared fields and scalar coercion at every nested boundary."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
        revalidate_instances="always",
    )


class CandidateReference(ClosedModel):
    """Coordinates only, never snippets, names, URLs or source identifiers.

    Byte coordinates refer to a transient input with this digest. This validates
    shape and bounds, not candidate recall or correspondence to actual input.
    """

    input_sha256: Digest
    start_byte: Annotated[int, Field(ge=0, lt=MAX_INPUT_BYTES)]
    end_byte: Annotated[int, Field(gt=0, le=MAX_INPUT_BYTES)]

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.end_byte <= self.start_byte:
            raise ValueError("candidate span must be nonempty and ordered")
        return self


class Certainty(ClosedModel):
    kind: Literal["native_probability", "self_reported_confidence"]
    value: Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class Judgment(ClosedModel):
    evidence_state: Evidence
    process_status: Process
    certainty: Certainty | None
    candidates: Annotated[tuple[CandidateReference, ...], Field(max_length=8)]
    error_code: ErrorCode | None

    @model_validator(mode="after")
    def process_evidence(self) -> Self:
        expected = {
            "ok": {"absent", "explicit_positive", "explicit_negative", "multiple"},
            "abstained": {"conflicting", "uncertain"},
            "error": {"unavailable"},
            "blocked": {"unavailable"},
        }
        if self.evidence_state not in expected[self.process_status]:
            raise ValueError("process/evidence mismatch")
        if self.process_status in {"error", "blocked"}:
            if self.error_code is None or self.certainty is not None or self.candidates:
                raise ValueError("failure needs a bounded code and no answer evidence")
            if (self.process_status == "blocked") != (self.error_code == "screen_hold"):
                raise ValueError("screen hold requires blocked status")
        elif self.error_code is not None:
            raise ValueError("successful or abstained judgment cannot carry an error code")
        if self.process_status == "abstained" and self.certainty is not None:
            raise ValueError("abstention cannot carry answer certainty")
        if self.evidence_state == "absent" and self.candidates:
            raise ValueError("absence cannot carry selected evidence")
        if self.evidence_state in {"explicit_positive", "explicit_negative", "multiple"}:
            if not self.candidates:
                raise ValueError("explicit evidence needs a safe candidate reference")
        return self


class BooleanJudgment(Judgment):
    """Absent is null/ok/absent; an explicit negative is false/ok/explicit_negative."""

    value: bool | None

    @model_validator(mode="after")
    def boolean_evidence(self) -> Self:
        expected = {"explicit_positive": True, "explicit_negative": False}
        if self.evidence_state == "multiple":
            raise ValueError("boolean judgment cannot be multiple")
        if self.value is not expected.get(self.evidence_state):
            raise ValueError("boolean value/evidence mismatch")
        return self


class CategoryJudgment(Judgment):
    value: (
        Literal[
            "junior",
            "mid",
            "senior",
            "staff_or_lead",
            "not_stated",
            "multiple",
            "remote",
            "hybrid",
            "onsite",
            "full_time",
            "part_time",
            "contract",
            "internship",
        ]
        | None
    )

    @model_validator(mode="after")
    def category_evidence(self) -> Self:
        value = self.value
        if self.process_status != "ok":
            if value is not None:
                raise ValueError("failed or abstained category must have null value")
        elif self.evidence_state == "absent":
            if value != "not_stated":
                raise ValueError("absent category must be not_stated")
        elif self.evidence_state == "explicit_positive":
            if value in {None, "not_stated", "multiple"}:
                raise ValueError("explicit category needs one stated class")
        elif self.evidence_state == "multiple":
            if value != "multiple":
                raise ValueError("multiple evidence needs multiple class")
        else:
            raise ValueError("unsupported categorical evidence")
        return self


class SeniorityJudgment(CategoryJudgment):
    value: Literal["junior", "mid", "senior", "staff_or_lead", "not_stated", "multiple"] | None
    levels: Annotated[tuple[Level, ...], Field(max_length=4)]

    @model_validator(mode="after")
    def multiple_levels(self) -> Self:
        if len(set(self.levels)) != len(self.levels):
            raise ValueError("duplicate seniority levels")
        if self.value == "multiple":
            if len(self.levels) < 2:
                raise ValueError("multiple seniority needs at least two distinct levels")
        elif self.levels:
            raise ValueError("only multiple seniority carries multiple levels")
        return self


class WorkModeJudgment(CategoryJudgment):
    value: Literal["remote", "hybrid", "onsite", "not_stated"] | None


class EmploymentJudgment(CategoryJudgment):
    value: Literal["full_time", "part_time", "contract", "internship", "not_stated"] | None


class SkillJudgments(ClosedModel):
    """Thirty separately required judgments; no omitted skill defaults."""

    python: BooleanJudgment
    javascript: BooleanJudgment
    typescript: BooleanJudgment
    go: BooleanJudgment
    rust: BooleanJudgment
    java: BooleanJudgment
    c: BooleanJudgment
    cpp: BooleanJudgment
    sql: BooleanJudgment
    pytorch: BooleanJudgment
    tensorflow: BooleanJudgment
    jax: BooleanJudgment
    llm_apis: BooleanJudgment
    agents: BooleanJudgment
    rag: BooleanJudgment
    evals: BooleanJudgment
    fine_tuning: BooleanJudgment
    mcp: BooleanJudgment
    vector_db: BooleanJudgment
    prompt_engineering: BooleanJudgment
    mlops: BooleanJudgment
    data_pipelines: BooleanJudgment
    kubernetes: BooleanJudgment
    aws: BooleanJudgment
    gcp: BooleanJudgment
    react: BooleanJudgment
    node: BooleanJudgment
    postgres: BooleanJudgment
    distributed_systems: BooleanJudgment
    security: BooleanJudgment


class NormalizedSalary(ClosedModel):
    """Unit-preserving decimal range; no annual conversion or inferred units."""

    minimum: Amount
    maximum: Amount
    currency: Currency
    period: Period

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.maximum < self.minimum:
            raise ValueError("salary range must be ordered")
        return self


class SalaryJudgment(ClosedModel):
    presence: BooleanJudgment
    stated_minimum: Amount | None
    stated_maximum: Amount | None
    currency: Currency | None
    period: Period | None
    normalization_status: Literal["ok", "abstained", "not_applicable", "error", "blocked"]
    normalized: NormalizedSalary | None

    @model_validator(mode="after")
    def stated_and_normalized(self) -> Self:
        stated = (self.stated_minimum, self.stated_maximum, self.currency, self.period)
        if self.presence.value is not True:
            if any(value is not None for value in stated) or self.normalized is not None:
                raise ValueError("unstated salary cannot contain amounts or units")
            expected = {
                "ok": "not_applicable",
                "abstained": "abstained",
                "error": "error",
                "blocked": "blocked",
            }[self.presence.process_status]
            if self.normalization_status != expected:
                raise ValueError("salary process/normalization mismatch")
            return self
        if self.stated_minimum is None or self.stated_maximum is None:
            raise ValueError("stated salary needs both decimal range endpoints")
        if self.stated_maximum < self.stated_minimum:
            raise ValueError("stated salary range must be ordered")
        if self.currency is None or self.period is None:
            if self.normalization_status != "abstained" or self.normalized is not None:
                raise ValueError("unknown salary units require normalization abstention")
        else:
            if self.normalization_status != "ok" or self.normalized is None:
                raise ValueError("explicit salary units need a unit-preserving normalized range")
            observed = (
                self.normalized.minimum,
                self.normalized.maximum,
                self.normalized.currency,
                self.normalized.period,
            )
            if observed != stated:
                raise ValueError("normalized salary cannot fabricate amounts or units")
        return self


class Classification(ClosedModel):
    ai_engineering_role: BooleanJudgment
    portfolio_requested: BooleanJudgment
    seniority: SeniorityJudgment
    work_mode: WorkModeJudgment
    employment: EmploymentJudgment
    skills: SkillJudgments
    salary: SalaryJudgment
    location_stated: BooleanJudgment

    def judgments(self) -> tuple[Judgment, ...]:
        return (
            self.ai_engineering_role,
            self.portfolio_requested,
            self.seniority,
            self.work_mode,
            self.employment,
            *(getattr(self.skills, skill) for skill in SKILL_IDS),
            self.salary.presence,
            self.location_stated,
        )


class LabelProvenance(ClosedModel):
    """Self-attested human provenance is not authentication or supplied human gold."""

    source: Literal["unprovided", "synthetic_expectation", "human_self_attested"]
    actor_ref: Digest | None
    attestation_sha256: Digest | None

    @model_validator(mode="after")
    def provenance(self) -> Self:
        provided = self.actor_ref is not None and self.attestation_sha256 is not None
        if self.source == "human_self_attested":
            if not provided:
                raise ValueError("human provenance needs actor and attestation references")
        elif self.actor_ref is not None or self.attestation_sha256 is not None:
            raise ValueError("nonhuman provenance cannot imply a human actor")
        return self


class PrivateDerivedRecord(ClosedModel):
    """Closed private derivation; neither raw text nor a public per-item output type.

    ID generation, source mapping, storage and aggregate privacy are unimplemented.
    Digest syntax does not prove HMAC generation or authentication.
    """

    schema_version: Version
    item_id: Digest
    month: Month
    input_sha256: Digest
    taxonomy_sha256: Digest
    config_sha256: Digest
    implementation_sha256: Digest
    method: Method
    model_sha256: Digest | None
    provenance: LabelProvenance
    classification: Classification

    @model_validator(mode="after")
    def references_and_method(self) -> Self:
        model_method = self.method in {"jev", "generative"}
        if model_method != (self.model_sha256 is not None):
            raise ValueError("model version reference required only for semantic methods")
        if (self.method == "human") != (self.provenance.source == "human_self_attested"):
            raise ValueError("human method and human provenance must agree")
        for judgment in self.classification.judgments():
            if any(ref.input_sha256 != self.input_sha256 for ref in judgment.candidates):
                raise ValueError("candidate input digest differs from record input")
            if judgment.certainty is not None:
                expected = {"jev": "native_probability", "generative": "self_reported_confidence"}
                if judgment.certainty.kind != expected.get(self.method):
                    raise ValueError("certainty kind does not match method")
        return self


class TaxonomyConfig(ClosedModel):
    """Inventory only; not a dictionary or a ratified labeling rubric."""

    schema_version: Version
    taxonomy_version: Literal["taxonomy-v1"]
    ratification_status: Literal["pending"]
    skills: Annotated[
        tuple[str, ...], Field(min_length=30, max_length=30, json_schema_extra={"const": SKILL_IDS})
    ]

    @model_validator(mode="after")
    def complete_inventory(self) -> Self:
        if self.skills != SKILL_IDS:
            raise ValueError("taxonomy must preserve the exact ordered thirty-skill inventory")
        return self


class ExperimentConfig(ClosedModel):
    schema_version: Version
    taxonomy_version: Literal["taxonomy-v1"]
    field_ids: Annotated[
        tuple[str, ...], Field(min_length=37, max_length=37, json_schema_extra={"const": FIELD_IDS})
    ]
    methods: tuple[Literal["rules", "jev", "generative", "dev_majority"], ...]
    split_seed: Annotated[int, Field(ge=20261014, le=20261014)]
    human_labels: Literal["unprovided"]
    evaluation_status: Literal["not_implemented"]
    provider_execution: Literal["disabled"]

    @model_validator(mode="after")
    def complete_inventory(self) -> Self:
        if self.field_ids != FIELD_IDS:
            raise ValueError("experiment must preserve all thirty-seven field IDs")
        if self.methods != ("rules", "jev", "generative", "dev_majority"):
            raise ValueError("experiment method inventory must remain complete")
        return self


class TransientInput:
    """Deliberately not a dataclass/model; no dict, JSON or pickle serialization.

    This is an in-memory input boundary, not enforced process isolation or erasure.
    The text attribute is intentionally accessible to future authorized extractors.
    """

    __slots__ = ("input_sha256", "text")

    def __init__(self, *, input_sha256: str, text: str):
        # Validate safe metadata without accepting raw text into a serializable model.
        CandidateReference(input_sha256=input_sha256, start_byte=0, end_byte=1)
        if not isinstance(text, str) or not text or len(text.encode("utf-8")) > MAX_INPUT_BYTES:
            raise ValueError("transient input must be nonempty UTF-8 within the byte limit")
        if sha256(text.encode("utf-8")).hexdigest() != input_sha256:
            raise ValueError("transient text digest mismatch")
        self.input_sha256 = input_sha256
        self.text = text

    def __repr__(self) -> str:
        return "TransientInput(<transient text omitted>)"

    def __reduce_ex__(self, protocol: int):
        raise TypeError("transient input serialization forbidden")


class ClassifierProposal(Protocol):
    """Own domain signature only; not a driver, provider or shipped implementation."""

    def classify(self, envelope: TransientInput) -> Classification: ...


SCHEMA_MODELS = {
    "classification": Classification,
    "private-derived-record": PrivateDerivedRecord,
    "taxonomy": TaxonomyConfig,
    "experiment": ExperimentConfig,
}


def schema_documents() -> dict[str, dict]:
    """Deterministic model closure, including a runtime-validation caveat."""
    result = {}
    for name, model in SCHEMA_MODELS.items():
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["x-runtime-validators-required"] = True
        result[name] = schema
    return result
