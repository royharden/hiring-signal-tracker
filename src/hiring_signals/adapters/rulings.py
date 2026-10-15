"""S10 scalar mapping to the unchanged canonical S2 durable journal.

The in-process source authority stores only digests and byte lengths. Callers
must reinstall actually prepared current input after restart; no raw text is
retained. This is not a multi-process source discovery or human Gold service.
"""

import hashlib
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from hiring_signals import contracts as c
from hiring_signals.annotation.models import (
    AppendReceipt,
    FieldDecision,
    PriorLabel,
    ScalarCommand,
    SourcePin,
)
from hiring_signals.shared.rulings import models as m
from hiring_signals.shared.rulings.identity import canonical_bytes
from hiring_signals.shared.rulings.projection import export_labels
from hiring_signals.shared.rulings.store import (
    AppendUncertain,
    GenerationConflict,
    IntentConflict,
    JournalError,
    JournalReadOnly,
    JournalStore,
    PriorConflict,
    subject_key,
)

PROFILE = "hiring-signals/scalar/1"


def generation(pin: SourcePin) -> m.ScalarGeneration:
    return m.ScalarGeneration(
        kind="scalar",
        profile=PROFILE,
        source_sha256=pin.raw_source_sha256,
        raw_source_revision=pin.raw_source_sha256,
        evidence_revision=hashlib.sha256(canonical_bytes(pin.model_dump(mode="json"))).hexdigest(),
    )


@dataclass(frozen=True)
class SourceSnapshot:
    pin: SourcePin
    byte_length: int


class SourceAuthority:
    """Single-process current-source registry and mutation lock; not a durable source store."""

    def __init__(self):
        self._lock = threading.RLock()
        self._current = {}

    def install(self, pin: SourcePin, source: c.TransientInput):
        pin = SourcePin.model_validate(pin)
        if not isinstance(source, c.TransientInput) or (
            hashlib.sha256(source.text.encode()).hexdigest() != pin.input_sha256
            or source.input_sha256 != pin.input_sha256
        ):
            raise ValueError("current_source_digest_mismatch")
        with self._lock:
            self._current[pin.item_id] = SourceSnapshot(pin, len(source.text.encode()))

    def remove(self, item_id: str):
        with self._lock:
            self._current.pop(item_id, None)

    @contextmanager
    def guard(self, item_id: str):
        with self._lock:
            yield self._current.get(item_id)


def _subject(item_id, field_id):
    if field_id not in c.FIELD_IDS:
        raise ValueError("unknown_annotation_field")
    return m.ScalarSubject(kind="field", item_id=item_id, field_id=field_id)


def _value(label):
    return (
        label.model_dump(mode="json") if label is not None and label.presence == "present" else None
    )


def to_owner_intent(command: ScalarCommand) -> m.RulingIntent:
    command = ScalarCommand.model_validate(command)
    pin = command.source
    old, new = _value(command.prior_value), _value(command.decision)
    action = command.action
    # UI confirmation of a first label introduces a value. Canonical confirm must
    # preserve an existing exact value, so this first write is canonical correct.
    if action == "confirm" and old != new:
        action = "correct"
    refs = tuple(
        f"hst.{key}:{getattr(pin, key)}"
        for key in ("input_sha256", "evidence_revision_sha256", "taxonomy_sha256", "rubric_sha256")
    ) + (f"hst.assisted:{int(command.assisted)}",)
    return m.RulingIntent(
        event_id=command.event_id,
        namespace="hiring-signals",
        subject=_subject(pin.item_id, command.decision.field_id),
        generation_identity=generation(pin),
        event_kind="scalar_decision",
        payload=m.ScalarPayload(action=action, old_value=old, new_value=new, issue_dispositions=()),
        expected_source_revision=pin.raw_source_sha256,
        expected_evidence_revision=generation(pin).evidence_revision,
        expected_prior_event_id=command.expected_prior_event_id,
        actor_label=command.actor.actor_ref,
        actor_provenance="human"
        if command.actor.origin == "human_self_attested"
        else "agent_provisional",
        actor_provenance_ref=command.actor.attestation_ref,
        at_utc=command.at_utc.isoformat(),
        reason=command.reason,
        context_refs=refs,
    )


def _pin_from_event(event):
    if not isinstance(event.subject, m.ScalarSubject) or not isinstance(
        event.generation_identity, m.ScalarGeneration
    ):
        raise ValueError("unsupported_annotation_event")
    refs = {}
    for ref in event.context_refs:
        key, value = ref.split(":", 1)
        if key in refs:
            raise ValueError("duplicate_annotation_context")
        refs[key] = value
    pin = SourcePin(
        item_id=event.subject.item_id,
        raw_source_sha256=event.generation_identity.source_sha256,
        **{
            key: refs["hst." + key]
            for key in (
                "input_sha256",
                "evidence_revision_sha256",
                "taxonomy_sha256",
                "rubric_sha256",
            )
        },
    )
    if generation(pin) != event.generation_identity:
        raise ValueError("annotation_generation_binding_mismatch")
    return pin


class AnnotationJournal:
    """Actual private journal with the app's current source lock held through fsync.

    All source install/remove mutations in this process use the same authority.
    Receipt completion acknowledges recorded writes, never current approval or
    human evidence. append() retains the full canonical historical receipt.
    """

    def __init__(self, directory: Path, *, product_root: Path, sources: SourceAuthority):
        directory, product = Path(directory).absolute(), Path(product_root).resolve()
        resolved = directory.resolve(strict=True)
        if resolved.is_relative_to(product) or product.is_relative_to(resolved):
            raise ValueError("annotation_state_must_be_outside_product")
        if type(sources) is not SourceAuthority:
            raise ValueError("source_authority_required")
        self.store = JournalStore(directory)
        self.sources = sources

    def append(self, command: ScalarCommand) -> m.AppendReceipt:
        command = ScalarCommand.model_validate(command)
        intent = to_owner_intent(command)
        with self.sources.guard(command.source.item_id) as current:

            class Validator:
                def validate(self, subject, supplied_generation):
                    if (
                        current is None
                        or current.pin != command.source
                        or supplied_generation != generation(current.pin)
                        or subject != intent.subject
                    ):
                        raise GenerationConflict("current_annotation_source_changed")
                    for label in (command.decision, command.prior_value):
                        if label is None:
                            continue
                        if label.field_id != subject.field_id:
                            raise GenerationConflict("annotation_prior_field_mismatch")
                        if any(
                            ref.input_sha256 != current.pin.input_sha256
                            or ref.end_byte > current.byte_length
                            for ref in label.evidence
                        ):
                            raise GenerationConflict("annotation_evidence_source_mismatch")

            # Exact historical retries intentionally precede generation/head checks
            # in the canonical store; they never become present source authority.
            return self.store.append(intent, Validator())

    def submit(self, command: ScalarCommand) -> AppendReceipt:
        command = ScalarCommand.model_validate(command)
        try:
            receipt = self.append(command)
        except (PriorConflict, GenerationConflict, IntentConflict):
            status = "conflict"
        except AppendUncertain:
            status = "unknown"
        except JournalReadOnly:
            status = "unavailable"
        except (JournalError, OSError):
            status = "unavailable"
        else:
            return AppendReceipt(
                event_id=receipt.event_id,
                status="accepted",
                origin="owner_runtime",
                sequence=receipt.sequence,
                durable=True,
            )
        return AppendReceipt(
            event_id=command.event_id,
            status=status,
            origin="owner_runtime",
            sequence=None,
            durable=False,
        )

    def head(self, item_id: str, field_id: str) -> PriorLabel:
        subject = _subject(item_id, field_id)
        with self.sources.guard(item_id) as current:
            snapshot = self.store.replay()
            if not snapshot.can_append:
                raise ValueError("annotation_journal_requires_repair")
            head = snapshot.stable_head("hiring-signals", subject)
            if head is None:
                return PriorLabel(event_id=None, source=None, effective=None)
            key = subject_key("hiring-signals", subject)
            label = next(
                label
                for label in export_labels(
                    snapshot, {key: generation(current.pin) if current else None}
                )
                if label.head_event_id == head.event_id
            )
            decision = None
            if label.presence == "present":
                decision = FieldDecision.model_validate_json(canonical_bytes(label.value))
                if decision.field_id != field_id:
                    raise ValueError("annotation_projection_field_mismatch")
            elif label.presence == "absent":
                decision = FieldDecision(
                    field_id=field_id, presence="absent", value=None, evidence=()
                )
            return PriorLabel(
                event_id=head.event_id, source=_pin_from_event(head), effective=decision
            )
