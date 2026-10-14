"""Limited supplied-term redaction for reviewed original synthetic inputs only.

No universal identity detection, HTML parser or de-identification claim. Unreviewed
identity inventory/unsupported markup/schemes or size overflow stays quarantined.
"""

import hashlib
import re
from dataclasses import dataclass

from hiring_signals.contracts import MAX_INPUT_BYTES, TransientInput

from .transport import MAX_POST_CHARACTERS, SyntheticPost


@dataclass(frozen=True)
class Span:
    raw_start_byte: int
    raw_end_byte: int
    redacted_start_byte: int
    redacted_end_byte: int
    kind: str


@dataclass(frozen=True)
class LinkFlags:
    has_link: bool
    portfolio: bool
    github: bool
    application: bool


class RedactionResult:
    __slots__ = ("envelope", "raw_sha256", "spans", "links", "reason")

    def __init__(self, envelope, raw_sha256, spans, links, reason):
        self.envelope, self.raw_sha256, self.spans = envelope, raw_sha256, spans
        self.links, self.reason = links, reason

    def __repr__(self):
        return "RedactionResult(<transient processing data omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("transient redaction serialization forbidden")


def prepare_synthetic(
    post: SyntheticPost,
    *,
    identity_terms: tuple[str, ...],
    identities_reviewed: bool,
    link_kinds: tuple[str, ...],
) -> RedactionResult:
    """Caller-declared link kinds preserve flags, not URLs or portfolio judgments."""
    empty_links = LinkFlags(False, False, False, False)

    def quarantine(code):
        return RedactionResult(None, None, (), empty_links, code)

    if identities_reviewed is not True:
        return quarantine("identity_review_required")
    if not isinstance(post, SyntheticPost) or not isinstance(post.text, str):
        return quarantine("invalid_post")
    if not post.text.strip() or len(post.text) > MAX_POST_CHARACTERS:
        return quarantine("post_character_limit")
    if any(not isinstance(term, str) or not term.strip() for term in identity_terms):
        return quarantine("invalid_identity_inventory")
    if any(kind not in {"portfolio", "github", "application", "other"} for kind in link_kinds):
        return quarantine("invalid_link_kind")
    if "<" in post.text or ">" in post.text:
        return quarantine("unsupported_markup")
    terms = "|".join(re.escape(term) for term in sorted(identity_terms, key=len, reverse=True))
    pattern = r"(?P<link>https?://[^\s<>]+|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,})"
    if terms:
        pattern += f"|(?P<identity>{terms})"
    expression = re.compile(pattern, re.IGNORECASE)
    parts, spans, cursor, output_bytes, links = [], [], 0, 0, 0
    try:
        raw_digest = hashlib.sha256(post.text.encode("utf-8")).hexdigest()
        for match in expression.finditer(post.text):
            untouched = post.text[cursor : match.start()]
            parts.append(untouched)
            output_bytes += len(untouched.encode("utf-8"))
            kind = "link" if match.lastgroup == "link" else "identity"
            replacement = "[LINK]" if kind == "link" else "[IDENTITY]"
            raw_start = len(post.text[: match.start()].encode("utf-8"))
            raw_end = raw_start + len(match.group().encode("utf-8"))
            spans.append(
                Span(raw_start, raw_end, output_bytes, output_bytes + len(replacement), kind)
            )
            parts.append(replacement)
            output_bytes += len(replacement)
            links += kind == "link"
            cursor = match.end()
        parts.append(post.text[cursor:])
        redacted = "".join(parts)
        if len(redacted.encode("utf-8")) > MAX_INPUT_BYTES:
            return quarantine("redacted_byte_limit")
    except UnicodeEncodeError:
        return quarantine("invalid_utf8")
    if "://" in redacted:
        return quarantine("unsupported_link_scheme")
    if len(link_kinds) != links:
        return quarantine("link_inventory_review_required")
    flags = LinkFlags(
        bool(links), "portfolio" in link_kinds, "github" in link_kinds, "application" in link_kinds
    )
    envelope = TransientInput(
        input_sha256=hashlib.sha256(redacted.encode()).hexdigest(), text=redacted
    )
    return RedactionResult(envelope, raw_digest, tuple(spans), flags, None)
