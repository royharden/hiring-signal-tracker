"""Bounded original-synthetic transport controls, with no network or filesystem access.

These validate supplied response bytes and simulated attempt timing. They are not
evidence of live HN transport behavior, data rights or measured acquisition latency.
"""

import calendar
import json
import math
import re
from dataclasses import dataclass

MAX_MONTHS = 4
MAX_TOP_LEVEL = 600
MAX_RESPONSE_BYTES = 10 * 1024 * 1024
MAX_NODES = 10000
MAX_DEPTH = 8
MAX_POST_CHARACTERS = 20000
MAX_TRANSPORT_SECONDS = 30
MAX_ATTEMPTS = 2
MIN_REQUEST_INTERVAL_SECONDS = 1


class IngestError(ValueError):
    """Closed errors contain codes only, never rejected source values."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class SyntheticPost:
    """Transient source text with no author field, dict or pickle serialization."""

    __slots__ = ("source_id", "text")

    def __init__(self, source_id: int, text: str):
        self.source_id = source_id
        self.text = text

    def __repr__(self):
        return "SyntheticPost(<transient text omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("transient post serialization forbidden")


@dataclass(frozen=True)
class Coverage:
    month: str
    status: str
    top_level: int | None
    accepted: int
    deleted: int
    dead: int
    empty: int
    oversized: int
    invalid: int
    reason: str | None


class MonthInput:
    __slots__ = ("coverage", "posts")

    def __init__(self, coverage: Coverage, posts: tuple[SyntheticPost, ...]):
        self.coverage = coverage
        self.posts = posts

    def __repr__(self):
        return f"MonthInput({self.coverage!r}, <transient posts omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("transient month serialization forbidden")


def month_title(month: str) -> str:
    if not isinstance(month, str) or not re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month):
        raise IngestError("invalid_month")
    year, number = map(int, month.split("-"))
    return f"Ask HN: Who is hiring? ({calendar.month_name[number]} {year})"


def validate_months(months: tuple[str, ...]) -> None:
    if not 1 <= len(months) <= MAX_MONTHS or len(set(months)) != len(months):
        raise IngestError("month_inventory_limit")
    for month in months:
        month_title(month)


def validate_origin(origin: str, root_id: int) -> None:
    if type(root_id) is not int or root_id <= 0 or root_id > 2**63 - 1:
        raise IngestError("invalid_root_id")
    if origin != f"https://hn.algolia.com/api/v1/items/{root_id}":
        raise IngestError("wrong_origin")


def _closed_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise IngestError("duplicate_json_key")
        result[key] = value
    return result


def _unready(month: str, reason: str, *, count=None, partial=False) -> MonthInput:
    return MonthInput(
        Coverage(month, "partial" if partial else "failed", count, 0, 0, 0, 0, 0, 0, reason), ()
    )


def read_synthetic_response(*, body: bytes, origin: str, root_id: int, month: str) -> MonthInput:
    """Accept only explicitly supplied original synthetic decompressed bytes.

    This is an Algolia-shaped local fixture protocol, not verified API compatibility.
    Root/thread mismatch raises a safe error. Coverage limits refuse the whole month
    rather than treating a bounded prefix as a complete dataset.
    """
    title = month_title(month)
    validate_origin(origin, root_id)
    if type(body) is not bytes:
        raise IngestError("body_must_be_bytes")
    if len(body) > MAX_RESPONSE_BYTES:
        return _unready(month, "response_size_limit", partial=True)
    try:
        root = json.loads(body, object_pairs_hook=_closed_object)
    except IngestError:
        return _unready(month, "duplicate_json_key")
    except (ValueError, UnicodeError, RecursionError):
        return _unready(month, "invalid_json")
    if not isinstance(root, dict):
        return _unready(month, "invalid_root")
    if type(root.get("id")) is not int or root["id"] != root_id:
        raise IngestError("root_identity_mismatch")
    if root.get("type") != "story" or root.get("title") != title:
        raise IngestError("wrong_thread")
    if root.get("deleted") or root.get("dead"):
        return _unready(month, "unavailable_root")
    children = root.get("children")
    if not isinstance(children, list):
        return _unready(month, "invalid_children")
    count = len(children)
    if count > MAX_TOP_LEVEL:
        return _unready(month, "top_level_limit", count=count, partial=True)
    # Validate all nodes iteratively before any post is admitted; root depth is zero.
    stack = [(root, 0)]
    nodes = 0
    seen = set()
    while stack:
        node, depth = stack.pop()
        nodes += 1
        if nodes > MAX_NODES or depth > MAX_DEPTH:
            reason = "node_limit" if nodes > MAX_NODES else "depth_limit"
            return _unready(month, reason, count=count, partial=True)
        if not isinstance(node, dict):
            return _unready(month, "invalid_node", count=count)
        node_id = node.get("id")
        if type(node_id) is not int or not 0 < node_id <= 2**63 - 1 or node_id in seen:
            return _unready(month, "invalid_or_duplicate_node_id", count=count)
        seen.add(node_id)
        if any(type(node.get(flag, False)) is not bool for flag in ("deleted", "dead")):
            return _unready(month, "invalid_node_flags", count=count)
        nested = node.get("children", [])
        if not isinstance(nested, list):
            return _unready(month, "invalid_children", count=count)
        stack.extend((child, depth + 1) for child in nested)
    accepted = []
    rejections = {"deleted": 0, "dead": 0, "empty": 0, "oversized": 0, "invalid": 0}
    for node in children:
        # Never copy by/author/company/title fields into the processing envelope.
        if node.get("deleted") is True:
            rejections["deleted"] += 1
        elif node.get("dead") is True:
            rejections["dead"] += 1
        elif node.get("type") != "comment" or not isinstance(node.get("text"), str):
            rejections["invalid"] += 1
        elif not node["text"].strip():
            rejections["empty"] += 1
        elif len(node["text"]) > MAX_POST_CHARACTERS:
            rejections["oversized"] += 1
        else:
            accepted.append(SyntheticPost(node["id"], node["text"]))
    coverage = Coverage(month, "complete", count, len(accepted), **rejections, reason=None)
    assert coverage.accepted + sum(rejections.values()) == count
    return MonthInput(coverage, tuple(accepted))


class LocalAttempt:
    """A supplied simulated attempt, with no executor/network client or implicit retry."""

    __slots__ = ("body", "status", "started", "duration", "retry_after")

    def __init__(
        self,
        *,
        body: bytes,
        status: int,
        started: float,
        duration: float,
        retry_after: float | None,
    ):
        self.body, self.status = body, status
        self.started, self.duration, self.retry_after = started, duration, retry_after

    def __repr__(self):
        return "LocalAttempt(<synthetic response omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("transient attempt serialization forbidden")


def validate_local_attempts(
    *, attempts: tuple[LocalAttempt, ...], origin: str, root_id: int, month: str
) -> MonthInput:
    """Validate sequential simulated timing/Retry-After; performs no waits or requests."""
    month_title(month)
    validate_origin(origin, root_id)
    if not 1 <= len(attempts) <= MAX_ATTEMPTS:
        return _unready(month, "attempt_limit")
    if any(
        not isinstance(attempt, LocalAttempt) or type(attempt.body) is not bytes
        for attempt in attempts
    ):
        return _unready(month, "invalid_attempt")
    if sum(len(attempt.body) for attempt in attempts) > MAX_RESPONSE_BYTES:
        return _unready(month, "response_size_limit", partial=True)
    first = attempts[0].started
    for index, attempt in enumerate(attempts):
        values = [attempt.started, attempt.duration]
        if attempt.retry_after is not None:
            values.append(attempt.retry_after)
        if any(
            type(value) not in {int, float} or not math.isfinite(value) or value < 0
            for value in values
        ):
            return _unready(month, "invalid_attempt_timing")
        if attempt.started + attempt.duration - first > MAX_TRANSPORT_SECONDS:
            return _unready(month, "transport_deadline")
        if index:
            previous = attempts[index - 1]
            wait = previous.retry_after or 0
            earliest = max(
                previous.started + MIN_REQUEST_INTERVAL_SECONDS,
                previous.started + previous.duration + wait,
            )
            if attempt.started < earliest:
                return _unready(month, "retry_after_or_rate_limit")
        if type(attempt.status) is not int:
            return _unready(month, "invalid_status")
        if attempt.status == 200:
            if index != len(attempts) - 1:
                return _unready(month, "attempt_after_success")
            return read_synthetic_response(
                body=attempt.body, origin=origin, root_id=root_id, month=month
            )
        if 300 <= attempt.status < 400:
            return _unready(month, "redirect_forbidden")
        if attempt.status not in {429, 500, 502, 503, 504}:
            return _unready(month, "transport_failed")
    return _unready(month, "attempts_exhausted")


class LocalMonthRequest:
    __slots__ = ("month", "root_id", "origin", "attempts")

    def __init__(
        self, *, month: str, root_id: int, origin: str, attempts: tuple[LocalAttempt, ...]
    ):
        self.month, self.root_id, self.origin, self.attempts = month, root_id, origin, attempts

    def __repr__(self):
        return "LocalMonthRequest(<transient responses omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("transient request serialization forbidden")


def read_synthetic_run(requests: tuple[LocalMonthRequest, ...]) -> tuple[MonthInput, ...]:
    """Four-month admission and sequential request timing across simulated months."""
    if any(not isinstance(request, LocalMonthRequest) for request in requests):
        raise IngestError("invalid_run_request")
    validate_months(tuple(request.month for request in requests))
    results, previous = [], None
    for request in requests:
        result = validate_local_attempts(
            attempts=request.attempts,
            month=request.month,
            origin=request.origin,
            root_id=request.root_id,
        )
        timing_valid = request.attempts and all(
            isinstance(attempt, LocalAttempt)
            and all(
                type(value) in {int, float} and math.isfinite(value) and value >= 0
                for value in (
                    attempt.started,
                    attempt.duration,
                    *(() if attempt.retry_after is None else (attempt.retry_after,)),
                )
            )
            for attempt in request.attempts
        )
        if timing_valid:
            first, last = request.attempts[0], request.attempts[-1]
            if previous is not None:
                earliest = max(
                    previous.started + MIN_REQUEST_INTERVAL_SECONDS,
                    previous.started + previous.duration + (previous.retry_after or 0),
                )
                if first.started < earliest:
                    raise IngestError("run_request_order_or_rate_limit")
            previous = last
        results.append(result)
    return tuple(results)
