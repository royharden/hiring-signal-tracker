"""Transient app annotation/session logic and a neutral injected submit port.

No generic journal, replay reducer, database, source acquisition or provider is
implemented here. Actual S2 adapters must perform atomic generation/CAS/fsync.
"""

import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from pydantic import ValidationError

from hiring_signals import contracts as c

from .models import (
    Actor,
    AppendReceipt,
    BlindRepeat,
    FieldDecision,
    MachinePrefill,
    MultipleLevels,
    PriorLabel,
    SalaryValue,
    ScalarCommand,
    SessionResult,
    SourcePin,
)


def decision_from_choice(field_id: str, choice: str, source: c.TransientInput) -> FieldDecision:
    """Compact choices only; rejected values/source text are never echoed."""
    try:
        if not isinstance(choice, str) or len(choice) > 256:
            raise ValueError()
        choice = choice.strip()
        if choice in {"a", "?"}:
            return FieldDecision(
                field_id=field_id,
                presence="absent" if choice == "a" else "unlabelled",
                value=None,
                evidence=(),
            )
        value = {"y": True, "n": False, "u": "not_stated"}.get(choice, choice)
        if field_id == "salary" and choice != "none":
            currency, minimum, maximum, period = choice.split()
            value = SalaryValue(
                minimum=Decimal(minimum),
                maximum=Decimal(maximum),
                currency=None if currency == "unknown" else currency,
                period=None if period == "unknown" else period,
            )
        elif field_id == "seniority" and choice.startswith("multiple:"):
            value = MultipleLevels(
                category="multiple", levels=tuple(choice.split(":", 1)[1].split(","))
            )
        # A whole-source review range is explicit, not a claim of localized extraction accuracy.
        evidence = (
            c.CandidateReference(
                input_sha256=source.input_sha256, start_byte=0, end_byte=len(source.text.encode())
            ),
        )
        return FieldDecision(field_id=field_id, presence="present", value=value, evidence=evidence)
    except (ValueError, TypeError, ValidationError, InvalidOperation):
        raise ValueError("invalid_label_choice") from None


class AnnotationSession:
    __slots__ = (
        "_source",
        "_pin",
        "_actor",
        "_split",
        "_lookup",
        "_head",
        "_submit",
        "_clock",
        "_labels",
        "_assisted",
        "_commands",
        "_receipts",
        "_closed",
        "_last",
        "_prefill",
    )

    def __init__(
        self,
        *,
        source: c.TransientInput,
        pin: SourcePin,
        actor: Actor,
        split: str,
        current_source: Callable[[], SourcePin],
        head: Callable[[str], PriorLabel],
        submit: Callable[[ScalarCommand], AppendReceipt] | None,
        prefill: MachinePrefill | None = None,
        repeat: BlindRepeat | None = None,
        utc_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if split not in {"dev", "heldout", "blind_repeat"}:
            raise ValueError("invalid_annotation_split")
        if split != "dev" and prefill is not None:
            raise ValueError("blind_annotation_forbids_prefill")
        try:
            pin = SourcePin.model_validate(pin)
            actor = Actor.model_validate(actor)
        except (ValidationError, TypeError):
            raise ValueError("invalid_annotation_context") from None
        if not isinstance(source, c.TransientInput):
            raise ValueError("annotation_requires_transient_source")
        if split == "blind_repeat":
            if repeat is None:
                raise ValueError("blind_repeat_requires_prior_timing")
            repeat = BlindRepeat.model_validate(repeat)
            if repeat.item_id != pin.item_id or repeat.actor_ref != actor.actor_ref:
                raise ValueError("blind_repeat_item_or_actor_mismatch")
            now = utc_clock()
            if (
                now.tzinfo is None
                or now.utcoffset() != timedelta(0)
                or now - repeat.first_at_utc < timedelta(days=7)
            ):
                raise ValueError("blind_repeat_requires_seven_days")
            if actor.origin == "human_self_attested" and repeat.origin != "human_self_attested":
                raise ValueError("blind_repeat_requires_human_prior_provenance")
        self._source = c.TransientInput(input_sha256=source.input_sha256, text=source.text)
        self._pin = SourcePin.model_validate(pin)
        self._actor = Actor.model_validate(actor)
        if pin.input_sha256 != source.input_sha256:
            raise ValueError("annotation_source_digest_mismatch")
        self._split, self._lookup, self._head, self._submit, self._clock = (
            split,
            current_source,
            head,
            submit,
            utc_clock,
        )
        self._labels = {}
        self._assisted = {}
        self._commands = {}
        self._receipts = {}
        self._closed = False
        self._last = None
        self._check()
        # A dev prefill is only a suggestion source, never an implicitly confirmed label.
        bound = MachinePrefill.model_validate(prefill) if prefill is not None else None
        if bound is not None and bound.source != self._pin:
            raise ValueError("prefill_source_generation_mismatch")
        self._prefill = bound.prediction.classification if bound is not None else None

    def __repr__(self):
        return "AnnotationSession(<transient source and draft omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("transient annotation serialization forbidden")

    def _check(self):
        if self._closed:
            raise ValueError("annotation_session_closed")
        try:
            current = SourcePin.model_validate(self._lookup())
            valid = (
                current == self._pin
                and hashlib.sha256(self._source.text.encode()).hexdigest() == self._pin.input_sha256
            )
        except Exception:
            self.cancel()
            raise ValueError("annotation_source_unavailable") from None
        if not valid:
            self.cancel()
            raise ValueError("annotation_source_generation_changed")

    def transient_view(self) -> c.TransientInput:
        """Memory-only view; keyboard output deliberately never prints this text."""
        self._check()
        return self._source

    def set_decision(self, decision: FieldDecision, *, assisted: bool = False):
        self._check()
        try:
            decision = FieldDecision.model_validate(decision)
        except ValidationError:
            raise ValueError("invalid_annotation_decision") from None
        if type(assisted) is not bool or (assisted and self._split != "dev"):
            raise ValueError("blind_annotation_forbids_assistance")
        if decision.field_id in self._commands:
            raise ValueError("submitted_intent_requires_retry_or_explicit_reopen")
        for reference in decision.evidence:
            if reference.input_sha256 != self._pin.input_sha256 or reference.end_byte > len(
                self._source.text.encode()
            ):
                raise ValueError("annotation_evidence_source_mismatch")
        self._labels[decision.field_id] = decision
        self._assisted[decision.field_id] = assisted

    def choose(self, field_id: str, choice: str):
        self._check()
        self.set_decision(decision_from_choice(field_id, choice, self._source))

    def suggestion(self, field_id: str) -> FieldDecision | None:
        self._check()
        if self._split != "dev" or self._prefill is None:
            return None
        if field_id not in c.FIELD_IDS:
            raise ValueError("unknown_annotation_field")
        if field_id.startswith("skills."):
            judgment = getattr(self._prefill.skills, field_id.split(".")[1])
        elif field_id == "salary":
            judgment = self._prefill.salary.presence
        else:
            judgment = getattr(self._prefill, field_id)
        if judgment.process_status != "ok":
            return None
        if judgment.evidence_state == "absent":
            return FieldDecision(field_id=field_id, presence="absent", value=None, evidence=())
        value = judgment.value
        if field_id == "salary":
            salary = self._prefill.salary
            value = (
                SalaryValue(
                    minimum=salary.stated_minimum,
                    maximum=salary.stated_maximum,
                    currency=salary.currency,
                    period=salary.period,
                )
                if value is True
                else "none"
            )
        elif field_id == "seniority" and value == "multiple":
            value = MultipleLevels(category="multiple", levels=judgment.levels)
        return FieldDecision(
            field_id=field_id, presence="present", value=value, evidence=judgment.candidates
        )

    def confirm_suggestion(self, field_id: str):
        suggestion = self.suggestion(field_id)
        if suggestion is None:
            raise ValueError("no_eligible_dev_suggestion")
        self.set_decision(suggestion, assisted=True)

    def _result(self, status):
        confirmed = sum(label.presence != "unlabelled" for label in self._labels.values())
        accepted = sum(receipt.status == "accepted" for receipt in self._receipts.values())
        durable = sum(receipt.durable for receipt in self._receipts.values())
        return SessionResult(
            status=status,
            confirmed_fields=confirmed,
            accepted_receipts=accepted,
            durable_receipts=durable,
            human_gold_eligible=False,
            human_evidence_status="not_human"
            if self._actor.origin == "agent_provisional"
            else "requires_owner_validation",
        )

    def _intent(self, field_id, *, reopen=False):
        if field_id in self._commands:
            cached = self._commands[field_id]
            if not reopen or cached.action == "reopen":
                return cached
            prior_receipt = self._receipts.get(field_id)
            if prior_receipt is None or prior_receipt.status != "accepted":
                raise ValueError("pending_intent_requires_resolution")
        try:
            prior = PriorLabel.model_validate(self._head(field_id))
        except Exception:
            raise ValueError("annotation_prior_head_unavailable") from None
        if prior.effective is not None and prior.effective.field_id != field_id:
            raise ValueError("annotation_prior_subject_mismatch")
        value = (
            FieldDecision(field_id=field_id, presence="unlabelled", value=None, evidence=())
            if reopen
            else self._labels[field_id]
        )
        effective = prior.effective if prior.source == self._pin else None
        action = (
            "reopen"
            if reopen
            else "waive_absent"
            if value.presence == "absent"
            else "correct"
            if effective is not None and effective != value
            else "confirm"
        )
        reason = {
            "reopen": "reopened",
            "waive_absent": "absence_confirmation",
            "confirm": "explicit_confirmation",
            "correct": "manual_correction",
        }[action]
        command = ScalarCommand(
            schema_version=1,
            event_id=secrets.token_hex(32),
            namespace="hiring-signals",
            source=self._pin,
            decision=value,
            action=action,
            expected_prior_event_id=prior.event_id,
            prior_value=effective,
            assisted=False if reopen else self._assisted[field_id],
            actor=self._actor,
            at_utc=self._clock(),
            reason=reason,
        )
        self._commands[field_id] = command
        return command

    def _send(self, command):
        self._check()
        try:
            receipt = AppendReceipt.model_validate(self._submit(command))
        except Exception:
            return "unknown"
        if receipt.event_id != command.event_id:
            return "unknown"
        self._receipts[command.decision.field_id] = receipt
        return receipt.status

    def submit(self) -> SessionResult:
        if self._closed:
            return self._last
        self._check()
        if any(
            field not in self._labels or self._labels[field].presence == "unlabelled"
            for field in c.FIELD_IDS
        ):
            return self._result("incomplete")
        if self._submit is None:
            return self._result("dependency_unavailable")
        for field in c.FIELD_IDS:
            if field in self._commands and self._commands[field].action == "reopen":
                return self._result("unknown")
            if field in self._receipts and self._receipts[field].status == "accepted":
                continue
            status = self._send(self._intent(field))
            if status != "accepted":
                return self._result(
                    "conflict"
                    if status == "conflict"
                    else "unknown"
                    if status == "unknown"
                    else "partial"
                    if any(receipt.status == "accepted" for receipt in self._receipts.values())
                    else "dependency_unavailable"
                )
        kinds = {receipt.origin for receipt in self._receipts.values()}
        if len(kinds) != 1:
            return self._result("partial")
        return self._result(
            "staging_complete" if kinds == {"test_staging"} else "owner_receipts_complete"
        )

    def reopen(self, field_id: str) -> SessionResult:
        self._check()
        if field_id not in c.FIELD_IDS:
            raise ValueError("unknown_annotation_field")
        if self._submit is None:
            return self._result("dependency_unavailable")
        command = self._intent(field_id, reopen=True)
        status = self._send(command)
        if status == "accepted":
            self._labels.pop(field_id, None)
            self._assisted.pop(field_id, None)
            self._receipts.pop(field_id, None)
            self._commands.pop(field_id, None)
            return self._result("incomplete")
        return self._result("conflict" if status == "conflict" else "unknown")

    def cancel(self, *, skipped=False) -> SessionResult:
        if self._closed:
            return self._last
        result = self._result("skipped" if skipped else "cancelled")
        self._source.text = ""
        self._labels.clear()
        self._commands.clear()
        self._receipts.clear()
        self._assisted.clear()
        self._prefill = None
        self._closed = True
        self._last = result
        return result


def run_keyboard(
    session: AnnotationSession, reader: Callable[[str], str], writer: Callable[[str], None]
) -> SessionResult:
    """Label prompts only; the source is viewed separately in memory/original file.

    y/n/u, a=explicit absence, ?=unlabelled; categorical IDs; salary four exact
    tokens. Skip/q never appends. No source/rejected choice is written to stdout.
    """
    try:
        for field in c.FIELD_IDS:
            suggestion = session.suggestion(field)
            if suggestion is not None:
                value = suggestion.value
                rendered = (
                    value.model_dump_json() if isinstance(value, c.ClosedModel) else str(value)
                )
                writer(f"dev_prefill_unconfirmed: {suggestion.presence}; {rendered}")
            while True:
                session._check()
                choice = reader(f"{field}: ")
                if choice == "q":
                    return session.cancel()
                if choice == "skip":
                    return session.cancel(skipped=True)
                try:
                    if choice == "=":
                        session.confirm_suggestion(field)
                    else:
                        session.choose(field, choice)
                except ValueError:
                    writer("invalid_label_choice")
                    continue
                if choice.strip() == "?":
                    writer("field_unlabelled_choose_or_skip")
                    continue
                break
        return session.submit()
    except (KeyboardInterrupt, EOFError):
        return session.cancel()
