"""S10 rules-only screen on complete reviewed privacy-redacted input.

No capture, persistence, provider dispatch or typed screening. A gate is a current
input binding, not data rights, identity removal, authentication or human approval.
"""

import hashlib
import re
from typing import Literal

from hiring_signals import contracts as c
from hiring_signals.ingest.redaction import RedactionResult
from hiring_signals.shared.screen import ScreenPolicy, UntrustedText, screen_rules

POLICY = ScreenPolicy(
    version="S10-rules/1",
    required_method="rules",
    max_input_bytes=32768,
    profile_id="S10-privacy-redacted-rules/1",
)


class ScreenGate(c.ClosedModel):
    item_id: c.Digest
    source_generation: c.Digest
    input_sha256: c.Digest | None
    normalized_sha256: c.Digest | None
    policy_sha256: c.Digest
    method: Literal["rules"]
    status: Literal["pass", "hold", "privacy_unavailable"]
    coverage: Literal["complete", "partial"]
    deterministic_flags: tuple[str, ...]
    diagnostic_notices: tuple[str, ...]
    reason_codes: tuple[str, ...]
    hazard_probabilities: None
    model_reported: None
    actual_dispatched_envelope_sha256: None

    def permits(self, source: c.TransientInput, *, generation: str) -> bool:
        return (
            self.status == "pass"
            and self.coverage == "complete"
            and self.policy_sha256 == POLICY.sha256
            and generation == self.source_generation
            and isinstance(source, c.TransientInput)
            and source.input_sha256 == self.input_sha256
            and hashlib.sha256(source.text.encode()).hexdigest() == self.input_sha256
        )


def screen_redacted(redaction: RedactionResult, *, item_id: str, generation: str) -> ScreenGate:
    """Call only after privacy assembly; never append a candidate/source suffix later."""
    if any(
        type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in (item_id, generation)
    ):
        raise ValueError("invalid_screen_identity")
    base = dict(
        item_id=item_id,
        source_generation=generation,
        policy_sha256=POLICY.sha256,
        method="rules",
        hazard_probabilities=None,
        model_reported=None,
        actual_dispatched_envelope_sha256=None,
    )
    if not isinstance(redaction, RedactionResult) or redaction.envelope is None:
        return ScreenGate(
            **base,
            input_sha256=None,
            normalized_sha256=None,
            status="privacy_unavailable",
            coverage="partial",
            deterministic_flags=(),
            diagnostic_notices=(),
            reason_codes=("privacy_not_prepared",),
        )
    source = redaction.envelope
    if not isinstance(source, c.TransientInput) or (
        hashlib.sha256(source.text.encode()).hexdigest() != source.input_sha256
    ):
        raise ValueError("stale_redacted_screen_source")
    # Complete privacy-redacted text is screened once; no snippets or truncated prefix.
    untrusted = UntrustedText(item_id, generation, source.text)
    result = screen_rules(untrusted, POLICY)
    allowed = result.permits_model_input(untrusted, POLICY)
    return ScreenGate(
        **base,
        input_sha256=result.input_sha256,
        normalized_sha256=result.normalized_sha256,
        status="pass" if allowed else "hold",
        coverage=result.coverage,
        deterministic_flags=result.deterministic_flags,
        diagnostic_notices=result.diagnostic_notices,
        reason_codes=result.reason_codes,
    )
