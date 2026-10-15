"""App-owned safe drafts/commands, not a duplicate canonical rulings envelope/store."""

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from hiring_signals import contracts as c

FieldID = Annotated[
    str, Field(min_length=1, max_length=48, json_schema_extra={"enum": list(c.FIELD_IDS)})
]
ScalarValue = (
    bool
    | Literal[
        "junior",
        "mid",
        "senior",
        "staff_or_lead",
        "remote",
        "hybrid",
        "onsite",
        "full_time",
        "part_time",
        "contract",
        "internship",
        "not_stated",
        "none",
    ]
)


class SalaryValue(c.ClosedModel):
    minimum: c.Amount
    maximum: c.Amount
    currency: c.Currency | None
    period: c.Period | None

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.maximum < self.minimum:
            raise ValueError("salary reference ordering")
        return self


class MultipleLevels(c.ClosedModel):
    category: Literal["multiple"]
    levels: Annotated[tuple[c.Level, ...], Field(min_length=2, max_length=4)]

    @model_validator(mode="after")
    def distinct(self) -> Self:
        if len(set(self.levels)) != len(self.levels):
            raise ValueError("duplicate levels")
        return self


class FieldDecision(c.ClosedModel):
    field_id: FieldID
    presence: Literal["present", "absent", "unlabelled"]
    value: ScalarValue | SalaryValue | MultipleLevels | None
    evidence: Annotated[tuple[c.CandidateReference, ...], Field(max_length=8)]

    @model_validator(mode="after")
    def domain_value(self) -> Self:
        if self.field_id not in c.FIELD_IDS:
            raise ValueError("unknown field")
        if self.presence != "present":
            if self.value is not None or self.evidence:
                raise ValueError("absent/unlabelled must remain null")
            return self
        if not self.evidence:
            raise ValueError("present label needs reviewed source coordinates")
        if self.field_id.startswith("skills.") or self.field_id in {
            "ai_engineering_role",
            "portfolio_requested",
            "location_stated",
        }:
            valid = type(self.value) is bool or self.value == "not_stated"
        elif self.field_id == "seniority":
            valid = isinstance(self.value, MultipleLevels) or (
                isinstance(self.value, str)
                and self.value in {"junior", "mid", "senior", "staff_or_lead", "not_stated"}
            )
        elif self.field_id == "work_mode":
            valid = isinstance(self.value, str) and self.value in {
                "remote",
                "hybrid",
                "onsite",
                "not_stated",
            }
        elif self.field_id == "employment":
            valid = isinstance(self.value, str) and self.value in {
                "full_time",
                "part_time",
                "contract",
                "internship",
                "not_stated",
            }
        else:
            valid = isinstance(self.value, SalaryValue) or self.value == "none"
        if not valid:
            raise ValueError("label does not match domain field")
        return self


class SourcePin(c.ClosedModel):
    item_id: c.Digest
    raw_source_sha256: c.Digest
    input_sha256: c.Digest
    evidence_revision_sha256: c.Digest
    taxonomy_sha256: c.Digest
    rubric_sha256: c.Digest


class Actor(c.ClosedModel):
    origin: Literal["agent_provisional", "human_self_attested"]
    actor_ref: c.Digest
    attestation_ref: c.Digest | None

    @model_validator(mode="after")
    def attribution(self) -> Self:
        if (self.origin == "human_self_attested") != (self.attestation_ref is not None):
            raise ValueError("human self-attestation reference mismatch")
        return self


class MachinePrefill(c.ClosedModel):
    source: SourcePin
    prediction: c.PrivateDerivedRecord

    @model_validator(mode="after")
    def machine_source(self) -> Self:
        record = self.prediction
        if record.method == "human" or record.provenance.source != "unprovided":
            raise ValueError(
                "prefill must be raw machine output, not reference/effective human labels"
            )
        if (record.item_id, record.input_sha256, record.taxonomy_sha256) != (
            self.source.item_id,
            self.source.input_sha256,
            self.source.taxonomy_sha256,
        ):
            raise ValueError("prefill source/taxonomy mismatch")
        return self


class BlindRepeat(c.ClosedModel):
    item_id: c.Digest
    actor_ref: c.Digest
    first_event_ref: c.Digest
    first_at_utc: datetime
    origin: Literal["human_self_attested", "synthetic_control"]

    @model_validator(mode="after")
    def time(self) -> Self:
        if self.first_at_utc.tzinfo is None or self.first_at_utc.utcoffset() != timedelta(0):
            raise ValueError("repeat reference needs UTC time")
        return self


class ScalarCommand(c.ClosedModel):
    """Neutral app intent; a published owner adapter must construct rulings/1."""

    schema_version: c.Version
    event_id: c.Digest
    namespace: Literal["hiring-signals"]
    source: SourcePin
    decision: FieldDecision
    action: Literal["correct", "confirm", "waive_absent", "reopen"]
    expected_prior_event_id: c.Digest | None
    prior_value: FieldDecision | None
    assisted: bool
    actor: Actor
    at_utc: datetime
    reason: Literal[
        "manual_correction", "explicit_confirmation", "absence_confirmation", "reopened"
    ]

    @model_validator(mode="after")
    def intent(self) -> Self:
        if self.at_utc.tzinfo is None or self.at_utc.utcoffset() != timedelta(0):
            raise ValueError("UTC event time required")
        if self.action == "reopen":
            if self.decision.presence != "unlabelled":
                raise ValueError("reopen clears current label")
        elif self.decision.presence == "unlabelled":
            raise ValueError("unlabelled navigation is not a decision")
        if self.action == "waive_absent" and self.decision.presence != "absent":
            raise ValueError("absence confirmation must be explicit absent/null")
        return self


class PriorLabel(c.ClosedModel):
    event_id: c.Digest | None
    source: SourcePin | None
    effective: FieldDecision | None

    @model_validator(mode="after")
    def prior(self) -> Self:
        if self.effective is not None and (self.event_id is None or self.source is None):
            raise ValueError("effective prior needs source and head")
        return self


class AppendReceipt(c.ClosedModel):
    event_id: c.Digest
    status: Literal["accepted", "conflict", "unavailable", "unknown"]
    origin: Literal["test_staging", "owner_runtime"]
    sequence: Annotated[int, Field(gt=0)] | None
    durable: bool

    @model_validator(mode="after")
    def receipt_scope(self) -> Self:
        if self.status == "accepted" and self.origin == "owner_runtime":
            if not self.durable or self.sequence is None:
                raise ValueError("owner ack needs actual durable receipt")
        elif self.durable or self.sequence is not None:
            raise ValueError("mock/nonaccepted receipt cannot imply a durable append")
        return self


class SessionResult(c.ClosedModel):
    status: Literal[
        "incomplete",
        "dependency_unavailable",
        "partial",
        "conflict",
        "unknown",
        "staging_complete",
        "owner_receipts_complete",
        "cancelled",
        "skipped",
    ]
    confirmed_fields: Annotated[int, Field(ge=0, le=37)]
    accepted_receipts: Annotated[int, Field(ge=0, le=37)]
    durable_receipts: Annotated[int, Field(ge=0, le=37)]
    human_evidence_status: Literal["not_human", "requires_owner_validation"]
    human_gold_eligible: bool

    @model_validator(mode="after")
    def scope(self) -> Self:
        if (
            self.human_gold_eligible
            or not self.durable_receipts <= self.accepted_receipts <= self.confirmed_fields
        ):
            raise ValueError("session receipt is not human Gold authority")
        if self.status == "staging_complete" and (
            self.accepted_receipts != 37 or self.durable_receipts
        ):
            raise ValueError("staging completion requires all non-durable test receipts")
        if self.status == "owner_receipts_complete" and self.durable_receipts != 37:
            raise ValueError("owner receipt completion requires all durable receipts")
        return self


def schema_documents() -> dict[str, dict]:
    result = {}
    for name, model in (
        ("field-decision", FieldDecision),
        ("scalar-app-command", ScalarCommand),
        ("append-receipt", AppendReceipt),
        ("source-pin", SourcePin),
        ("blind-repeat", BlindRepeat),
        ("machine-prefill", MachinePrefill),
    ):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["x-runtime-validators-required"] = True
        result[name] = schema
    return result
