"""Owner-local identity/retention/race controls with original synthetic canaries."""

import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from hiring_signals import contracts as c
from hiring_signals.ingest.private_state import PrivacyError, PrivateState
from hiring_signals.ingest.redaction import prepare_synthetic
from hiring_signals.ingest.transport import SyntheticPost

ROOT = Path(__file__).resolve().parents[2]
COMPANY = "Canary Workshop"
PERSON = "Canary Person"
LINK = "https://example.invalid/PRIVATE_APPLY_CANARY"
TEXT = f"{COMPANY} seeks an engineer. Contact {PERSON} at {LINK}"
CANARIES = (COMPANY.encode(), PERSON.encode(), LINK.encode(), TEXT.encode())


class Clock:
    def __init__(self):
        self.now, self.calls, self.expire_on = 0.0, 0, None

    def __call__(self):
        self.calls += 1
        if self.expire_on == self.calls:
            self.now = 100.0
        return self.now


def prepared():
    return prepare_synthetic(
        SyntheticPost(900002, TEXT),
        identity_terms=(COMPANY, PERSON),
        identities_reviewed=True,
        link_kinds=("application",),
    )


def source(state, lease):
    result = prepared()
    item_id = state.register_source(
        source_id=900002,
        month="2026-10",
        raw_sha256=result.raw_sha256,
        input_sha256=result.envelope.input_sha256,
        organization=COMPANY,
        lease=lease,
    )
    return item_id, result


def record(item_id, input_hash):
    absent = {
        "value": None,
        "evidence_state": "absent",
        "process_status": "ok",
        "certainty": None,
        "candidates": [],
        "error_code": None,
    }
    data = {
        "schema_version": 1,
        "item_id": item_id,
        "month": "2026-10",
        "input_sha256": input_hash,
        "taxonomy_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "implementation_sha256": "c" * 64,
        "method": "rules",
        "model_sha256": None,
        "provenance": {"source": "unprovided", "actor_ref": None, "attestation_sha256": None},
        "classification": {
            "ai_engineering_role": absent,
            "portfolio_requested": absent,
            "seniority": {**absent, "value": "not_stated", "levels": []},
            "work_mode": {**absent, "value": "not_stated"},
            "employment": {**absent, "value": "not_stated"},
            "skills": {skill: absent for skill in c.SKILL_IDS},
            "location_stated": absent,
            "salary": {
                "presence": absent,
                "stated_minimum": None,
                "stated_maximum": None,
                "currency": None,
                "period": None,
                "normalization_status": "not_applicable",
                "normalized": None,
            },
        },
    }
    return c.PrivateDerivedRecord.model_validate_json(json.dumps(data))


def canary_files(directory):
    # Return names only, never content or key bytes, even when an assertion fails.
    return [
        p.name
        for p in directory.rglob("*")
        if p.is_file() and any(canary in p.read_bytes() for canary in CANARIES)
    ]


def test_redacted_text_hash_links_and_utf8_lineage_are_transient():
    """Catches known identity/link strings retained or raw and redacted hashes conflated."""
    result = prepared()
    assert result.reason is None
    assert all(value not in result.envelope.text for value in (COMPANY, PERSON, LINK))
    assert result.raw_sha256 == hashlib.sha256(TEXT.encode()).hexdigest()
    assert result.raw_sha256 != result.envelope.input_sha256
    assert result.links.application and result.links.has_link and not result.links.portfolio
    for span in result.spans:
        assert TEXT.encode()[span.raw_start_byte : span.raw_end_byte]
        assert result.envelope.text.encode()[span.redacted_start_byte : span.redacted_end_byte] in {
            b"[IDENTITY]",
            b"[LINK]",
        }
    assert COMPANY not in repr(result)


@pytest.mark.parametrize(
    "text,reviewed,terms,kinds,reason",
    [
        (TEXT, False, (COMPANY, PERSON), ("application",), "identity_review_required"),
        ("<b>Canary Person</b>", True, (PERSON,), (), "unsupported_markup"),
        ("ftp://example.invalid/private", True, (), (), "unsupported_link_scheme"),
        (TEXT, True, (COMPANY, PERSON), (), "link_inventory_review_required"),
        ("é" * 20000, True, (), (), "redacted_byte_limit"),
        (TEXT, True, ("",), ("application",), "invalid_identity_inventory"),
    ],
    ids=["unreviewed", "markup", "scheme", "link_inventory", "utf8_bytes", "empty_identity"],
)
def test_unknown_unreviewed_or_oversize_input_is_quarantined(text, reviewed, terms, kinds, reason):
    """Catches unsupported identity/markup/byte states proceeding as de-identified model input."""
    result = prepare_synthetic(
        SyntheticPost(1, text), identity_terms=terms, identities_reviewed=reviewed, link_kinds=kinds
    )
    assert result.envelope is None and result.raw_sha256 is None and result.reason == reason


def test_generated_hmac_private_store_and_recovery_no_plaintext(tmp_path, capsys):
    """Catches durable plaintext and identity drift across consistent backup/restore."""
    directory = tmp_path / "private"
    state = PrivateState(directory, product_root=ROOT)
    lease = state.begin(lease_seconds=30)
    item_id, result = source(state, lease)
    state.write_record(record(item_id, result.envelope.input_sha256), lease=lease)
    assert len(item_id) == 64 and item_id != result.raw_sha256
    assert state.lookup_source(item_id, lease=lease) == 900002
    assert len(state.read_records(lease=lease)) == 1
    assert (directory / "identity.key").stat().st_size == 32
    state.close()
    assert canary_files(directory) == []
    restored = tmp_path / "restored"
    shutil.copytree(directory, restored)
    replacement = PrivateState(restored, product_root=ROOT)
    new_lease = replacement.begin(lease_seconds=30)
    assert replacement.item_id(900002) == item_id
    assert replacement.lookup_source(item_id, lease=new_lease) == 900002
    assert len(replacement.read_records(lease=new_lease)) == 1
    with pytest.raises(PrivacyError):
        replacement.write_record(record(item_id, result.envelope.input_sha256), lease=lease)
    replacement.close()
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_private_state_refuses_product_or_ancestor_directory():
    """Catches a key/state store accidentally created in the public product tree."""
    for directory in (ROOT, ROOT / "data", ROOT.parent):
        with pytest.raises(PrivacyError, match="state_must_be_outside_product"):
            PrivateState(directory, product_root=ROOT)


def test_missing_key_cannot_silently_regenerate_identity(tmp_path):
    """Catches a missing recovery key silently breaking stable source mapping."""
    directory = tmp_path / "private"
    state = PrivateState(directory, product_root=ROOT)
    state.close()
    (directory / "identity.key").unlink()
    with pytest.raises(PrivacyError, match="identity_key_recovery_required"):
        PrivateState(directory, product_root=ROOT)


def test_cancel_expires_memory_and_rejects_late_write_after_reopen(tmp_path):
    """Catches cancelled work restored to validity by reopening the same key/mapping."""
    directory = tmp_path / "private"
    state = PrivateState(directory, product_root=ROOT)
    lease = state.begin(lease_seconds=30)
    item_id, result = source(state, lease)
    assert lease.mappings
    state.cancel(lease)
    assert not lease.active and lease.mappings == {}
    with pytest.raises(PrivacyError):
        state.write_record(record(item_id, result.envelope.input_sha256), lease=lease)
    state.close()
    reopened = PrivateState(directory, product_root=ROOT)
    with pytest.raises(PrivacyError):
        reopened.write_record(record(item_id, result.envelope.input_sha256), lease=lease)
    valid = reopened.begin(lease_seconds=30)
    assert reopened.read_records(lease=valid) == ()
    reopened.close()
    assert canary_files(directory) == []


def test_queued_write_loses_to_cancellation_in_same_critical_section(tmp_path):
    """Catches a queued writer using a lease checked before cancellation acquired the lock."""
    state = PrivateState(tmp_path / "private", product_root=ROOT)
    lease = state.begin(lease_seconds=30)
    item_id, result = source(state, lease)
    started = threading.Event()
    outcomes = []

    def writer():
        started.set()
        try:
            state.write_record(record(item_id, result.envelope.input_sha256), lease=lease)
        except PrivacyError:
            outcomes.append("rejected")

    with state._lock:
        worker = threading.Thread(target=writer)
        worker.start()
        assert started.wait(2)
        state.cancel(lease)
    worker.join(5)
    assert not worker.is_alive() and outcomes == ["rejected"]
    valid = state.begin(lease_seconds=30)
    assert state.read_records(lease=valid) == ()
    state.close()


def test_expiry_between_sql_and_commit_rolls_back_and_clears_memory(tmp_path):
    """Catches expiry during SQL admitted because only the start of a write was checked."""
    clock = Clock()
    state = PrivateState(tmp_path / "private", product_root=ROOT, clock=clock)
    lease = state.begin(lease_seconds=10)
    item_id, result = source(state, lease)
    clock.expire_on = clock.calls + 2
    with pytest.raises(PrivacyError, match="inactive_or_expired_lease"):
        state.write_record(record(item_id, result.envelope.input_sha256), lease=lease)
    assert lease.mappings == {} and not lease.active
    renewed = state.begin(lease_seconds=10)
    assert state.read_records(lease=renewed) == ()
    state.close()


def test_cross_handle_cancel_generation_blocks_old_writer(tmp_path):
    """Catches another state handle committing work after the cancellation epoch advanced."""
    directory = tmp_path / "private"
    first = PrivateState(directory, product_root=ROOT)
    second = PrivateState(directory, product_root=ROOT)
    lease1 = first.begin(lease_seconds=30)
    lease2 = second.begin(lease_seconds=30)
    item_id, result = source(first, lease1)
    first.cancel(lease1)
    with pytest.raises(PrivacyError, match="stale_generation"):
        second.write_record(record(item_id, result.envelope.input_sha256), lease=lease2)
    first.close()
    second.close()


def test_invalid_schema_and_changed_source_never_persist(tmp_path):
    """Catches source changes or raw/unvalidated fields written through the persistence adapter."""
    directory = tmp_path / "private"
    state = PrivateState(directory, product_root=ROOT)
    lease = state.begin(lease_seconds=30)
    item_id, result = source(state, lease)
    valid = record(item_id, result.envelope.input_sha256)
    invalid = json.loads(valid.model_dump_json())
    invalid["raw_text"] = TEXT
    with pytest.raises(PrivacyError, match="invalid_derived_record"):
        state.write_record(invalid, lease=lease)
    with pytest.raises(PrivacyError, match="source_changed_requires_successor"):
        state.register_source(
            source_id=900002,
            month="2026-10",
            raw_sha256="f" * 64,
            input_sha256=result.envelope.input_sha256,
            organization=COMPANY,
            lease=lease,
        )
    with pytest.raises(PrivacyError, match="record_source_binding_mismatch"):
        state.write_record(valid.model_copy(update={"input_sha256": "f" * 64}), lease=lease)
    assert state.read_records(lease=lease) == ()
    state.close()
    assert canary_files(directory) == []


def test_actual_process_crash_before_commit_preserves_prior_safe_record(tmp_path):
    """Catches partial durable replacement or plaintext leakage after process termination."""
    directory = tmp_path / "private"
    state = PrivateState(directory, product_root=ROOT)
    lease = state.begin(lease_seconds=30)
    item_id, result = source(state, lease)
    baseline = record(item_id, result.envelope.input_sha256)
    state.write_record(baseline, lease=lease)
    state.close()
    changed = baseline.model_copy(update={"config_sha256": "f" * 64})
    script = tmp_path / "crash_control.py"
    script.write_text(
        "import os,sys\nfrom pathlib import Path\n"
        "sys.path.insert(0,str(Path(sys.argv[1])/'src'))\n"
        "from hiring_signals.contracts import PrivateDerivedRecord\n"
        "from hiring_signals.ingest.private_state import PrivateState\n"
        "state=PrivateState(Path(sys.argv[2]),product_root=Path(sys.argv[1]))\n"
        "lease=state.begin(lease_seconds=30)\n"
        "payload=PrivateDerivedRecord.model_validate_json(sys.stdin.read())\n"
        "transient_source='Canary Workshop Canary Person https://example.invalid/PRIVATE_APPLY_CANARY'\n"
        "original=state._active\ncalls=0\n"
        "def crash_before_commit(token):\n"
        " global calls\n calls+=1\n original(token)\n"
        " if calls==2: os._exit(23)\n"
        "state._active=crash_before_commit\nstate.write_record(payload,lease=lease)\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-I", str(script), str(ROOT), str(directory)],
        input=changed.model_dump_json(),
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    assert completed.returncode == 23
    assert completed.stdout == completed.stderr == ""
    reopened = PrivateState(directory, product_root=ROOT)
    valid = reopened.begin(lease_seconds=30)
    assert reopened.read_records(lease=valid) == (baseline,)
    reopened.close()
    assert canary_files(directory) == []


def test_utf8_redaction_ranges_use_bytes_not_character_offsets():
    """Catches non-ASCII prefixes shifting candidate lineage to wrong original byte spans."""
    text = "éé " + TEXT
    result = prepare_synthetic(
        SyntheticPost(1, text),
        identity_terms=(COMPANY, PERSON),
        identities_reviewed=True,
        link_kinds=("application",),
    )
    first = result.spans[0]
    assert first.raw_start_byte == len("éé ".encode()) == 5
    assert text.encode()[first.raw_start_byte : first.raw_end_byte] == COMPANY.encode()


@pytest.mark.parametrize("lifetime", [0, -1, True, float("nan"), "30"])
def test_lease_lifetime_must_be_explicit_positive_finite_scalar(tmp_path, lifetime):
    """Catches implicit/coerced/infinite lease lifetime defeating expiry admission."""
    state = PrivateState(tmp_path / "private", product_root=ROOT)
    with pytest.raises(PrivacyError, match="invalid_explicit_lease"):
        state.begin(lease_seconds=lifetime)
    state.close()


def test_reopened_records_must_still_bind_to_private_source_mapping(tmp_path):
    """Catches a valid-looking restored record whose source fingerprint mapping differs."""
    directory = tmp_path / "private"
    state = PrivateState(directory, product_root=ROOT)
    lease = state.begin(lease_seconds=30)
    item_id, result = source(state, lease)
    saved = record(item_id, result.envelope.input_sha256)
    state.write_record(saved, lease=lease)
    state.close()
    changed = saved.model_copy(update={"input_sha256": "f" * 64})
    with sqlite3.connect(directory / "derived.sqlite3") as connection:
        connection.execute("UPDATE records SET payload=?", (changed.model_dump_json(),))
    with pytest.raises(PrivacyError, match="invalid_private_state"):
        PrivateState(directory, product_root=ROOT)


def test_generated_key_binary_control_bytes_never_expand_on_windows(tmp_path):
    """Catches Windows O_TEXT newline expansion corrupting randomly generated HMAC key length."""
    # Deliberately public synthetic binary control, never a real credential or owner key.
    control = bytes([10, 13, 26] + [65] * 29)
    directory = tmp_path / "private"
    with patch("hiring_signals.ingest.private_state.secrets.token_bytes", return_value=control):
        state = PrivateState(directory, product_root=ROOT)
    assert (directory / "identity.key").stat().st_size == 32
    first = state.item_id(1)
    state.close()
    restored = PrivateState(directory, product_root=ROOT)
    assert restored.item_id(1) == first
    restored.close()
