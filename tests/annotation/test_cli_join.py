"""Opt-in original synthetic DEV controls; no Human/Gold/quality evidence.

Set HST_ANNOTATION_CONTROLS to the explicitly granted outer control directory.
Source/identity canaries and journals stay there or in an outside-checkout basetemp.
Failure injection below is labelled simulation, separate from real journal IO.
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from hiring_signals import contracts as c
from hiring_signals.adapters.rulings import AnnotationJournal, SourceAuthority
from hiring_signals.annotation import workflow as w
from hiring_signals.annotation.models import Actor, AppendReceipt
from hiring_signals.annotation.session import AnnotationSession
from hiring_signals.shared.rulings.store import JournalStore


@pytest.fixture(scope="session")
def controls():
    value = os.environ.get("HST_ANNOTATION_CONTROLS")
    if not value:
        pytest.skip("requires explicitly admitted outer original-synthetic controls")
    root = Path(value)
    metadata = json.loads((root / "controls.json").read_bytes())
    data = tuple((root / name).read_bytes() for name in ("control-1.txt", "control-2.txt"))
    assert [hashlib.sha256(body).hexdigest() for body in data] == metadata["source_hashes"]
    assert sum(map(len, data)) < 262144
    return data, metadata


def setup_case(tmp_path, controls):
    data, metadata = controls
    assert not tmp_path.resolve().is_relative_to(w.PRODUCT_ROOT)
    source = tmp_path / "source.txt"
    source.write_bytes(data[0])
    owner, actor = metadata["owner_ref"], metadata["actor_ref"]
    manifest = {
        "kind": "synthetic-dev-annotation/1",
        "origin": "original_synthetic",
        "split": "dev",
        "owner_ref": owner,
        "actor": {"origin": "agent_provisional", "actor_ref": actor, "attestation_ref": None},
        "bindings": w.bindings(),
        "source_file": "source.txt",
        "source": w.source_pin(data[0], owner).model_dump(mode="json"),
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    journal = tmp_path / "journal"
    journal.mkdir()
    (journal / "owner.json").write_text(
        json.dumps(
            {
                "kind": "synthetic-dev-annotation-owner/1",
                "owner_ref": owner,
                "actor_ref": actor,
            }
        ),
        encoding="utf-8",
    )
    return path, journal, manifest


def options(case):
    path, journal, _ = case
    return {
        "manifest_path": path,
        "manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "journal_directory": journal,
    }


def choices():
    result = {field: "a" for field in c.FIELD_IDS}
    result.update(
        {
            "ai_engineering_role": "n",
            "seniority": "u",
            "skills.python": "n",
            "salary": "none",
            "location_stated": "n",
        }
    )
    return list(result.values())


def execute(case, answers):
    iterator, output = iter(answers), []

    def reader(prompt):
        output.append(prompt)
        try:
            return next(iterator)
        except StopIteration:
            raise EOFError from None

    return w.execute(**options(case), reader=reader, writer=output.append), output


def no_leak(controls, *values):
    _, metadata = controls
    data = b"\n".join(x if isinstance(x, bytes) else str(x).encode() for x in values)
    for canary in metadata["canaries"]:
        assert canary.encode() not in data


def cli_run(case, answers, tmp_path, *, sha=None, extra=()):
    path, journal, _ = case
    guard = """
import sys
def audit(event, args):
    if event.startswith('socket.') or event in {'subprocess.Popen','os.system'}:
        raise RuntimeError('outbound_or_child_refused')
    if event == 'open' and isinstance(args[0], (str, bytes)):
        p = str(args[0]).lower().replace(chr(92), '/')
        denied = ['.creds','.thinking','.chatexports','.agent-registry','heldout']
        if any('/'+part+'/' in p for part in denied):
            raise RuntimeError('protected_input_refused')
sys.addaudithook(audit)
from hiring_signals.cli import main
raise SystemExit(main(sys.argv[1:]))
"""
    allowed = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC"}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env.update(PYTHONPATH=str(w.PRODUCT_ROOT / "src"), PYTHONDONTWRITEBYTECODE="1")
    argv = [
        sys.executable,
        "-B",
        "-c",
        guard,
        "annotate",
        "--manifest",
        str(path),
        "--manifest-sha256",
        sha or options(case)["manifest_sha256"],
        "--journal-dir",
        str(journal),
        *extra,
    ]
    completed = subprocess.run(
        argv,
        input="\n".join(answers) + "\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=30,
    )
    (tmp_path / "cli.stdout").write_text(completed.stdout, encoding="utf-8")
    (tmp_path / "cli.stderr").write_text(completed.stderr, encoding="utf-8")
    (tmp_path / "cli-command.json").write_text(
        json.dumps(
            {
                "argv": argv,
                "exit": completed.returncode,
                "systemroot_present": any(key.upper() == "SYSTEMROOT" for key in env),
            }
        ),
        encoding="utf-8",
    )
    return completed


def test_actual_cli_all_explicit_fields_private_durable_and_reprompt(tmp_path, controls):
    """Catches fake journal success, false/absence conflation, auto-filled '?' or text echo."""
    case = setup_case(tmp_path, controls)
    run = cli_run(case, ["?", controls[1]["canaries"][0], *choices()], tmp_path)
    assert run.returncode == 0
    result = json.loads(run.stdout)
    assert result["status"] == "owner_receipts_complete"
    assert result["durable_receipts"] == result["durable_acknowledgments_this_process"] == 37
    assert result["human_authenticated"] is result["human_gold_eligible"] is False
    assert "field_unlabelled_choose_or_skip" in run.stderr and "invalid_label_choice" in run.stderr
    events = [json.loads(line) for line in (case[1] / "rulings.jsonl").read_bytes().splitlines()]
    assert len(events) == 37
    journal = open_journal(case, controls)
    pin = w.source_pin(controls[0][0], case[2]["owner_ref"])
    assert journal.head(pin.item_id, "ai_engineering_role").effective.value is False
    assert journal.head(pin.item_id, "portfolio_requested").effective.presence == "absent"
    assert journal.head(pin.item_id, "seniority").effective.value == "not_stated"
    no_leak(controls, run.stdout, run.stderr, (case[1] / "rulings.jsonl").read_bytes())


@pytest.mark.parametrize(
    "fault",
    [
        "hash",
        "malformed",
        "duplicate",
        "pin",
        "rubric",
        "human",
        "heldout",
        "prefill",
        "owner",
        "source_path",
    ],
)
def test_actual_cli_refuses_before_journal_mutation(tmp_path, controls, fault):
    """Catches validation after opening state, implicit authority or rejected input echo."""
    case = setup_case(tmp_path, controls)
    path, journal, manifest = case
    sha = None
    if fault == "hash":
        sha = "0" * 64
    elif fault == "pin":
        manifest["source"]["evidence_revision_sha256"] = "0" * 64
    elif fault == "rubric":
        manifest["bindings"]["rubric_sha256"] = "0" * 64
    elif fault == "human":
        manifest["actor"].update(origin="human_self_attested", attestation_ref="a" * 64)
    elif fault == "heldout":
        manifest["split"] = "heldout"
    elif fault == "prefill":
        manifest["prefill"] = controls[1]["canaries"][0]
    elif fault == "owner":
        manifest["owner_ref"] = "0" * 64
        manifest["source"] = w.source_pin(controls[0][0], "0" * 64).model_dump(mode="json")
    elif fault == "source_path":
        manifest["source_file"] = "../source.txt"
    if fault != "hash":
        raw = json.dumps(manifest)
        if fault == "malformed":
            raw = "{"
        elif fault == "duplicate":
            raw = raw[:-1] + ', "split":"dev"}'
        path.write_text(raw, encoding="utf-8")
    before = sorted(p.name for p in journal.iterdir())
    run = cli_run(case, [], tmp_path, sha=sha)
    assert run.returncode == 2 and not run.stdout
    error = json.loads(run.stderr)
    assert (
        not error["private_effects_possible"] and error["durable_acknowledgments_this_process"] == 0
    )
    assert sorted(p.name for p in journal.iterdir()) == before == ["owner.json"]
    no_leak(controls, run.stderr)


@pytest.mark.parametrize("stop", ["q", "skip", None])
def test_cancel_skip_eof_before_submit_has_no_journal_effect(tmp_path, controls, stop):
    """Catches persisting a draft or pretending cancellation rolled back prior events."""
    case = setup_case(tmp_path, controls)
    result, output = execute(case, choices()[:3] + ([] if stop is None else [stop]))
    assert result["status"] == ("skipped" if stop == "skip" else "cancelled")
    assert result["accepted_receipts"] == 0 and not result["private_effects_possible"]
    assert sorted(p.name for p in case[1].iterdir()) == ["owner.json"]
    no_leak(controls, output)


@pytest.mark.parametrize("target", ["missing", "checkout"])
def test_unowned_or_product_target_refuses_without_creation(tmp_path, controls, target):
    """Catches creating target state as a side effect of discovering missing ownership."""
    case = setup_case(tmp_path, controls)
    bad = tmp_path / "missing" if target == "missing" else w.PRODUCT_ROOT
    opts = options(case) | {"journal_directory": bad}
    with pytest.raises(w.AnnotationError) as error:
        w.execute(**opts, reader=lambda _: "a", writer=lambda _: None)
    assert not error.value.private_effects_possible
    if target == "missing":
        assert not bad.exists()


def test_changed_source_during_draft_refuses_without_label_write(tmp_path, controls):
    """Catches trusting the initially installed pin after on-disk source replacement."""
    case = setup_case(tmp_path, controls)

    def changed(_):
        (tmp_path / "source.txt").write_bytes(controls[0][1])
        return "n"

    with pytest.raises(w.AnnotationError) as error:
        w.execute(**options(case), reader=changed, writer=lambda _: None)
    assert not error.value.private_effects_possible
    assert not (case[1] / "rulings.jsonl").exists()


def open_journal(case, controls):
    source = c.TransientInput(
        input_sha256=case[2]["source"]["input_sha256"], text=controls[0][0].decode()
    )
    sources = SourceAuthority()
    sources.install(w.source_pin(controls[0][0], case[2]["owner_ref"]), source)
    return AnnotationJournal(case[1], product_root=w.PRODUCT_ROOT, sources=sources)


def test_actual_cas_conflict_preserves_competing_write(tmp_path, controls, monkeypatch):
    """Catches silently advancing a stale draft over a concurrent owner's current head."""
    case = setup_case(tmp_path, controls)
    original = AnnotationJournal.submit

    def compete(journal, command):
        other = command.model_copy(update={"event_id": "1" * 64})
        journal.append(other)
        return original(journal, command)

    monkeypatch.setattr(AnnotationJournal, "submit", compete)
    result, _ = execute(case, choices())
    assert result["status"] == "conflict" and result["durable_receipts"] == 0
    assert len(JournalStore(case[1]).replay().events) == 1


@pytest.mark.parametrize("retry", [False, True])
def test_injected_ambiguous_fsync_retains_prefix_and_exact_retry(
    tmp_path, controls, monkeypatch, retry
):
    """Simulated one fsync failure with real IO; not power-loss durability certification."""
    case = setup_case(tmp_path, controls)
    original, failed = JournalStore._sync, []

    def once(store, descriptor):
        # Replay also fsyncs existing history: select the third written event,
        # not a guessed number of internal _sync calls.
        if not failed and store.path.read_bytes().count(b"\n") == 3:
            failed.append(True)
            raise OSError(controls[1]["canaries"][1])
        return original(store, descriptor)

    monkeypatch.setattr(JournalStore, "_sync", once)
    result, output = execute(case, choices() + (["retry"] if retry else ["q"]))
    events = JournalStore(case[1]).replay().events
    if retry:
        assert result["status"] == "owner_receipts_complete"
        assert result["durable_receipts"] == len(events) == 37
        assert len({event.event_id for event in events}) == 37
    else:
        assert result["status"] == "unknown"
        assert result["durable_receipts"] == result["durable_acknowledgments_this_process"] == 2
        assert len(events) == 3  # third write exists but was never falsely acknowledged
    no_leak(controls, output, result, (case[1] / "rulings.jsonl").read_bytes())


def test_corrupt_backend_preserved_not_repaired(tmp_path, controls):
    """Catches overwriting a torn journal to report a fresh successful annotation."""
    case = setup_case(tmp_path, controls)
    journal = case[1] / "rulings.jsonl"
    journal.write_bytes(b"{")
    with pytest.raises(w.AnnotationError) as error:
        execute(case, choices())
    assert error.value.private_effects_possible and error.value.durable_acknowledgments == 0
    assert journal.read_bytes() == b"{"


def test_injected_backend_unavailable_preserves_acknowledged_prefix(
    tmp_path, controls, monkeypatch
):
    """Typed failure injection, not a fabricated durable backend or whole-batch rollback."""
    case = setup_case(tmp_path, controls)
    original, calls = AnnotationJournal.submit, []

    def unavailable(journal, command):
        calls.append(command)
        if len(calls) == 3:
            return AppendReceipt(
                event_id=command.event_id,
                status="unavailable",
                origin="owner_runtime",
                sequence=None,
                durable=False,
            )
        return original(journal, command)

    monkeypatch.setattr(AnnotationJournal, "submit", unavailable)
    result, _ = execute(case, choices() + ["q"])
    assert result["status"] == "partial" and result["durable_receipts"] == 2
    assert len(JournalStore(case[1]).replay().events) == 2


def test_linked_source_rejected_without_journal_effect(tmp_path, controls):
    """Catches following hard-linked input despite a matching source digest."""
    case = setup_case(tmp_path, controls)
    os.link(tmp_path / "source.txt", tmp_path / "alias.txt")
    with pytest.raises(w.AnnotationError) as error:
        execute(case, choices())
    assert not error.value.private_effects_possible
    assert sorted(p.name for p in case[1].iterdir()) == ["owner.json"]


def test_actual_restart_reopen_and_historical_retry_no_current_authority(tmp_path, controls):
    """Catches treating a historical exact receipt as current source or revived old label."""
    case = setup_case(tmp_path, controls)
    result, _ = execute(case, choices())
    assert result["durable_receipts"] == 37
    journal = open_journal(case, controls)
    pin = w.source_pin(controls[0][0], case[2]["owner_ref"])
    source = c.TransientInput(input_sha256=pin.input_sha256, text=controls[0][0].decode())
    active = AnnotationSession(
        source=source,
        pin=pin,
        actor=Actor.model_validate(case[2]["actor"]),
        split="dev",
        current_source=lambda: pin,
        head=lambda field: journal.head(pin.item_id, field),
        submit=journal.submit,
    )
    assert active.reopen("skills.python").status == "incomplete"
    assert journal.head(pin.item_id, "skills.python").effective is None
    # New process-equivalent adapter replays actual history after reinstalling source.
    restarted = open_journal(case, controls)
    assert restarted.head(pin.item_id, "skills.python").effective is None
    active.choose("skills.python", "n")
    command = active._intent("skills.python")
    receipt = restarted.append(command)
    restarted.sources.remove(pin.item_id)
    exact = restarted.append(command)
    assert exact.historical and exact.sequence == receipt.sequence
    assert not exact.current_generation_authority
    assert restarted.head(pin.item_id, "skills.python").effective is None
    no_leak(controls, restarted.store.path.read_bytes())


def test_cli_rejected_arguments_never_echo_identity(tmp_path, controls):
    """Catches argparse leaking private arguments before the closed workflow can handle them."""
    case = setup_case(tmp_path, controls)
    run = cli_run(case, [], tmp_path, extra=("--human", controls[1]["canaries"][1]))
    assert run.returncode == 2
    no_leak(controls, run.stdout, run.stderr)
    assert not (case[1] / "rulings.jsonl").exists()
