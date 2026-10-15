"""Actual full37 hiring repair joins with authored injected transports, no live model."""

import importlib.util
import json
import socket
from decimal import Decimal
from pathlib import Path

import pytest

from hiring_signals import contracts as c
from hiring_signals.adapters import generation as app
from hiring_signals.adapters.rulings import SourceAuthority, generation
from hiring_signals.adapters.screen import screen_redacted
from hiring_signals.annotation.models import SourcePin
from hiring_signals.extract import generative
from hiring_signals.extract.semantic import SemanticInput
from hiring_signals.ingest.redaction import prepare_synthetic
from hiring_signals.ingest.transport import SyntheticPost
from hiring_signals.shared.providers import GenerationRepairPolicy, build_generation_repair_request

HELPER = Path(__file__).parents[1] / "shared_contracts/s3/tests/providers/conftest.py"
spec = importlib.util.spec_from_file_location("s10_generation_public_helper", HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("network forbidden in authored generation controls")

    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)


class Rig(helper.Rig):
    def __init__(self, path, text="Requirements: Python\nSalary:100000-120000"):
        super().__init__(path)
        redacted = prepare_synthetic(
            SyntheticPost(1, text),
            identity_terms=(),
            identities_reviewed=True,
            link_kinds=(),
        )
        self.pin = SourcePin(
            item_id="a" * 64,
            raw_source_sha256=redacted.raw_sha256,
            input_sha256=redacted.envelope.input_sha256,
            evidence_revision_sha256="b" * 64,
            taxonomy_sha256="c" * 64,
            rubric_sha256="d" * 64,
        )
        self.sources = SourceAuthority()
        self.sources.install(self.pin, redacted.envelope)
        gen = generation(self.pin).evidence_revision
        gate = screen_redacted(redacted, item_id=self.pin.item_id, generation=gen)
        self.source = SemanticInput(redacted.envelope, gate=gate, generation=gen)
        self.bundle = generative.compile_request(
            self.source, model="fixture-model", max_output_tokens=4096
        )
        self.validator = app.GenerationContentValidator(
            self.source, self.bundle, pin=self.pin, sources=self.sources
        )
        self.repair = GenerationRepairPolicy(
            schema_version=1,
            mode="regenerate_original_v1",
            base_config_sha256="e" * 64,
            content_validator_revision_sha256=self.validator.revision_sha256,
        )
        self.request = self.bundle.request
        self.limits = self.limits.model_copy(
            update={
                "max_content_repairs": 1,
                "max_total_output_tokens": 4096,
                "max_request_bytes": 262144,
                "max_response_bytes": 262144,
            }
        )
        self.bound = self.bound.model_copy(update={"output_token_maximum": 4096})
        self.repair_request = build_generation_repair_request(self.request, self.repair)
        self.evidence = []
        self.register(self.request)
        self.register(self.repair_request)

    def context(self, *args, **kwargs):
        original = super().context(*args, **kwargs)
        if not hasattr(self, "repair"):
            return original
        return original.model_copy(
            update={
                "consumer_namespace": "hiring-signals",
                "purpose": "hiring.extract.generative",
                "source_generation": self.source.generation,
                "consumer_context_sha256": self.source.generation,
                "policy_sha256": app.generation_policy_sha256(self.validator),
                "template_sha256": app.generation_template_sha256(self.bundle),
                "config_sha256": self.repair.bound_config_sha256,
            }
        )

    def plan(self, **kwargs):
        original = super().plan(**kwargs)
        return original.model_copy(
            update={
                "children": [
                    child.model_copy(
                        update={"purpose": "hiring.extract.generative", "max_repairs": 1}
                    )
                    for child in original.children
                ]
            }
        )

    def body(self, payload=None):
        body = super().body()
        if payload is None:
            payload = {field: {"label": "not_stated", "confidence": 0.7} for field in c.FIELD_IDS}
            payload["skills.python"] = {"label": "requested", "confidence": 0.9}
        body["output"][0]["content"][0]["text"] = (
            payload if isinstance(payload, str) else json.dumps(payload)
        )
        return body

    def run(self, provider, ledger, **updates):
        options = dict(
            pin=self.pin,
            sources=self.sources,
            provider=provider,
            ledger=ledger,
            budget=self.authority,
            context=self.context(),
            limits=self.limits,
            plan=self.plan(),
            repair_policy=self.repair,
        )
        options.update(updates)
        return app.run_generation_simulation(self.source, self.bundle, **options)


def test_full37_schema_repair_uses_actual_two_attempts_and_final_physical_capture(tmp_path):
    """Catches a local fake repair, lost first-call cost or original request relabelled final."""
    rig = Rig(
        tmp_path / "generation.sqlite3",
        "Requirements: Python\nSalary:100000-120000\nSYNTHETIC_PRIVATE_SOURCE_CANARY",
    )
    transport = helper.Spy(
        rig, [helper.response(rig.body("BAD_AUTHORED_OUTPUT")), helper.response(rig.body())]
    )
    provider = rig.provider(transport=transport)
    with rig.open() as ledger:
        result = rig.run(provider, ledger)
        assert result.status == "outcomes_complete" and result.native_status == "ok"
        assert len(result.classification.judgments()) == 37
        assert result.classification.skills.python.value is True
        assert result.classification.skills.python.certainty.kind == "self_reported_confidence"
        assert result.child_used_attempts == len(result.attempt_ids) == len(transport.calls) == 2
        assert result.child_repairs_used == 1
        assert result.authority_simulation_known_spend_usd == Decimal("0.02")
        assert result.authority_simulation_future_holds_usd == 0
        assert (
            result.final_physical_request_sha256
            == rig.prepared(rig.repair_request).request_identity_sha256
        )
        assert result.final_physical_request_sha256 != rig.prepared().request_identity_sha256
        assert all(call[1]["max_retries"] == 0 for call in transport.calls)
        assert b"BAD_AUTHORED_OUTPUT" not in transport.calls[-1][0]
        assert "BAD_AUTHORED_OUTPUT" not in result.model_dump_json()
        assert "SYNTHETIC_PRIVATE_SOURCE_CANARY" not in result.model_dump_json()
        assert result.live_provider_evidence is False and result.quality_status == "not_measured"


def test_first_valid_output_releases_unused_hold_without_content_repair(tmp_path):
    """Catches an automatic second call after a complete first response."""
    rig = Rig(tmp_path / "first-valid.sqlite3")
    transport = helper.Spy(rig, [helper.response(rig.body())])
    with rig.open() as ledger:
        result = rig.run(rig.provider(transport=transport), ledger)
    assert result.child_used_attempts == len(transport.calls) == 1
    assert result.child_repairs_used == 0 and result.authority_simulation_future_holds_usd == 0
    assert result.final_physical_request_sha256 == rig.prepared().request_identity_sha256


def test_valid_uncertainty_does_not_fish_for_a_more_confident_second_answer(tmp_path):
    """Catches valid uncertainty spending the repair budget to chase a convenient answer."""
    rig = Rig(tmp_path / "uncertainty.sqlite3")
    payload = {field: {"label": "uncertain", "confidence": 0.5} for field in c.FIELD_IDS}
    transport = helper.Spy(rig, [helper.response(rig.body(payload))])
    with rig.open() as ledger:
        result = rig.run(rig.provider(transport=transport), ledger)
    assert result.status == "outcomes_complete" and result.child_used_attempts == 1
    assert result.child_repairs_used == 0 and len(transport.calls) == 1
    assert all(j.process_status == "abstained" for j in result.classification.judgments())


def test_completed_operation_does_not_automatically_resume_or_invent_a_replay(tmp_path):
    """Catches a used child resetting attempts or its old result being labelled a new call."""
    rig = Rig(tmp_path / "no-resume.sqlite3")
    transport = helper.Spy(rig, [helper.response(rig.body())])
    provider = rig.provider(transport=transport)
    with rig.open() as ledger:
        first = rig.run(provider, ledger)
        before = list(ledger.connection.iterdump())
        second = rig.run(provider, ledger)
        assert before == list(ledger.connection.iterdump())
    assert first.status == "outcomes_complete" and second.status == "unavailable"
    assert second.child_used_attempts == 1 and len(transport.calls) == 1
    assert second.native_status is None and second.attempt_ids == ()


def test_network_guard_positive_control():
    """Catches the injected-control network denial fixture not actually blocking connections."""
    with pytest.raises(AssertionError, match="network forbidden"):
        socket.create_connection(("example.invalid", 443))


@pytest.mark.parametrize("first", ["schema", "transport"])
def test_invalid_second_or_transport_retry_cannot_add_third_attempt(tmp_path, first):
    """Catches transport and content retries obtaining separate two-attempt budgets."""
    rig = Rig(tmp_path / "two-total.sqlite3")
    first_reply = (
        helper.response(rig.body("invalid JSON"))
        if first == "schema"
        else helper.response({}, status=429)
    )
    transport = helper.Spy(rig, [first_reply, helper.response(rig.body("still invalid JSON"))])
    with rig.open() as ledger:
        result = rig.run(rig.provider(transport=transport), ledger)
    assert (
        result.status == "unavailable" and result.child_used_attempts == len(transport.calls) == 2
    )
    assert result.child_repairs_used == (1 if first == "schema" else 0)
    assert all(j.process_status == "error" for j in result.classification.judgments())


@pytest.mark.parametrize("side", ["provider", "ledger"])
def test_missing_repair_proof_has_zero_sends_and_retains_actual_admitted_hold(tmp_path, side):
    """Catches a missing repair proof dispatching first or hiding the actual reserved hold."""
    rig = Rig(tmp_path / "missing-proof.sqlite3")
    complete = list(rig.evidence)
    if side == "provider":
        rig.evidence = complete[:1]
    transport = helper.Spy(rig, [])
    provider = rig.provider(transport=transport)
    rig.evidence = complete if side == "provider" else complete[:1]
    with rig.open() as ledger:
        result = rig.run(provider, ledger)
    assert not transport.calls and result.child_used_attempts == 0
    assert result.status == "unavailable" and result.admission_status == "admitted"
    assert result.authority_simulation_future_holds_usd == Decimal("0.2")


@pytest.mark.parametrize("mutation", ["config", "repair_limit", "mode", "capture", "source"])
def test_source_profile_or_unsupported_mode_reject_before_admission(tmp_path, mutation):
    """Catches wrong source/config/limits or unsupported mock repair spending an admission hold."""
    rig = Rig(tmp_path / "preflight.sqlite3")
    transport = helper.Spy(rig, [])
    provider = rig.provider(transport=transport)
    updates = {}
    if mutation == "config":
        updates["context"] = rig.context().model_copy(update={"config_sha256": "f" * 64})
    elif mutation == "repair_limit":
        updates["limits"] = rig.limits.model_copy(update={"max_content_repairs": 0})
    elif mutation == "mode":
        provider.mode = "mock"
    elif mutation == "capture":
        provider.capture_mode = "fixture_replay"
    else:
        rig.sources.remove(rig.pin.item_id)
    with rig.open() as ledger:
        result = rig.run(provider, ledger, **updates)
        assert ledger.totals()["dispatched_attempts"] == 0
    assert result.admission_status == "not_attempted" and not transport.calls
    assert result.child_used_attempts is None and result.authority_simulation_future_holds_usd == 0


def test_unknown_first_usage_liability_survives_successful_repair(tmp_path):
    """Catches an invalid first result with unknown usage being silently priced as free."""
    rig = Rig(tmp_path / "unknown-usage.sqlite3")
    first = rig.body("invalid JSON")
    first["usage"]["input_tokens"] = None
    transport = helper.Spy(rig, [helper.response(first), helper.response(rig.body())])
    with rig.open() as ledger:
        result = rig.run(rig.provider(transport=transport), ledger)
    assert result.status == "outcomes_complete" and result.child_repairs_used == 1
    assert result.authority_simulation_unknown_liability_usd == Decimal("0.1")
    assert result.authority_simulation_known_spend_usd == Decimal("0.01")


def test_source_removed_during_first_response_stops_repair_and_blocks_predictions(tmp_path):
    """Catches source removal producing stale successes or another repair call."""
    rig = Rig(tmp_path / "source-removed.sqlite3")

    class Removing(helper.Spy):
        def send(self, payload_json, **kwargs):
            reply = super().send(payload_json, **kwargs)
            rig.sources.remove(rig.pin.item_id)
            return reply

    transport = Removing(rig, [helper.response(rig.body())])
    with rig.open() as ledger:
        result = rig.run(rig.provider(transport=transport), ledger)
    assert result.status == "blocked" and result.reason == "source_changed"
    assert result.child_used_attempts == 1 and result.child_repairs_used == 0
    assert len(transport.calls) == 1 and all(
        j.process_status == "blocked" for j in result.classification.judgments()
    )
