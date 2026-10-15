"""Original one-source controller controls; no real labels, Gold or human agreement."""

import hashlib
import json
import pickle
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from hiring_signals import contracts as c
from hiring_signals.annotation.models import (
    Actor,
    AppendReceipt,
    BlindRepeat,
    MachinePrefill,
    PriorLabel,
    SessionResult,
    SourcePin,
    schema_documents,
)
from hiring_signals.annotation.session import AnnotationSession, decision_from_choice, run_keyboard
from hiring_signals.extract.rules import classify

TEXT = "ORIGINAL_TRANSIENT_SOURCE_CANARY with invented requirements."
SOURCE = c.TransientInput(input_sha256=hashlib.sha256(TEXT.encode()).hexdigest(), text=TEXT)
PIN = SourcePin(
    item_id="a" * 64,
    raw_source_sha256="b" * 64,
    input_sha256=SOURCE.input_sha256,
    evidence_revision_sha256="c" * 64,
    taxonomy_sha256="d" * 64,
    rubric_sha256="e" * 64,
)
ACTOR = Actor(origin="agent_provisional", actor_ref="f" * 64, attestation_ref=None)


class Staging:
    def __init__(self):
        self.calls = []
        self.heads = {}

    def head(self, field):
        return self.heads.get(field, PriorLabel(event_id=None, source=None, effective=None))

    def __call__(self, command):
        self.calls.append(command)
        self.heads[command.decision.field_id] = PriorLabel(
            event_id=command.event_id,
            source=command.source,
            effective=None if command.action == "reopen" else command.decision,
        )
        return AppendReceipt(
            event_id=command.event_id,
            status="accepted",
            origin="test_staging",
            sequence=None,
            durable=False,
        )


def session(backend=None, **changes):
    args = dict(
        source=SOURCE,
        pin=PIN,
        actor=ACTOR,
        split="dev",
        current_source=lambda: PIN,
        head=backend.head
        if backend
        else lambda field: PriorLabel(event_id=None, source=None, effective=None),
        submit=backend,
        utc_clock=lambda: datetime(2026, 10, 14, tzinfo=UTC),
    )
    if changes.get("split") == "blind_repeat" and "repeat" not in changes:
        args["repeat"] = BlindRepeat(
            item_id=PIN.item_id,
            actor_ref=ACTOR.actor_ref,
            first_event_ref="3" * 64,
            first_at_utc=datetime(2026, 10, 1, tzinfo=UTC),
            origin="synthetic_control",
        )
    args.update(changes)
    return AnnotationSession(**args)


def confirm_absent(s):
    # Explicit unit choices; no corpus/Gold generator or implicit controller default.
    for field in c.FIELD_IDS:
        s.choose(field, "a")


def machine_prefill():
    record = c.PrivateDerivedRecord(
        schema_version=1,
        item_id=PIN.item_id,
        month="2026-10",
        input_sha256=PIN.input_sha256,
        taxonomy_sha256=PIN.taxonomy_sha256,
        config_sha256="1" * 64,
        implementation_sha256="2" * 64,
        method="rules",
        model_sha256=None,
        provenance=c.LabelProvenance(source="unprovided", actor_ref=None, attestation_sha256=None),
        classification=classify(SOURCE),
    )
    return MachinePrefill(source=PIN, prediction=record)


@pytest.mark.parametrize(
    "field,choice,presence,value",
    [
        ("skills.python", "y", "present", True),
        ("skills.python", "n", "present", False),
        ("skills.python", "a", "absent", None),
        ("skills.python", "?", "unlabelled", None),
        ("skills.python", "u", "present", "not_stated"),
        ("work_mode", "remote", "present", "remote"),
        ("employment", "contract", "present", "contract"),
        ("salary", "none", "present", "none"),
    ],
)
def test_explicit_field_choices_preserve_presence_and_false(field, choice, presence, value):
    """Catches absence/unlabelled/explicit false or unknown class silently conflated."""
    decision = decision_from_choice(field, choice, SOURCE)
    assert decision.presence == presence
    if type(value) is bool or value is None:
        assert decision.value is value
    else:
        assert decision.value == value


def test_multiple_and_unknown_salary_units_remain_typed():
    """Catches multiple levels flattened or absent salary units guessed annual/currency."""
    multiple = decision_from_choice("seniority", "multiple:junior,senior", SOURCE)
    assert multiple.value.category == "multiple" and multiple.value.levels == ("junior", "senior")
    salary = decision_from_choice("salary", "USD 100000 120000 unknown", SOURCE)
    assert salary.value.currency == "USD" and salary.value.period is None
    assert str(salary.value.minimum) == "100000"


@pytest.mark.parametrize(
    "field,choice",
    [
        ("skills.python", "1"),
        ("work_mode", "full_time"),
        ("seniority", "multiple:senior,senior"),
        ("salary", "USD 120 100 year"),
        ("salary", "USD NaN 100 year"),
        ("company", "secret"),
    ],
)
def test_invalid_choices_never_echo_rejected_values(field, choice):
    """Catches coercion, invalid ranges and arbitrary names accepted as annotation labels."""
    with pytest.raises(ValueError) as failure:
        decision_from_choice(field, choice, SOURCE)
    assert str(failure.value) == "invalid_label_choice"


def test_all37_fields_need_explicit_confirmation_and_missing_backend_is_unavailable():
    """Catches automatic absence/default labels or a nonexistent journal reported committed."""
    s = session()
    assert s.submit().status == "incomplete" and s.submit().confirmed_fields == 0
    s.choose("skills.python", "a")
    assert s.submit().status == "incomplete"
    for field in c.FIELD_IDS:
        if field != "skills.python":
            s.choose(field, "a")
    result = s.submit()
    assert result.status == "dependency_unavailable" and result.accepted_receipts == 0
    assert not result.human_gold_eligible


@pytest.mark.parametrize("command,status", [("skip", "skipped"), ("q", "cancelled")])
def test_skip_cancel_navigation_does_not_append_or_serialize_text(command, status):
    """Catches skip/abort treated as a human decision or transient source escaping into output."""
    backend = Staging()
    s = session(backend)
    view = s.transient_view()
    prompts = []
    output = []
    result = run_keyboard(s, lambda prompt: prompts.append(prompt) or command, output.append)
    assert result.status == status and backend.calls == [] and view.text == ""
    assert TEXT not in str(prompts) + str(output) + repr(s)
    for operation in (pickle.dumps, json.dumps):
        with pytest.raises(TypeError):
            operation(s)


@pytest.mark.parametrize("split", ["heldout", "blind_repeat"])
def test_blind_source_forbids_prefill_and_assisted_labels(split):
    """Catches heldout/repeat reference labeling exposed to machine predictions."""
    with pytest.raises(ValueError, match="forbids_prefill"):
        session(split=split, prefill=machine_prefill())
    s = session(split=split)
    with pytest.raises(ValueError, match="forbids_assistance"):
        s.set_decision(decision_from_choice("skills.python", "a", SOURCE), assisted=True)


def test_dev_prefill_is_disclosed_and_never_automatically_confirmed():
    """Catches dev machine suggestions silently becoming actual human reference Gold."""
    backend = Staging()
    s = session(backend, prefill=machine_prefill())
    output = []
    assert s.submit().status == "incomplete" and not backend.calls
    result = run_keyboard(s, lambda prompt: "=", output.append)
    assert (
        result.status == "staging_complete"
        and result.accepted_receipts == 37
        and result.durable_receipts == 0
    )
    assert all(
        command.assisted and command.actor.origin == "agent_provisional"
        for command in backend.calls
    )
    assert any("dev_prefill_unconfirmed" in line for line in output)
    assert TEXT not in str(output) and not result.human_gold_eligible


def test_keyboard_explicit_absence_and_unlabelled_never_prints_source_or_bad_choice():
    """Catches unknown choice/source bodies retained in annotation prompts or errors."""
    backend = Staging()
    s = session(backend)
    answers = iter(["RAW_PRIVATE_INPUT_CANARY", "?", *(["a"] * 37)])
    prompts = []
    output = []
    result = run_keyboard(s, lambda prompt: prompts.append(prompt) or next(answers), output.append)
    assert result.status == "staging_complete" and len(backend.calls) == 37
    assert all(
        command.action == "waive_absent" and command.decision.value is None
        for command in backend.calls
    )
    assert "RAW_PRIVATE_INPUT_CANARY" not in str(output) + str(prompts) and TEXT not in str(
        output
    ) + str(prompts)


def test_stale_source_refuses_before_next_field_submit_and_clears_memory():
    """Catches old annotation continued after raw/evidence generation changes."""
    backend = Staging()
    current = [PIN]
    s = session(backend, current_source=lambda: current[0])
    view = s.transient_view()
    s.choose("skills.python", "y")
    current[0] = PIN.model_copy(update={"raw_source_sha256": "9" * 64})
    with pytest.raises(ValueError, match="generation_changed"):
        s.choose("skills.go", "a")
    assert not backend.calls and view.text == "" and s.submit().status == "cancelled"


def test_source_guard_failure_and_wrong_evidence_never_echo_private_text():
    """Catches stale/invalid input exceptions leaking a source body or out-of-input span."""
    s = session()
    decision = decision_from_choice("skills.python", "y", SOURCE)
    bad = decision.model_copy(
        update={
            "evidence": (c.CandidateReference(input_sha256="9" * 64, start_byte=0, end_byte=1),)
        }
    )
    with pytest.raises(ValueError, match="evidence_source_mismatch"):
        s.set_decision(bad)

    def unavailable():
        raise RuntimeError(TEXT)

    s = session(current_source=lambda: PIN)
    s._lookup = unavailable
    with pytest.raises(ValueError) as failure:
        s.transient_view()
    assert str(failure.value) == "annotation_source_unavailable" and TEXT not in str(failure.value)


def test_ambiguous_retry_reuses_exact_intent_before_obsolete_head_and_blocks_edit():
    """Catches a timed-out append retried with a new ID/time/head or changed label intent."""
    backend = Staging()
    first = []
    calls = []

    def ambiguous(command):
        calls.append(command)
        if not first:
            first.append(command)
            backend(command)
            return AppendReceipt(
                event_id=command.event_id,
                status="unknown",
                origin="test_staging",
                sequence=None,
                durable=False,
            )
        return backend(command)

    s = session(backend, submit=ambiguous)
    confirm_absent(s)
    assert s.submit().status == "unknown"
    with pytest.raises(ValueError, match="submitted_intent"):
        s.choose(c.FIELD_IDS[0], "y")
    assert s.submit().status == "staging_complete"
    assert calls[0].model_dump_json() == calls[1].model_dump_json()
    assert calls[1].expected_prior_event_id is None


def test_old_generation_head_kept_for_cas_but_old_label_not_reused():
    """Catches stale generation effective values borrowed merely because stable item ID matches."""
    backend = Staging()
    field = c.FIELD_IDS[0]
    backend.heads[field] = PriorLabel(
        event_id="8" * 64,
        source=PIN.model_copy(update={"raw_source_sha256": "7" * 64}),
        effective=decision_from_choice(field, "y", SOURCE),
    )
    s = session(backend)
    confirm_absent(s)
    s.submit()
    command = backend.calls[0]
    assert command.expected_prior_event_id == "8" * 64 and command.prior_value is None


def test_reopen_clears_current_ui_label_and_unknown_reopen_retries_same_intent():
    """Catches reopen restoring old positive/absence or its uncertain retry becoming a new event."""
    backend = Staging()
    s = session(backend)
    confirm_absent(s)
    assert s.submit().status == "staging_complete"
    original = backend.__call__
    unknown = []
    seen = []

    def reopen_uncertain(command):
        seen.append(command)
        if command.action == "reopen" and not unknown:
            unknown.append(command)
            original(command)
            return AppendReceipt(
                event_id=command.event_id,
                status="unknown",
                origin="test_staging",
                sequence=None,
                durable=False,
            )
        return original(command)

    s._submit = reopen_uncertain
    assert s.reopen(c.FIELD_IDS[0]).status == "unknown"
    assert s.submit().status == "unknown"  # Must not misinterpret pending reopen as a confirm.
    assert s.reopen(c.FIELD_IDS[0]).status == "incomplete"
    assert seen[0].model_dump_json() == seen[1].model_dump_json()
    assert s.submit().status == "incomplete" and c.FIELD_IDS[0] not in s._labels


def test_source_changes_mid_batch_stop_further_appends_without_fictitious_rollback():
    """Catches partial append batches claimed complete or cancelled writes silently undone."""
    backend = Staging()
    current = [PIN]

    def moving(command):
        receipt = backend(command)
        current[0] = PIN.model_copy(update={"evidence_revision_sha256": "6" * 64})
        return receipt

    s = session(backend, current_source=lambda: current[0], submit=moving)
    confirm_absent(s)
    with pytest.raises(ValueError, match="generation_changed"):
        s.submit()
    result = s.submit()
    assert result.status == "cancelled" and result.accepted_receipts == 1
    assert len(backend.calls) == 1 and not result.human_gold_eligible


def test_human_actor_or_mock_receipts_never_establish_human_gold_eligibility():
    """Catches actor self-attestation or a mocked append promoted to actual human Gold."""
    backend = Staging()
    actor = Actor(origin="human_self_attested", actor_ref="5" * 64, attestation_ref="4" * 64)
    s = session(backend, actor=actor)
    confirm_absent(s)
    result = s.submit()
    assert (
        result.human_evidence_status == "requires_owner_validation"
        and not result.human_gold_eligible
    )
    data = result.model_dump()
    data["human_gold_eligible"] = True
    with pytest.raises(ValidationError):
        SessionResult.model_validate(data)


def test_blind_repeat_requires_same_item_actor_and_at_least_seven_days():
    """Catches a blind repeat performed early or attached to another item/operator."""
    repeat = BlindRepeat(
        item_id=PIN.item_id,
        actor_ref=ACTOR.actor_ref,
        first_event_ref="3" * 64,
        first_at_utc=datetime(2026, 10, 7, tzinfo=UTC),
        origin="synthetic_control",
    )
    session(split="blind_repeat", repeat=repeat)
    with pytest.raises(ValueError, match="requires_prior_timing"):
        session(split="blind_repeat", repeat=None)
    with pytest.raises(ValueError, match="requires_seven_days"):
        session(
            split="blind_repeat",
            repeat=repeat.model_copy(
                update={"first_at_utc": datetime(2026, 10, 7, 0, 1, tzinfo=UTC)}
            ),
        )
    with pytest.raises(ValueError, match="item_or_actor_mismatch"):
        session(split="blind_repeat", repeat=repeat.model_copy(update={"actor_ref": "2" * 64}))


def test_generated_own_schema_closed_and_safe_command_roundtrip():
    """Catches private text/arbitrary dimensions becoming part of serializable app intents."""
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "src/hiring_signals/annotation/schemas.json"
    assert json.loads(path.read_text()) == schema_documents()
    backend = Staging()
    s = session(backend)
    confirm_absent(s)
    s.submit()
    assert all(TEXT not in command.model_dump_json() for command in backend.calls)
    for document in schema_documents().values():
        for obj in [document, *document.get("$defs", {}).values()]:
            if obj.get("type") == "object":
                assert obj["additionalProperties"] is False


def test_prefill_must_bind_full_source_generation_and_raw_machine_provenance():
    """Catches stale predictions or reference/human labels laundered as dev suggestions."""
    prefill = machine_prefill()
    stale = prefill.model_copy(
        update={"source": PIN.model_copy(update={"raw_source_sha256": "9" * 64})}
    )
    with pytest.raises(ValueError, match="source_generation_mismatch"):
        session(prefill=stale)
    data = prefill.model_dump(mode="json")
    data["prediction"]["provenance"]["source"] = "synthetic_expectation"
    with pytest.raises(ValidationError):
        MachinePrefill.model_validate_json(json.dumps(data))
