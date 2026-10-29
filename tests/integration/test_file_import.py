"""Tiny handcrafted posting controls; no source corpus, Gold or quality measurement."""

import hashlib
import json
import math
import os
import sqlite3

import pytest

from hiring_signals import contracts as c
from hiring_signals.cli import main
from hiring_signals.ingest import file_import as f
from hiring_signals.ingest import redaction, transport
from hiring_signals.ingest.private_state import PrivateState

COMPANY = "SYNTHETIC_FILE_COMPANY_713"
AUTHOR = "SYNTHETIC_FILE_AUTHOR_829"
URL = "https://file-synthetic.invalid/apply"
SOURCE_ID = 79301
TEXT = (
    f"{COMPANY}\nContact: {AUTHOR}\nDuties: build ML systems\nRequirements: Python\n"
    f"Application instructions: send resume only\nApply: {URL}"
)


def inputs(tmp_path, *, text=TEXT):
    source, review = tmp_path / "owned-posting.txt", tmp_path / "review.json"
    source.write_text(text, encoding="utf-8")
    review.write_text(
        json.dumps(
            {
                "source_id": SOURCE_ID,
                "identities_reviewed": True,
                "identity_terms": [COMPANY, AUTHOR],
                "organization": COMPANY,
                "link_kinds": ["application"],
            }
        ),
        encoding="utf-8",
    )
    return source, review


def execute(source, review, private, **changes):
    options = {
        "review_path": review,
        "month": "2026-10",
        "source_id": SOURCE_ID,
        "synthetic_only": True,
        "private_directory": private,
        "lease_seconds": 30,
    }
    options.update(changes)
    return f.execute_file_import(source, **options)


def cli_args(source, review, private):
    return [
        "import",
        "--file",
        str(source),
        "--review",
        str(review),
        "--month",
        "2026-10",
        "--source-id",
        str(SOURCE_ID),
        "--synthetic-only",
        "--private-dir",
        str(private),
        "--lease-seconds",
        "30",
    ]


def rows(private):
    with sqlite3.connect(private / "derived.sqlite3") as connection:
        sources = connection.execute("SELECT * FROM sources").fetchall()
        records = connection.execute("SELECT payload FROM records").fetchall()
    return sources, records


def test_text_cli_reuses_rules_redaction_hmac_and_closed_state(tmp_path, capsys, monkeypatch):
    """Catches a renamed envelope command, unredacted state, or disconnected CLI/storage."""
    import socket

    def forbidden(*args, **kwargs):
        raise AssertionError("network_forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    source, review = inputs(tmp_path)
    originals = source.read_bytes(), review.read_bytes()
    private = tmp_path / "private"
    assert main(cli_args(source, review, private)) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert json.loads(captured.out) == {
        "schema_version": 1,
        "status": "synthetic_file_derivation_stored",
        "complete_workflow": False,
        "source_scope": "original_synthetic",
        "quality_status": "not_measured",
        "provider_calls": 0,
    }
    mappings, payloads = rows(private)
    assert len(mappings) == len(payloads) == 1
    record = c.PrivateDerivedRecord.model_validate_json(payloads[0][0])
    assert record.month == "2026-10" and record.method == "rules"
    assert record.provenance.source == "unprovided" and record.model_sha256 is None
    judgment = record.classification
    assert judgment.ai_engineering_role.value is True
    assert judgment.portfolio_requested.value is False
    assert judgment.skills.python.value is True
    assert judgment.skills.rust.value is None
    assert judgment.skills.rust.evidence_state == "absent"
    prepared = redaction.prepare_synthetic(
        transport.SyntheticPost(SOURCE_ID, TEXT),
        identity_terms=(COMPANY, AUTHOR),
        identities_reviewed=True,
        link_kinds=("application",),
    )
    assert mappings[0][3] == hashlib.sha256(TEXT.encode()).hexdigest()
    assert mappings[0][4] == prepared.envelope.input_sha256 == record.input_sha256
    assert mappings[0][3] != mappings[0][4]
    state = PrivateState(private, product_root=f.workflow.PRODUCT_ROOT)
    try:
        assert record.item_id == state.item_id(SOURCE_ID)
    finally:
        state.close()
    retained = b"".join(path.read_bytes() for path in private.iterdir())
    for marker in (COMPANY, AUTHOR, URL, TEXT, str(source), str(review)):
        assert marker.encode() not in retained + captured.out.encode() + captured.err.encode()
    assert (source.read_bytes(), review.read_bytes()) == originals
    assert set(path.name for path in tmp_path.iterdir()) == {
        "owned-posting.txt",
        "review.json",
        "private",
    }


@pytest.mark.parametrize(
    "fault",
    [
        "no_flag",
        "invalid_month",
        "boolean_id",
        "overflow_id",
        "wrong_id",
        "unreviewed",
        "extra_review",
        "missing_review",
        "duplicate_key",
        "nonfinite_json",
        "bad_link_type",
        "missing_identity",
        "organization_inventory",
        "link_inventory",
        "empty",
        "characters",
        "bytes",
        "invalid_utf8",
        "markup",
        "scheme",
        "extension",
        "protected",
        "review_limit",
        "surrogate_inventory",
    ],
)
def test_bad_input_or_quarantine_has_no_private_effects(tmp_path, fault):
    """Catches malformed, oversized or quarantined input becoming an accepted derivation."""
    source, review = inputs(tmp_path)
    options = {}
    value = json.loads(review.read_text(encoding="utf-8"))
    if fault == "no_flag":
        options["synthetic_only"] = False
    elif fault == "invalid_month":
        options["month"] = "2026-13"
    elif fault == "boolean_id":
        options["source_id"] = True
    elif fault == "overflow_id":
        options["source_id"] = 2**63
    elif fault == "wrong_id":
        value["source_id"] += 1
    elif fault == "unreviewed":
        value["identities_reviewed"] = False
    elif fault == "extra_review":
        value["raw_text"] = "synthetic-extra-field"
    elif fault == "missing_review":
        del value["organization"]
    elif fault == "bad_link_type":
        value["link_kinds"] = [{}]
    elif fault == "missing_identity":
        value["identity_terms"] = [" "]
        value["organization"] = None
    elif fault == "organization_inventory":
        value["identity_terms"] = [AUTHOR]
    elif fault == "surrogate_inventory":
        value["identity_terms"] = ["\ud800"]
        value["organization"] = "\ud800"
    elif fault == "link_inventory":
        value["link_kinds"] = []
    elif fault == "empty":
        source.write_text(" \n", encoding="utf-8")
    elif fault == "characters":
        source.write_text("x" * 20001, encoding="utf-8")
    elif fault == "bytes":
        source.write_text("\u754c" * 12000, encoding="utf-8")
    elif fault == "invalid_utf8":
        source.write_bytes(b"\xff")
    elif fault == "markup":
        source.write_text("<b>original synthetic</b>", encoding="utf-8")
    elif fault == "scheme":
        source.write_text("ftp://synthetic.invalid", encoding="utf-8")
    elif fault == "extension":
        renamed = source.with_suffix(".json")
        source.rename(renamed)
        source = renamed
    elif fault == "protected":
        folder = tmp_path / ".chatexports"
        folder.mkdir()
        renamed = folder / source.name
        source.rename(renamed)
        source = renamed
    review.write_text(json.dumps(value), encoding="utf-8")
    if fault == "duplicate_key":
        review.write_text('{"source_id":1,"source_id":2}', encoding="utf-8")
    elif fault == "nonfinite_json":
        review.write_text('{"source_id":NaN}', encoding="utf-8")
    elif fault == "review_limit":
        review.write_bytes(b" " * (c.MAX_INPUT_BYTES + 1))
    original = source.read_bytes(), review.read_bytes()
    private = tmp_path / "private"
    with pytest.raises(f.FileImportError) as failure:
        execute(source, review, private, **options)
    assert failure.value.private_effects_possible is False
    assert not private.exists()
    assert (source.read_bytes(), review.read_bytes()) == original
    assert COMPANY not in str(failure.value) and str(source) not in str(failure.value)


@pytest.mark.parametrize("lease", [0, -1, True, math.nan, math.inf])
def test_invalid_lease_refuses_before_input_reads(tmp_path, lease, monkeypatch):
    """Catches invalid leases reading postings or creating state before admission."""

    def forbidden(*args, **kwargs):
        raise AssertionError("input_read_forbidden")

    monkeypatch.setattr(f, "_input_path", forbidden)
    with pytest.raises(f.FileImportError, match="finite_explicit_lease_required"):
        execute(
            tmp_path / "absent.txt",
            tmp_path / "absent.json",
            tmp_path / "private",
            lease_seconds=lease,
        )
    assert not (tmp_path / "private").exists()


@pytest.mark.parametrize("target", ["posting", "review", "parent", "hardlink"])
def test_linked_input_paths_refuse_without_state(tmp_path, target):
    """Catches symlink/reparse ancestors or multiply linked files bypassing selection checks."""
    source, review = inputs(tmp_path)
    linked = tmp_path / ("alias.json" if target == "review" else "alias.txt")
    try:
        if target == "parent":
            linked = tmp_path / "alias-dir"
            linked.symlink_to(tmp_path, target_is_directory=True)
            source = linked / source.name
        elif target == "hardlink":
            os.link(source, linked)
            source = linked
        else:
            linked.symlink_to(review if target == "review" else source)
            if target == "review":
                review = linked
            else:
                source = linked
    except OSError:
        pytest.skip("filesystem link creation unavailable")
    private = tmp_path / "private"
    with pytest.raises(f.FileImportError):
        execute(source, review, private)
    assert not private.exists()


def test_private_state_cannot_overlap_input_or_product(tmp_path):
    """Catches raw owner input accidentally retained under the private state directory."""
    source, review = inputs(tmp_path)
    for destination in (tmp_path, f.workflow.PRODUCT_ROOT / "refused-file-state"):
        with pytest.raises(f.FileImportError, match="file_private_directory_refused"):
            execute(source, review, destination)
    assert not (tmp_path / "derived.sqlite3").exists()


def test_hardlinked_state_key_refuses_before_database_creation(tmp_path):
    """Catches private-state admission modifying an external file through a hardlink."""
    source, review = inputs(tmp_path)
    private = tmp_path / "private"
    private.mkdir()
    outside = tmp_path / "external-identity.bin"
    outside.write_bytes(b"x" * 32)
    try:
        os.link(outside, private / "identity.key")
    except OSError:
        pytest.skip("filesystem hardlink creation unavailable")
    with pytest.raises(f.FileImportError, match="file_private_directory_refused") as error:
        execute(source, review, private)
    assert error.value.private_effects_possible is False
    assert outside.read_bytes() == b"x" * 32
    assert not (private / "derived.sqlite3").exists()


@pytest.mark.parametrize("missing", ["posting", "review"])
def test_absent_owner_input_is_an_error_without_empty_success(tmp_path, missing):
    """Catches a missing input/review being silently treated as a successfully empty posting."""
    source, review = inputs(tmp_path)
    (source if missing == "posting" else review).unlink()
    private = tmp_path / "private"
    with pytest.raises(f.FileImportError) as error:
        execute(source, review, private)
    assert error.value.private_effects_possible is False
    assert not private.exists()


def test_retry_stable_identity_and_changed_source_refuses_prior_record(tmp_path):
    """Catches regenerated IDs, duplicate records or overwriting a registered source revision."""
    source, review = inputs(tmp_path)
    private = tmp_path / "private"
    execute(source, review, private)
    before, key = rows(private), (private / "identity.key").read_bytes()
    execute(source, review, private)
    assert rows(private) == before and (private / "identity.key").read_bytes() == key
    source.write_text(TEXT + "\nRequirements: Rust", encoding="utf-8")
    with pytest.raises(f.FileImportError, match="source_changed_requires_successor") as error:
        execute(source, review, private)
    assert error.value.private_effects_possible is True
    assert rows(private) == before
    with pytest.raises(f.FileImportError, match="source_changed_requires_successor"):
        execute(source, review, private, month="2026-09")
    assert rows(private) == before


def test_state_failure_is_closed_and_retry_does_not_invent_accepted_record(tmp_path, monkeypatch):
    """Catches classifier failure reported as success or raw exception payloads in CLI output."""
    source, review = inputs(tmp_path)
    private = tmp_path / "private"

    def failed(*args, **kwargs):
        raise RuntimeError(TEXT + str(source))

    with monkeypatch.context() as scoped:
        scoped.setattr(f.rules, "classify_and_store", failed)
        with pytest.raises(f.FileImportError, match="file_import_failed_or_cancelled") as error:
            execute(source, review, private)
    assert error.value.private_effects_possible is True
    assert COMPANY not in str(error.value) and str(source) not in str(error.value)
    mappings, payloads = rows(private)
    assert len(mappings) == 1 and payloads == []
    execute(source, review, private)
    assert len(rows(private)[1]) == 1


@pytest.mark.parametrize("fail", [False, True])
def test_transient_text_is_cleared_after_success_or_failure(tmp_path, monkeypatch, fail):
    """Catches retained posting/envelope references after the private write path exits."""
    source, review = inputs(tmp_path)
    captured = []
    original = f.redaction.prepare_synthetic

    def prepare(post, **kwargs):
        result = original(post, **kwargs)
        captured.append((post, result.envelope))
        return result

    def failed(*args, **kwargs):
        raise RuntimeError("synthetic_failure")

    monkeypatch.setattr(f.redaction, "prepare_synthetic", prepare)
    if fail:
        monkeypatch.setattr(f.rules, "classify_and_store", failed)
        with pytest.raises(f.FileImportError):
            execute(source, review, tmp_path / "private")
    else:
        execute(source, review, tmp_path / "private")
    assert len(captured) == 1
    assert captured[0][0].text == captured[0][1].text == ""


def test_other_method_state_is_preserved_and_field_errors_stay_errors(tmp_path):
    """Catches clobbered method records or invalid salary parsing silently turning into absence."""
    source, review = inputs(tmp_path, text=TEXT + "\nSalary: USD0/year")
    private = tmp_path / "private"
    execute(source, review, private)
    record = c.PrivateDerivedRecord.model_validate_json(rows(private)[1][0][0])
    assert record.classification.salary.normalization_status == "error"
    assert record.classification.salary.presence.process_status == "error"
    assert record.classification.salary.presence.evidence_state == "unavailable"
    with sqlite3.connect(private / "derived.sqlite3") as connection:
        payload = record.model_dump(mode="json")
        payload.update(method="jev", model_sha256="a" * 64)
        connection.execute("UPDATE records SET payload=?", (json.dumps(payload),))
    before = rows(private)
    with pytest.raises(f.FileImportError, match="other_method_state_requires_separate_run"):
        execute(source, review, private)
    assert rows(private) == before


def test_cli_requires_synthetic_declaration_and_never_echoes_rejected_arguments(tmp_path, capsys):
    """Catches default real-data permission or argparse leaking an owner-selected path."""
    source, review = inputs(tmp_path)
    private = tmp_path / "private"
    args = cli_args(source, review, private)
    args.remove("--synthetic-only")
    assert main(args) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err) == {
        "code": "explicit_synthetic_only_required",
        "private_effects_possible": False,
    }
    assert not private.exists()
    with pytest.raises(SystemExit) as error:
        main([*args, "--unexpected", str(source)])
    assert error.value.code == 2
    captured = capsys.readouterr()
    assert str(source) not in captured.out + captured.err
