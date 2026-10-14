"""Original synthetic bound/retry controls; no network behavior or rights claims."""

import json
import pickle
from pathlib import Path

import pytest

from hiring_signals.ingest import transport as t

ROOT = Path(__file__).resolve().parents[2]
ORIGIN = "https://hn.algolia.com/api/v1/items/900001"


def fixture():
    return json.loads((ROOT / "fixtures/transport/october-original.json").read_text())


def read(data=None, **changes):
    args = {
        "body": json.dumps(data if data is not None else fixture()).encode(),
        "origin": ORIGIN,
        "root_id": 900001,
        "month": "2026-10",
    }
    args.update(changes)
    return t.read_synthetic_response(**args)


def test_original_local_fixture_accounts_all_top_level_and_drops_authors():
    """Catches deleted/dead/empty rows disappearing and by/author leaking into processing."""
    result = read()
    assert result.coverage.status == "complete"
    assert (
        result.coverage.top_level,
        result.coverage.accepted,
        result.coverage.deleted,
        result.coverage.dead,
        result.coverage.empty,
    ) == (4, 1, 1, 1, 1)
    assert not hasattr(result.posts[0], "by")
    assert not hasattr(result.posts[0], "author")
    assert "Canary" not in repr(result)
    for value in (result, result.posts[0]):
        with pytest.raises(TypeError):
            pickle.dumps(value)
        with pytest.raises(TypeError):
            json.dumps(value)


@pytest.mark.parametrize(
    "origin",
    [
        "http://hn.algolia.com/api/v1/items/900001",
        "https://hn.algolia.com.evil.invalid/api/v1/items/900001",
        "https://hn.algolia.com/api/v1/items/900001?redirect=x",
        "https://127.0.0.1/900001",
        "https://hn.algolia.com/api/v1/items/900002",
        "https://hn.algolia.com/api/v1/items/0900001",
    ],
)
def test_wrong_origin_rejected_without_fetch(origin):
    """Catches alternate hosts/schemes/roots/query redirects admitted as the allowed origin."""
    with pytest.raises(t.IngestError, match="^wrong_origin$"):
        read(origin=origin)


@pytest.mark.parametrize(
    "change",
    [
        {"id": 900002},
        {"id": True},
        {"type": "comment"},
        {"title": "Ask HN: Who wants to be hired? (October 2026)"},
        {"title": "Ask HN: Freelancer? (October 2026)"},
        {"title": "Ask HN: Who is hiring? (September 2026)"},
    ],
)
def test_root_thread_month_identity_mismatch(change):
    """Catches same-author wrong thread or requested-month mismatch accepted as hiring data."""
    data = fixture()
    data.update(change)
    with pytest.raises(t.IngestError):
        read(data)


def test_month_inventory_and_boundary():
    """Catches more than four months, duplicates and malformed months in one run."""
    t.validate_months(("2026-07", "2026-08", "2026-09", "2026-10"))
    for months in (
        (),
        ("2026-10",) * 2,
        ("2026-01", "2026-02", "2026-03", "2026-04", "2026-05"),
        ("2026-13",),
        ("2026-1",),
    ):
        with pytest.raises(t.IngestError):
            t.validate_months(months)


def test_top_level_600_boundary_and_oversize_no_prefix_complete():
    """Catches the first600 of601 being silently marked complete."""
    data = fixture()
    sample = data["children"][0]
    data["children"] = [{**sample, "id": 1000000 + i} for i in range(600)]
    assert read(data).coverage.accepted == 600
    data["children"].append({**sample, "id": 2000000})
    result = read(data)
    assert result.coverage.status == "partial" and not result.posts
    assert result.coverage.top_level == 601


def test_response_bytes_exact_limit_and_overflow():
    """Catches a byte limit treated as characters or an oversize response accepted partially."""
    body = json.dumps(fixture()).encode()
    padded = body + b" " * (t.MAX_RESPONSE_BYTES - len(body))
    assert read(body=padded).coverage.status == "complete"
    result = read(body=padded + b" ")
    assert result.coverage.reason == "response_size_limit" and result.coverage.status == "partial"


def test_node_10000_limit_and_depth8_limit():
    """Catches descendants omitted from node accounting or depth overrun reported complete."""
    data = fixture()
    data["children"] = [data["children"][0]]
    data["children"][0]["children"] = [
        {"id": 1000000 + i, "type": "comment", "text": "original", "children": []}
        for i in range(9998)
    ]
    assert read(data).coverage.status == "complete"
    data["children"][0]["children"].append({"id": 2000000, "children": []})
    assert read(data).coverage.reason == "node_limit"
    data = fixture()
    node = data["children"][0]
    data["children"] = [node]
    for i in range(7):
        child = {"id": 3000000 + i, "children": []}
        node["children"] = [child]
        node = child
    assert read(data).coverage.status == "complete"
    node["children"] = [{"id": 4000000, "children": []}]
    assert read(data).coverage.reason == "depth_limit"


def test_post_character_20000_boundary_and_rejection_counts():
    """Catches oversize text admitted or omitted from rejection denominators."""
    data = fixture()
    data["children"][0]["text"] = "é" * 20000
    assert read(data).coverage.accepted == 1  # This transport bound is characters, not input bytes.
    data["children"][0]["text"] += "é"
    result = read(data)
    assert result.coverage.oversized == 1 and result.coverage.top_level == 4


@pytest.mark.parametrize("mutator", ["duplicate_id", "bool_id", "bad_flag", "bad_children"])
def test_malformed_node_does_not_claim_complete(mutator):
    """Catches duplicate/coerced IDs or malformed traversal nodes producing a complete month."""
    data = fixture()
    if mutator == "duplicate_id":
        data["children"][0]["id"] = 900001
    elif mutator == "bool_id":
        data["children"][0]["id"] = True
    elif mutator == "bad_flag":
        data["children"][0]["deleted"] = "false"
    else:
        data["children"][0]["children"] = "SYNTHETIC_PRIVATE_TEXT"
    assert read(data).coverage.status == "failed"


@pytest.mark.parametrize("body", [b'{"id":900001,"id":900001}', b"\xff", b"not json"])
def test_invalid_json_and_duplicate_keys_fail_closed(body):
    """Catches malformed/duplicate-key source JSON silently becoming clean coverage."""
    assert read(body=body).coverage.status == "failed"


def attempt(status, start=0.0, duration=0.0, retry=None, body=None):
    return t.LocalAttempt(
        body=json.dumps(fixture()).encode() if body is None else body,
        status=status,
        started=start,
        duration=duration,
        retry_after=retry,
    )


def run(attempts):
    return t.validate_local_attempts(
        attempts=attempts, origin=ORIGIN, root_id=900001, month="2026-10"
    )


def test_two_attempt_retry_after_rate_and_cumulative_deadline():
    """Catches reset retry/deadline counters or ignored Retry-After without making requests."""
    assert (
        run((attempt(429, duration=0.5, retry=2), attempt(200, start=2.5))).coverage.status
        == "complete"
    )
    assert (
        run((attempt(429, retry=2), attempt(200, start=1))).coverage.reason
        == "retry_after_or_rate_limit"
    )
    assert (
        run((attempt(503), attempt(200, start=0.5))).coverage.reason == "retry_after_or_rate_limit"
    )
    assert run((attempt(503), attempt(200, start=1))).coverage.status == "complete"
    assert (
        run((attempt(503), attempt(200, start=29, duration=2))).coverage.reason
        == "transport_deadline"
    )
    assert run((attempt(503), attempt(200, start=29, duration=1))).coverage.status == "complete"
    assert (
        run((attempt(503), attempt(503, start=1), attempt(200, start=2))).coverage.reason
        == "attempt_limit"
    )


@pytest.mark.parametrize(
    "attempts,reason",
    [
        ((attempt(302),), "redirect_forbidden"),
        ((attempt(401),), "transport_failed"),
        ((attempt(503), attempt(503, start=1)), "attempts_exhausted"),
        ((attempt(200), attempt(200, start=1)), "attempt_after_success"),
        ((attempt(200, start=float("nan")),), "invalid_attempt_timing"),
    ],
)
def test_attempt_failure_states_remain_failed(attempts, reason):
    """Catches simulated network failure/redirect/invalid timing treated as success."""
    result = run(attempts)
    assert result.coverage.status == "failed" and result.coverage.reason == reason


def test_decompressed_byte_budget_is_shared_across_attempts():
    """Catches a fresh10MiB allowance granted to every retry."""
    result = run((attempt(503, body=b" " * t.MAX_RESPONSE_BYTES), attempt(200, start=1)))
    assert result.coverage.status == "partial" and result.coverage.reason == "response_size_limit"


def test_actual_run_admission_enforces_four_unique_months_and_sequential_timing():
    """Catches callers bypassing month/run and cross-month request rate admission."""
    requests = []
    for index, month in enumerate(("2026-07", "2026-08", "2026-09", "2026-10")):
        data = fixture()
        data["title"] = t.month_title(month)
        requests.append(
            t.LocalMonthRequest(
                month=month,
                root_id=900001,
                origin=ORIGIN,
                attempts=(attempt(200, start=float(index), body=json.dumps(data).encode()),),
            )
        )
    assert all(
        result.coverage.status == "complete" for result in t.read_synthetic_run(tuple(requests))
    )
    with pytest.raises(t.IngestError):
        t.read_synthetic_run(tuple(requests + [requests[0]]))
    requests[1].attempts[0].started = 0.5
    with pytest.raises(t.IngestError, match="run_request_order_or_rate_limit"):
        t.read_synthetic_run(tuple(requests))
