"""Original small actual-journal controls; no Gold or human label evidence."""

import hashlib
import json
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

from hiring_signals import contracts as c
from hiring_signals.adapters.rulings import (
    AnnotationJournal,
    SourceAuthority,
    generation,
    to_owner_intent,
)
from hiring_signals.annotation.models import Actor, FieldDecision, ScalarCommand, SourcePin
from hiring_signals.annotation.session import AnnotationSession, decision_from_choice
from hiring_signals.shared.rulings.store import GenerationConflict, IntentConflict, PriorConflict

TEXT = "ORIGINAL_TRANSIENT_TEXT_741\nRequirements: Python"
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


def backend(tmp_path):
    private = tmp_path / "private"
    private.mkdir()
    sources = SourceAuthority()
    sources.install(PIN, SOURCE)
    return AnnotationJournal(private, product_root=Path(__file__).parents[2], sources=sources)


def command(number=1, choice="n", prior=None, action=None, pin=PIN, actor=ACTOR):
    label = decision_from_choice("skills.python", choice, SOURCE)
    selected = action or (
        "reopen" if choice == "?" else "waive_absent" if choice == "a" else "confirm"
    )
    return ScalarCommand(
        schema_version=1,
        event_id=f"{number:064x}",
        namespace="hiring-signals",
        source=pin,
        decision=label,
        action=selected,
        expected_prior_event_id=prior.event_id if prior else None,
        prior_value=prior.effective if prior else None,
        assisted=False,
        actor=actor,
        at_utc=datetime(2026, 10, 1, tzinfo=UTC),
        reason="reopened" if selected == "reopen" else "explicit_confirmation",
    )


def test_actual_correct_confirm_reopen_and_absent_do_not_revive_old_false(tmp_path):
    """Catches false/null conflation or reopening restoring a previous effective label."""
    journal = backend(tmp_path)
    first = command()
    assert to_owner_intent(first).payload.action == "correct"
    assert journal.append(first).sequence == 1
    prior = journal.head(PIN.item_id, "skills.python")
    assert prior.effective.value is False
    confirmed = command(2, prior=prior)
    assert to_owner_intent(confirmed).payload.action == "confirm"
    assert journal.submit(confirmed).durable
    prior = journal.head(PIN.item_id, "skills.python")
    reopened = command(3, "?", prior=prior)
    journal.append(reopened)
    after = journal.head(PIN.item_id, "skills.python")
    assert after.event_id == reopened.event_id and after.effective is None
    journal.append(command(4, "a", prior=after))
    assert journal.head(PIN.item_id, "skills.python").effective == FieldDecision(
        field_id="skills.python", presence="absent", value=None, evidence=()
    )
    raw = journal.store.path.read_bytes()
    assert TEXT.encode() not in raw and b"ORIGINAL_TRANSIENT_TEXT_741" not in raw
    assert b'"value":false' in raw and b'"new_value":null' in raw


def test_historical_retry_stale_source_and_stable_head_conflicts_are_distinct(tmp_path):
    """Catches minting current authority from an old retry or bypassing subject CAS."""
    journal = backend(tmp_path)
    first = command()
    journal.append(first)
    with pytest.raises(PriorConflict):
        journal.append(command(2))
    changed = first.model_copy(update={"assisted": True})
    with pytest.raises(IntentConflict):
        journal.append(changed)
    newer_pin = PIN.model_copy(update={"evidence_revision_sha256": "1" * 64})
    journal.sources.install(newer_pin, SOURCE)
    receipt = journal.append(first)
    assert receipt.historical and receipt.outcome == "exact_retry" and receipt.sequence == 1
    assert receipt.current_generation_authority is False
    prior = journal.head(PIN.item_id, "skills.python")
    assert prior.event_id == first.event_id and prior.effective is None
    assert journal.submit(command(2, prior=prior)).status == "conflict"
    journal.sources.remove(PIN.item_id)
    assert journal.head(PIN.item_id, "skills.python").effective is None


@pytest.mark.parametrize(
    "field", ["raw_source_sha256", "input_sha256", "taxonomy_sha256", "rubric_sha256"]
)
def test_every_source_revision_component_changes_generation(field):
    """Catches taxonomy/rubric/input/raw changes leaving old label authority active."""
    assert generation(PIN.model_copy(update={field: "9" * 64})) != generation(PIN)


def test_actual_fsync_uncertainty_keeps_same_intent_and_historical_retry(tmp_path, monkeypatch):
    """Catches acknowledging an unsynced append or duplicating it on ambiguous retry."""
    journal = backend(tmp_path)
    first = command()
    actual = journal.store._sync

    def failed(fd):
        raise OSError("PRIVATE_ERROR_DO_NOT_EXPORT")

    monkeypatch.setattr(journal.store, "_sync", failed)
    assert journal.submit(first).status == "unknown"
    monkeypatch.setattr(journal.store, "_sync", actual)
    ack = journal.append(first)
    assert ack.historical and ack.sequence == 1
    assert len(journal.store.replay().events) == 1


def test_actual_reopen_restart_projection_and_torn_journal_no_repair(tmp_path):
    """Catches restart losing the barrier or silently truncating a damaged journal."""
    journal = backend(tmp_path)
    first = command()
    journal.append(first)
    journal.append(command(2, "?", prior=journal.head(PIN.item_id, "skills.python")))
    restarted = AnnotationJournal(
        journal.store.root, product_root=Path(__file__).parents[2], sources=journal.sources
    )
    assert restarted.head(PIN.item_id, "skills.python").effective is None
    journal.store.path.write_bytes(journal.store.path.read_bytes() + b"torn")
    before = journal.store.path.read_bytes()
    assert restarted.submit(command(3)).status == "unavailable"
    with pytest.raises(ValueError, match="requires_repair"):
        restarted.head(PIN.item_id, "skills.python")
    assert journal.store.path.read_bytes() == before


def test_actual37field_session_has_durable_receipts_without_human_gold(tmp_path):
    """Catches a complete UI session still using a mock instead of the canonical journal."""
    journal = backend(tmp_path)
    session = AnnotationSession(
        source=SOURCE,
        pin=PIN,
        actor=ACTOR,
        split="heldout",
        current_source=lambda: PIN,
        head=lambda field: journal.head(PIN.item_id, field),
        submit=journal.submit,
    )
    for field in c.FIELD_IDS:
        session.choose(field, "a")
    result = session.submit()
    assert result.status == "owner_receipts_complete" and result.durable_receipts == 37
    assert result.human_gold_eligible is False
    assert len(journal.store.replay().events) == 37
    assert session.submit() == result and len(journal.store.replay().events) == 37


def test_human_actor_attribution_remains_unverified_in_actual_canonical_export(tmp_path):
    """Catches self-attested actor strings becoming authenticated human labels."""
    from hiring_signals.shared.rulings.projection import export_labels
    from hiring_signals.shared.rulings.store import subject_key

    journal = backend(tmp_path)
    human = Actor(origin="human_self_attested", actor_ref="f" * 64, attestation_ref="1" * 64)
    intent = to_owner_intent(command(actor=human))
    journal.append(command(actor=human))
    labels = export_labels(
        journal.store.replay(),
        {subject_key(intent.namespace, intent.subject): intent.generation_identity},
    )
    assert labels[0].label_source == "unverified_human"


def test_source_mutation_waits_until_actual_append_fsync_finishes(tmp_path, monkeypatch):
    """Catches a source removal racing between current-generation validation and append ack."""
    journal = backend(tmp_path)
    entered, release, attempting, removed = (threading.Event() for _ in range(4))
    actual = journal.store._sync

    def paused(fd):
        entered.set()
        assert release.wait(3)
        actual(fd)

    def remove():
        attempting.set()
        journal.sources.remove(PIN.item_id)
        removed.set()

    monkeypatch.setattr(journal.store, "_sync", paused)
    with ThreadPoolExecutor(max_workers=2) as pool:
        append = pool.submit(journal.append, command())
        assert entered.wait(3)
        removal = pool.submit(remove)
        assert attempting.wait(3) and not removed.is_set()
        release.set()
        assert append.result(timeout=3).sequence == 1
        removal.result(timeout=3)
    assert removed.is_set() and journal.head(PIN.item_id, "skills.python").effective is None


def test_invalid_field_source_coordinates_and_product_storage_are_refused(tmp_path):
    """Catches arbitrary fields, stale byte references or journal durability inside the repo."""
    journal = backend(tmp_path)
    first = command()
    bad = first.decision.model_copy(
        update={
            "evidence": (
                c.CandidateReference(input_sha256=PIN.input_sha256, start_byte=0, end_byte=1000),
            )
        }
    )
    with pytest.raises(GenerationConflict):
        journal.append(first.model_copy(update={"decision": bad}))
    with pytest.raises(ValueError, match="outside_product"):
        AnnotationJournal(
            Path(__file__).parents[2],
            product_root=Path(__file__).parents[2],
            sources=journal.sources,
        )
    with pytest.raises(ValueError, match="digest_mismatch"):
        journal.sources.install(PIN.model_copy(update={"input_sha256": "0" * 64}), SOURCE)


def test_detached_actual_journal_owner_and_network_blocked(tmp_path):
    """Catches a hidden original-app dependency in real copied append/replay/negative paths."""
    source = Path(__file__).parents[2] / "src/hiring_signals/shared/rulings"
    shutil.copytree(source, tmp_path / "moved", ignore=shutil.ignore_patterns("__pycache__"))
    private = tmp_path / "detached-private"
    private.mkdir()
    payload = tmp_path / "intent.json"
    payload.write_text(to_owner_intent(command()).model_dump_json())
    code = """
import sys,importlib.abc,socket,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
class Guard(importlib.abc.MetaPathFinder):
 def find_spec(self,name,path=None,target=None):
  if name.split('.')[0] in {'rfr','hiring_signals','openai','typesafe','PIL','pytesseract'}:
   raise RuntimeError('owner_sdk_forbidden')
sys.meta_path.insert(0,Guard())
def denied(*a,**k):raise RuntimeError('network_forbidden')
socket.create_connection=denied;socket.socket.connect=denied
from moved.models import RulingIntent
from moved.store import JournalStore,GenerationConflict
intent=RulingIntent.model_validate_json(Path(sys.argv[2]).read_bytes())
class Valid:
 def validate(self,subject,generation):assert generation==intent.generation_identity
class Invalid:
 def validate(self,subject,generation):raise ValueError('stale')
s=JournalStore(Path(sys.argv[3]))
assert s.append(intent,Valid()).sequence==1
assert s.append(intent,Invalid()).historical
bad=intent.model_copy(update={'event_id':'detached-negative','expected_prior_event_id':intent.event_id})
try:s.append(bad,Invalid())
except GenerationConflict:pass
else:raise AssertionError('negative_not_detected')
assert len(JournalStore(Path(sys.argv[3])).replay().events)==1
print(json.dumps({'events':1,'positive':1,'negative':1,'owner':'blocked','network':'blocked'}))
"""
    result = subprocess.run(
        [sys.executable, "-I", "-c", code, str(tmp_path), str(payload), str(private)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "events": 1,
        "positive": 1,
        "negative": 1,
        "owner": "blocked",
        "network": "blocked",
    }
