"""Few original wiring controls, not the required independent60/four-month corpus or Gold."""

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from hiring_signals import contracts as c
from hiring_signals import workflow as w
from hiring_signals.ingest.private_state import PrivateState
from hiring_signals.ingest.transport import month_title
from hiring_signals.reporting.render import verify_report
from hiring_signals.shared.aggregate_privacy.models import POLICY_V2

ROOT = Path(__file__).parents[2]
MONTHS = ("2026-07", "2026-08", "2026-09", "2026-10")
COMPANY = "ORIGINAL_COMPANY_CANARY_943"
AUTHOR = "ORIGINAL_AUTHOR_CANARY_729"
KEY = "SYNTHETIC_ENV_CANARY_NOT_A_REAL_KEY_442"


def document():
    # Four original API wiring records only. No reference labels/generator/split
    # or learned-model outputs, and no substitute for the independent required set.
    result = {"schema_version": 1, "origin": "original_synthetic", "months": []}
    for index, month in enumerate(MONTHS):
        source_id, root_id = 200000 + index, 100000 + index
        text = (
            COMPANY + "\nDuties: build ML systems\nRequirements: Python\n"
            "Application instructions: send resume only\nSalary: USD100 per fortnight"
        )
        result["months"].append(
            {
                "month": month,
                "root_id": root_id,
                "origin": f"https://hn.algolia.com/api/v1/items/{root_id}",
                "response": {
                    "id": root_id,
                    "type": "story",
                    "title": month_title(month),
                    "children": [
                        {"id": source_id, "type": "comment", "text": text, "author": AUTHOR}
                    ],
                },
                "reviews": [
                    {
                        "source_id": source_id,
                        "identities_reviewed": True,
                        "identity_terms": [COMPANY],
                        "organization": COMPANY,
                        "link_kinds": [],
                    }
                ],
            }
        )
    return result


def write_input(tmp_path, data=None):
    path = tmp_path / "original-source.json"
    path.write_text(json.dumps(document() if data is None else data), encoding="utf-8")
    return path


def run_cli(tmp_path, *args):
    guards = tmp_path / "guard"
    guards.mkdir(exist_ok=True)
    (guards / "sitecustomize.py").write_text(
        "import socket\n"
        "def blocked(*a,**k):raise AssertionError('network_forbidden')\n"
        "socket.create_connection=blocked\nsocket.socket.connect=blocked\n"
    )
    environment = {
        **os.environ,
        "PYTHONPATH": str(guards) + os.pathsep + str(ROOT / "src"),
        "OPENAI_API_KEY": KEY,
        "TYPESAFE_API_KEY": KEY,
    }
    return subprocess.run(
        [sys.executable, "-m", "hiring_signals", *map(str, args)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def run_args(source, private, output):
    return (
        "run-synthetic",
        "--input",
        source,
        "--private-dir",
        private,
        "--out",
        output,
        "--lease-seconds",
        "30",
        "--policy",
        "v2",
    )


def payloads(private):
    with sqlite3.connect(private / "derived.sqlite3") as connection:
        return connection.execute("SELECT item_id,payload FROM records ORDER BY item_id").fetchall()


def test_actual_keyless_cli_rules_private_state_fourmonth_report_and_public_verifier(tmp_path):
    """Catches disconnected CLI wiring or raw identities/text leaking to durable outputs."""
    source = write_input(tmp_path)
    private, output = tmp_path / "private", tmp_path / "report"
    run = run_cli(tmp_path, *run_args(source, private, output))
    assert run.returncode == 0, run.stderr
    result = json.loads(run.stdout)
    assert result["status"] == "outcomes_complete" and result["complete_workflow"] is False
    assert (
        result["required_independent_fixture_gold"] == "pending" and result["provider_calls"] == 0
    )
    assert KEY not in run.stdout + run.stderr
    rows = payloads(private)
    assert len(rows) == 4
    for _, payload in rows:
        record = c.PrivateDerivedRecord.model_validate_json(payload)
        assert record.method == "rules" and record.model_sha256 is None
        assert record.classification.ai_engineering_role.value is True
        assert record.classification.portfolio_requested.value is False
        assert record.classification.skills.python.value is True
        assert record.classification.salary.normalization_status == "abstained"
    report = verify_report(output)
    assert report.month_ids == MONTHS and all(m.eligible_denominator is None for m in report.months)
    public_bytes = b"".join(p.read_bytes() for p in output.iterdir())
    persisted = (private / "derived.sqlite3").read_bytes()
    for marker in (COMPANY, AUTHOR, KEY, "Duties: build ML systems"):
        assert marker.encode() not in public_bytes + persisted
    assert all(item.encode() not in public_bytes for item, _ in rows)
    verified = run_cli(tmp_path, "report", "verify", "--directory", output)
    assert (
        verified.returncode == 0
        and json.loads(verified.stdout)["recipient_delivery"] == "not_established"
    )
    copied = tmp_path / "report-copy"
    exported = run_cli(
        tmp_path, "report", "export", "--input", output / "aggregates.json", "--out", copied
    )
    assert exported.returncode == 0, exported.stderr
    assert (copied / "aggregates.json").read_bytes() == (output / "aggregates.json").read_bytes()


def test_repeat_run_preserves_source_file_prior_report_and_stable_private_ids(tmp_path):
    """Catches destructive refreshes or regenerated identities when reusing actual private state."""
    source = write_input(tmp_path)
    original = source.read_bytes()
    private, output = tmp_path / "private", tmp_path / "report"
    w.execute_rules(
        source, private_directory=private, destination=output, lease_seconds=30, policy=POLICY_V2
    )
    ids = [item for item, _ in payloads(private)]
    old_report = (output / "aggregates.json").read_bytes()
    w.execute_rules(
        source,
        private_directory=private,
        destination=tmp_path / "next-report",
        lease_seconds=30,
        policy=POLICY_V2,
    )
    assert ids == [item for item, _ in payloads(private)]
    assert (
        source.read_bytes() == original and (output / "aggregates.json").read_bytes() == old_report
    )


@pytest.mark.parametrize(
    "fault",
    ["origin", "month_count", "thread", "duplicate_id", "review", "extra", "nonconsecutive"],
)
def test_invalid_manifest_refused_before_private_state_or_report_creation(tmp_path, fault):
    """Catches ungranted modes, invalid source grouping or defaults creating partial state."""
    data = document()
    if fault == "origin":
        data["origin"] = "real_corpus_not_authorized"
    elif fault == "month_count":
        data["months"].pop()
    elif fault == "thread":
        data["months"][0]["response"]["title"] = "wrong PRIVATE_CANARY_991"
    elif fault == "duplicate_id":
        data["months"][1]["response"]["children"][0]["id"] = 200000
        data["months"][1]["reviews"][0]["source_id"] = 200000
    elif fault == "review":
        data["months"][0]["reviews"][0]["identity_terms"] = []
    elif fault == "nonconsecutive":
        data["months"][0]["month"] = "2026-06"
        data["months"][0]["response"]["title"] = month_title("2026-06")
    else:
        data["source_text"] = "PRIVATE_CANARY_991"
    source = write_input(tmp_path, data)
    private, output = tmp_path / "private", tmp_path / "report"
    run = run_cli(tmp_path, *run_args(source, private, output))
    assert run.returncode == 2 and run.stdout == ""
    error = json.loads(run.stderr)
    assert error["private_effects_possible"] is False
    assert "PRIVATE_CANARY_991" not in run.stderr
    assert not private.exists() and not output.exists()


def test_duplicate_json_keys_and_existing_output_are_refused_without_side_effects(tmp_path):
    """Catches duplicate-key reinterpretation or overwriting an owner-selected directory."""
    source = write_input(tmp_path)
    source.write_text(
        source.read_text().replace(
            '"schema_version": 1', '"schema_version": 1, "schema_version": 1'
        )
    )
    private, output = tmp_path / "private", tmp_path / "report"
    run = run_cli(tmp_path, *run_args(source, private, output))
    assert run.returncode == 2 and not private.exists() and not output.exists()
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("original-owner-content")
    run = run_cli(tmp_path, *run_args(source, private, output))
    assert run.returncode == 2 and json.loads(run.stderr)["code"] == "output_already_exists"
    assert sentinel.read_text() == "original-owner-content" and not private.exists()


def test_missing_identity_review_stays_in_every_expected_denominator(tmp_path):
    """Catches a privacy-quarantined posting disappearing from monthly accounting."""
    data = document()
    data["months"][0]["reviews"] = []
    source = write_input(tmp_path, data)
    captured = []
    actual = w.pop.aggregate_month

    def spy(cohort):
        captured.append(cohort)
        return actual(cohort)

    with patch.object(w.pop, "aggregate_month", side_effect=spy):
        result = w.execute_rules(
            source,
            private_directory=tmp_path / "private",
            destination=tmp_path / "report",
            lease_seconds=30,
            policy=POLICY_V2,
        )
    assert result["status"] == "partial"
    assert len(captured[0].expected_ids) == 1 and captured[0].records == ()
    assert captured[0].missing_status == "blocked"
    public = verify_report(tmp_path / "report").months[0]
    assert public.method_status == "partial" and len(public.partitions) == 37
    assert len(payloads(tmp_path / "private")) == 3


def test_oversized_month_never_becomes_a_successful_600_post_prefix(tmp_path):
    """Catches rendering a bounded prefix as a fully acquired month."""
    data = document()
    data["months"][0]["response"]["children"] = [
        {"id": 300000 + i, "type": "comment", "text": "Original boundary control"}
        for i in range(601)
    ]
    source = write_input(tmp_path, data)
    result = w.execute_rules(
        source,
        private_directory=tmp_path / "private",
        destination=tmp_path / "report",
        lease_seconds=30,
        policy=POLICY_V2,
    )
    assert result["status"] == "partial"
    month = verify_report(tmp_path / "report").months[0]
    assert month.source_coverage == "partial" and month.eligible_denominator is None
    assert len(payloads(tmp_path / "private")) == 3


def test_empty_source_run_is_not_a_successful_prediction_or_quality_benchmark(tmp_path):
    """Catches an empty four-month fixture advertised as a successful prediction run."""
    data = document()
    for month in data["months"]:
        month["response"]["children"] = []
        month["reviews"] = []
    source = write_input(tmp_path, data)
    run = run_cli(tmp_path, *run_args(source, tmp_path / "private", tmp_path / "report"))
    assert run.returncode == 3 and json.loads(run.stdout)["status"] == "no_eligible_input"
    assert payloads(tmp_path / "private") == []
    assert all(m.eligible_denominator is None for m in verify_report(tmp_path / "report").months)


def test_other_method_state_is_preserved_before_any_rule_overwrite(tmp_path):
    """Catches the current single-record-per-item store erasing another method's raw output."""
    source = write_input(tmp_path)
    private = tmp_path / "private"
    w.execute_rules(
        source,
        private_directory=private,
        destination=tmp_path / "report",
        lease_seconds=30,
        policy=POLICY_V2,
    )
    state = PrivateState(private, product_root=ROOT)
    try:
        lease = state.begin(lease_seconds=30)
        original = state.read_records(lease=lease)[0]
        # Explicit authored foreign-method control, not an actual model output.
        foreign = original.model_copy(update={"method": "generative", "model_sha256": "f" * 64})
        state.write_record(foreign, lease=lease)
    finally:
        state.close()
    before = payloads(private)
    with pytest.raises(w.WorkflowError, match="other_method_state"):
        w.execute_rules(
            source,
            private_directory=private,
            destination=tmp_path / "next",
            lease_seconds=30,
            policy=POLICY_V2,
        )
    assert payloads(private) == before and not (tmp_path / "next").exists()


def test_late_failure_acknowledges_private_partial_effects_without_creating_report(
    tmp_path, monkeypatch
):
    """Catches failed batches falsely claiming rollback of prior committed private records."""
    source = write_input(tmp_path)
    actual = w.rules.classify_and_store
    calls = []

    def fail_after_first(*args, **kwargs):
        calls.append(True)
        if len(calls) == 2:
            raise RuntimeError("PRIVATE_CANARY_398")
        return actual(*args, **kwargs)

    monkeypatch.setattr(w.rules, "classify_and_store", fail_after_first)
    with pytest.raises(w.WorkflowError) as caught:
        w.execute_rules(
            source,
            private_directory=tmp_path / "private",
            destination=tmp_path / "report",
            lease_seconds=30,
            policy=POLICY_V2,
        )
    assert caught.value.private_effects_possible and "PRIVATE_CANARY_398" not in str(caught.value)
    assert len(payloads(tmp_path / "private")) == 1 and not (tmp_path / "report").exists()


def test_public_verification_refuses_extra_files_and_tampering(tmp_path):
    """Catches a safe manifest used to endorse an unsafe extra-file directory or changed HTML."""
    source = write_input(tmp_path)
    output = tmp_path / "report"
    w.execute_rules(
        source,
        private_directory=tmp_path / "private",
        destination=output,
        lease_seconds=30,
        policy=POLICY_V2,
    )
    extra = output / "unexpected.txt"
    extra.write_text("original-nonsecret-extra-control")
    with pytest.raises(w.WorkflowError, match="verification_failed"):
        w.verify_public_report(output)
    extra.unlink()
    html = output / "report.html"
    html.write_bytes(html.read_bytes() + b"changed")
    run = run_cli(tmp_path, "report", "verify", "--directory", output)
    assert run.returncode == 2 and run.stdout == ""
    assert json.loads(run.stderr)["code"] == "public_report_verification_failed"


def test_invalid_closed_public_input_and_private_agent_paths_are_not_exported(tmp_path):
    """Catches arbitrary source/credential/export payloads treated as a public report."""
    source = tmp_path / "invalid.json"
    source.write_text('{"source_text":"PRIVATE_CANARY_911"}')
    run = run_cli(tmp_path, "report", "export", "--input", source, "--out", tmp_path / "report")
    assert run.returncode == 2 and "PRIVATE_CANARY_911" not in run.stderr
    assert not (tmp_path / "report").exists()
    blocked = tmp_path / ".chatexports"
    blocked.mkdir()
    path = blocked / "not-a-product-input.json"
    path.write_text("original fake file; must not be read")
    with patch.object(Path, "open", side_effect=AssertionError("unexpected read")):
        with pytest.raises(w.WorkflowError, match="input_file_refused"):
            w.bounded_json_file(path, maximum=1000)
