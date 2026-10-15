"""Actual canonical ledger/provider app integration with original synthetic replies only."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from hiring_signals.adapters.providers import policy_sha256, run_jev_offline, template_sha256
from hiring_signals.adapters.rulings import SourceAuthority, generation
from hiring_signals.adapters.screen import screen_redacted
from hiring_signals.annotation.models import SourcePin
from hiring_signals.extract import jev
from hiring_signals.extract.semantic import DecisionPolicy, SemanticInput
from hiring_signals.ingest.redaction import prepare_synthetic
from hiring_signals.ingest.transport import SyntheticPost
from hiring_signals.shared.providers.adapters import decode_outcome
from hiring_signals.shared.providers.captures import FixtureIndex, synthetic_capture
from hiring_signals.shared.providers.controller import Provider

# Reuse the exact published public synthetic construction helper in its moved
# namespace. This is no owner app import or heldout/Gold authoring.
HELPER = Path(__file__).parents[1] / "shared_contracts/s3/tests/providers/conftest.py"
spec = importlib.util.spec_from_file_location("s10_public_s3_helper", HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class AppRig(helper.Rig):
    def __init__(self, path, partition="packed"):
        redacted = prepare_synthetic(
            SyntheticPost(1, "Requirements: Python"),
            identity_terms=(),
            identities_reviewed=True,
            link_kinds=(),
        )
        self.pin = SourcePin(
            item_id="a" * 64,
            raw_source_sha256="b" * 64,
            input_sha256=redacted.envelope.input_sha256,
            evidence_revision_sha256="c" * 64,
            taxonomy_sha256="d" * 64,
            rubric_sha256="e" * 64,
        )
        self.sources = SourceAuthority()
        self.sources.install(self.pin, redacted.envelope)
        current_generation = generation(self.pin).evidence_revision
        gate = screen_redacted(redacted, item_id=self.pin.item_id, generation=current_generation)
        self.source = SemanticInput(redacted.envelope, gate=gate, generation=current_generation)
        self.bundle = jev.compile_requests(self.source, model="fixture-model", partition=partition)
        self.decisions = DecisionPolicy(
            high_probability=0.8, provenance="synthetic_control", evidence_ref="f" * 64
        )
        super().__init__(path, "typesafe", True)
        self.limits = self.limits.model_copy(
            update={
                "max_questions": 128,
                "max_request_bytes": 262144,
                "max_response_bytes": 262144,
                "max_outbound_attempts": 0,
            }
        )
        self.evidence = []
        for request in self.bundle.requests:
            self.register(request)

    def context(self, operation="op1", child="group", run="run1"):
        base = super().context(operation, child, run)
        return base.model_copy(
            update={
                "consumer_namespace": "hiring-signals",
                "purpose": "hiring.extract.jev",
                "source_generation": self.source.generation,
                "consumer_context_sha256": self.source.generation,
                "policy_sha256": policy_sha256(self.decisions),
                "template_sha256": template_sha256(self.bundle),
            }
        )

    def plan(self, **kwargs):
        plan = super().plan(**kwargs)
        return plan.model_copy(
            update={
                "children": [
                    child.model_copy(update={"purpose": "hiring.extract.jev"})
                    for child in plan.children
                ]
            }
        )

    def captures(self):
        captures = []
        for index, request in enumerate(self.bundle.requests):
            answers = {}
            for key, question in request.questions.items():
                if question.type == "noul":
                    answers[key] = {
                        "type": "noul",
                        "noul": 1.0 if key == "skills.python.requested" else 0.0,
                    }
                else:
                    label = "requested" if key == "skills.python.class" else "not_stated"
                    answers[key] = {
                        "type": "choice",
                        "choice": label,
                        "probabilities": {key: float(key == label) for key in question.criteria},
                        "confidence": 0.5,
                    }
            prepared = self.prepared(request)
            outcome = decode_outcome(
                json.dumps(
                    {
                        "model": "fixture-model-reported",
                        "answers": answers,
                        "usage": {"input_tokens": 100},
                    }
                ).encode(),
                prepared=prepared,
                config=self.config,
                max_bytes=262144,
            )
            captures.append(
                synthetic_capture(
                    prepared,
                    context=self.context(),
                    outcome=outcome,
                    capture_id=f"original-S10-control-{index}",
                    review_receipt_sha256=hashlib.sha256(b"synthetic-test-review-only").hexdigest(),
                )
            )
        return captures

    def run(self, ledger, provider=None, plan=None, context=None):
        return run_jev_offline(
            self.source,
            self.bundle,
            policy=self.decisions,
            pin=self.pin,
            sources=self.sources,
            provider=provider
            or self.provider(
                "strict_replay",
                fixtures=FixtureIndex(self.captures()),
                capture_mode="fixture_replay",
            ),
            ledger=ledger,
            budget=self.authority,
            context=context or self.context(),
            limits=self.limits,
            plan=plan or self.plan(offline=True, count=len(self.bundle.requests)),
        )


@pytest.mark.parametrize("partition", ["packed", "split"])
def test_actual_full_inventory_admission_replay_and_zero_current_charge(tmp_path, partition):
    """Catches fake accounting, omitted questions or replay called real model evidence."""
    rig = AppRig(tmp_path / "app.sqlite3", partition)
    with rig.open(offline=True) as ledger:
        result = rig.run(ledger)
        assert result.admission_status == "admitted" and result.status == "outcomes_complete"
        assert result.lookup_statuses == ("ok",) * len(rig.bundle.requests)
        assert result.classification.skills.python.value is True
        assert result.classification.skills.go.value is None
        assert result.outbound_attempts == ledger.totals()["dispatched_attempts"] == 0
        assert result.current_external_cost_usd == "0" and result.quality_status == "not_measured"
        assert len(result.native_children) == len(rig.bundle.requests)
        for child, request in zip(result.native_children, rig.bundle.requests, strict=True):
            assert child.origin == "mock" and child.source_capture.origin == "synthetic"
            assert child.source_capture.model_requested == request.model
            assert child.source_capture.request_identity_sha256 == child.request_identity_sha256
            assert child.accounting_ref is not None
            assert child.counters.child_id == child.child_id
            assert child.counters.used_attempts == child.counters.repairs_used == 0
            assert child.counters.mode == "offline"
        assert "original_text" not in result.model_dump_json()


def test_split_strict_miss_preserves_other_group_and_does_not_fallback(tmp_path):
    """Catches a missing capture silently dispatching or erasing the successful skill group."""
    rig = AppRig(tmp_path / "app.sqlite3", "split")
    provider = rig.provider(
        "strict_replay", fixtures=FixtureIndex(rig.captures()[1:]), capture_mode="fixture_replay"
    )
    with rig.open(offline=True) as ledger:
        result = rig.run(ledger, provider=provider)
        assert result.status == "partial" and result.lookup_statuses == ("cache_miss", "ok")
        assert result.classification.ai_engineering_role.process_status == "error"
        assert result.classification.skills.python.value is True
        assert tuple(child.status for child in result.native_children) == ("cache_miss", "ok")
        assert result.native_children[0].source_capture is None
        assert result.native_children[1].source_capture.origin == "synthetic"
        assert ledger.totals()["dispatched_attempts"] == 0


def test_current_source_removal_blocks_before_any_operation_admission(tmp_path):
    """Catches stale model input admitted after the app authority removes its source."""
    rig = AppRig(tmp_path / "app.sqlite3")
    with rig.open(offline=True) as ledger:
        before = ledger.connection.total_changes
        rig.sources.remove(rig.pin.item_id)
        result = rig.run(ledger)
        assert result.status == "blocked" and result.admission_status == "not_attempted"
        assert ledger.connection.total_changes == before
        assert all(j.process_status == "blocked" for j in result.classification.judgments())


def test_bad_second_evidence_fails_entire_preflight_before_first_lookup(tmp_path, monkeypatch):
    """Catches first-child execution before all fixed child request evidence is validated."""
    rig = AppRig(tmp_path / "app.sqlite3", "split")
    provider = Provider(
        rig.config,
        mode="strict_replay",
        request_evidence=rig.evidence[:1],
        fixtures=FixtureIndex(rig.captures()),
        capture_mode="fixture_replay",
    )
    called = []
    actual = provider.run

    def tracked(*args, **kwargs):
        called.append(True)
        return actual(*args, **kwargs)

    monkeypatch.setattr(provider, "run", tracked)
    with rig.open(offline=True) as ledger:
        result = rig.run(ledger, provider=provider)
        assert result.status == "unavailable" and result.admission_status == "admitted"
        assert called == [] and ledger.totals()["dispatched_attempts"] == 0


@pytest.mark.parametrize("fault", ["extra_child", "context", "outbound", "bytes", "attempts"])
def test_scope_inventory_limits_and_whole_request_caps_fail_before_admission(tmp_path, fault):
    """Catches unfunded fallback, wrong source context or request-prefix admission."""
    rig = AppRig(tmp_path / "app.sqlite3")
    provider = rig.provider(
        "strict_replay", fixtures=FixtureIndex(rig.captures()), capture_mode="fixture_replay"
    )
    plan = rig.plan(offline=True)
    context = rig.context()
    if fault == "extra_child":
        plan = rig.plan(offline=True, count=2)
    elif fault == "context":
        context = context.model_copy(update={"source_generation": "changed"})
    else:
        field, value = {
            "outbound": ("max_outbound_attempts", 1),
            "bytes": ("max_request_bytes", 1),
            "attempts": ("max_attempts_total", 3),
        }[fault]
        rig.limits = rig.limits.model_copy(update={field: value})
    with rig.open(offline=True) as ledger:
        before = ledger.connection.total_changes
        result = rig.run(ledger, provider=provider, plan=plan, context=context)
        assert result.status == "unavailable" and result.admission_status == "not_attempted"
        assert ledger.connection.total_changes == before
