"""App composition of canonical offline ports; constant authored replies, not AI.

No reference labels, environment credentials, SDK, HTTP client or transport options
enter this module. Simulated usage/pricing are synthetic accounting controls only.
"""

import hashlib
import json
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from pathlib import Path

from hiring_signals import contracts as c
from hiring_signals.adapters import generation as gen_adapter
from hiring_signals.adapters import providers as jev_adapter
from hiring_signals.adapters.rulings import generation
from hiring_signals.adapters.screen import screen_redacted
from hiring_signals.extract import generative, jev, semantic
from hiring_signals.ingest.redaction import prepare_synthetic
from hiring_signals.ingest.transport import SyntheticPost
from hiring_signals.shared.callledger import Ledger
from hiring_signals.shared.callledger.models import (
    BudgetAuthority,
    CallContext,
    ChildBound,
    Limits,
    OperationPlan,
    canonical_digest,
)
from hiring_signals.shared.callledger.pricing import (
    FundingEvidence,
    PricePolicy,
    PriceProvenance,
    PriceSnapshot,
    RequestEvidence,
)
from hiring_signals.shared.providers import GenerationRepairPolicy, build_generation_repair_request
from hiring_signals.shared.providers.adapters import (
    ModelSupport,
    ProviderConfig,
    decode_outcome,
    prepare_request,
)
from hiring_signals.shared.providers.captures import FixtureIndex, synthetic_capture
from hiring_signals.shared.providers.controller import Provider, TransportReply

from . import domain

PROFILE = "authored-constant-not-stated/1"
MODEL = "synthetic-constant"
NOW = datetime(2026, 10, 17, tzinfo=UTC)
DEADLINE = "2026-10-18T00:00:00Z"


def profile():
    return {
        "version": PROFILE,
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "response_policy": "all_fields_not_stated_independent_of_source_and_reference",
        "jev": "packed69_synthetic_capture_replay",
        "generative": "injected_synthetic_response_counted_by_canonical_controller",
        "token_and_price_evidence": "authored_synthetic_not_measured",
        "external_attempts": 0,
        "quality_status": "not_measured",
    }


class ConstantTransport:
    """A closed in-process reply; never receives a client, URL, key or callback."""

    is_test_transport = True

    def send(self, payload_json, *, timeout_s, max_retries, max_response_bytes):
        body = {
            "model": MODEL,
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    field: {"label": "not_stated", "confidence": 0.5}
                                    for field in c.FIELD_IDS
                                }
                            ),
                        }
                    ],
                }
            ],
            "usage": {"input_tokens": 100, "output_tokens": 100},
        }
        return TransportReply(200, json.dumps(body).encode())


def _binding(item, registry, method, config_sha256, stack):
    # The supplied DEV declaration is not identity review for real third-party text.
    # Refuse links/redaction changes rather than silently changing a frozen source.
    redacted = prepare_synthetic(
        SyntheticPost(1, item.source.text),
        identity_terms=(),
        identities_reviewed=True,
        link_kinds=(),
    )
    if redacted.envelope is None or redacted.envelope.input_sha256 != item.pin.input_sha256:
        raise ValueError("mock_requires_prepared_original_synthetic_source")
    revision = generation(item.pin).evidence_revision
    gate = screen_redacted(redacted, item_id=item.pin.item_id, generation=revision)
    source = semantic.SemanticInput(item.source, gate=gate, generation=revision)
    typed = method == "jev"
    bundle = (
        jev.compile_requests(source, model=MODEL, partition="packed")
        if typed
        else generative.compile_request(source, model=MODEL, max_output_tokens=4096)
    )
    decisions = semantic.DecisionPolicy(
        high_probability=0.8, provenance="synthetic_control", evidence_ref=canonical_digest(PROFILE)
    )
    repair = None
    if not typed:
        validator = gen_adapter.GenerationContentValidator(
            source, bundle, pin=item.pin, sources=registry.sources
        )
        repair = GenerationRepairPolicy(
            schema_version=1,
            mode="regenerate_original_v1",
            base_config_sha256=config_sha256,
            content_validator_revision_sha256=validator.revision_sha256,
        )
    config = ProviderConfig(
        schema_version=1,
        flavor="typesafe" if typed else "openai_responses",
        endpoint_id="authored-offline-only",
        revision_sha256=canonical_digest(PROFILE),
        models={
            MODEL: ModelSupport(
                generation=not typed,
                typed_judgment=typed,
                structured_output=not typed,
                image_input=False,
                streaming=False,
                temperature=False,
                reasoning_efforts=[],
                reported_models=[MODEL],
            )
        },
    )
    authority = BudgetAuthority(
        schema_version=1,
        authority_id="authored-simulation-only",
        scope_sha256=canonical_digest(PROFILE),
        cap_usd="0",
        max_outbound_attempts=2,
        run_deadline_utc=DEADLINE,
    )
    limits = Limits(
        schema_version=1,
        max_attempts_total=2,
        max_content_repairs=0 if typed else 1,
        operation_deadline_s=30.0,
        attempt_timeout_s=20.0,
        run_deadline_utc=DEADLINE,
        max_outbound_attempts=0 if typed else 2,
        max_concurrent_operations=1,
        max_total_input_tokens=4000,
        max_state_plus_longest_question_tokens=2000,
        max_request_bytes=262144,
        max_response_bytes=262144,
        max_questions=128,
        max_choice_options=64,
        max_total_output_tokens=4096,
    )
    context = CallContext(
        schema_version=1,
        authority_id=authority.authority_id,
        run_id="synthetic-cli",
        operation_id="synthetic-operation",
        child_id="group",
        task_id="synthetic-task",
        span_id="synthetic-span",
        consumer_namespace="hiring-signals",
        purpose="hiring.extract." + method,
        source_generation=revision,
        consumer_context_sha256=revision,
        policy_sha256=jev_adapter.policy_sha256(decisions)
        if typed
        else gen_adapter.generation_policy_sha256(validator),
        template_sha256=jev_adapter.template_sha256(bundle)
        if typed
        else gen_adapter.generation_template_sha256(bundle),
        config_sha256=config_sha256 if typed else repair.bound_config_sha256,
    )
    price = PricePolicy(
        schema_version=1,
        provider="synthetic",
        model=MODEL,
        context_sha256=canonical_digest(PROFILE),
        cache_mode="flat_inclusive",
        input_usd_per_million="0",
        cache_read_usd_per_million=None,
        cache_write_usd_per_million=None,
        output_usd_per_million="0",
        fee_usd="0",
    )
    snapshot = PriceSnapshot(
        schema_version=1,
        provenance=PriceProvenance(
            origin="synthetic",
            source_url=None,
            retrieved_at="2026-10-17T00:00:00Z",
            official_verified_at=None,
            source_commit=None,
        ),
        policies=[price],
        data_sha256=canonical_digest([price.model_dump(mode="json")]),
    )
    funding = FundingEvidence(
        schema_version=1,
        snapshot_sha256=snapshot.snapshot_sha256,
        policy_sha256=price.policy_sha256,
        provider_config_sha256=config.sha256,
        model=MODEL,
        request_shape_limit_sha256=canonical_digest(PROFILE),
        input_token_maximum=1000,
        output_token_maximum=None if typed else 4096,
        bound_kind="synthetic_fixture",
        proof_sha256=canonical_digest("authored_not_a_token_measurement"),
    )
    request = bundle.requests[0] if typed else bundle.request
    requests = (request,) if typed else (request, build_generation_repair_request(request, repair))
    prepared = tuple(
        prepare_request(r, config=config, context=context, limits=limits) for r in requests
    )
    evidence = tuple(
        RequestEvidence(
            schema_version=1,
            bound_evidence_sha256=funding.evidence_sha256,
            request_identity_sha256=p.request_identity_sha256,
            dispatched_envelope_sha256=p.dispatched_envelope_sha256,
            input_token_count=100,
            output_token_maximum=None if typed else 4096,
            proof_sha256=canonical_digest("authored_not_a_token_measurement"),
        )
        for p in prepared
    )
    ledger = stack.enter_context(
        Ledger(
            Path(":memory:"),
            authority=authority,
            price_snapshot=None if typed else snapshot,
            trusted_bounds=[] if typed else [funding],
            trusted_requests=evidence,
            clock=lambda: NOW,
        )
    )
    plan = OperationPlan(
        schema_version=1,
        operation_id=context.operation_id,
        authority_id=authority.authority_id,
        context_sha256=canonical_digest(context.model_dump(mode="json")),
        children=[
            ChildBound(
                child_id="child0",
                purpose=context.purpose,
                provider_config_sha256=config.sha256,
                model=MODEL,
                bound_evidence_sha256=funding.evidence_sha256,
                max_attempts=0 if typed else 2,
                max_repairs=0 if typed else 1,
                input_token_maximum=1000,
                output_token_maximum=None if typed else 4096,
                fee_maximum_usd="0",
                reserved_usd_per_attempt="0",
                request_shape_limit_sha256=funding.request_shape_limit_sha256,
                conditional=False,
            )
        ],
    )
    if typed:
        answers = {
            key: {"type": "noul", "noul": 0.0}
            if q.type == "noul"
            else {
                "type": "choice",
                "choice": "not_stated",
                "confidence": 0.5,
                "probabilities": {label: float(label == "not_stated") for label in q.criteria},
            }
            for key, q in request.questions.items()
        }
        outcome = decode_outcome(
            json.dumps(
                {
                    "model": MODEL,
                    "answers": answers,
                    "usage": {"input_tokens": 100},
                }
            ).encode(),
            prepared=prepared[0],
            config=config,
            max_bytes=262144,
        )
        capture = synthetic_capture(
            prepared[0],
            context=context,
            outcome=outcome,
            capture_id="authored-constant",
            review_receipt_sha256=canonical_digest(
                "authored_syntax_fixture_not_independent_review"
            ),
        )
        provider = Provider(
            config,
            mode="strict_replay",
            request_evidence=evidence,
            fixtures=FixtureIndex((capture,)),
            capture_mode="fixture_replay",
        )
        return domain.JevBinding(
            source, bundle, decisions, provider, ledger, authority, context, limits, plan
        )
    provider = Provider(
        config, mode="injected_simulation", request_evidence=evidence, transport=ConstantTransport()
    )
    return domain.GenerationBinding(
        source, bundle, repair, provider, ledger, authority, context, limits, plan
    )


@contextmanager
def methods(registry, config_sha256):
    """Keep actual canonical bindings alive for one comparison, then close all memory DBs."""
    with ExitStack() as stack:
        result = {}
        for method in ("jev", "generative"):
            bindings = {
                item.pin.item_id: _binding(item, registry, method, config_sha256, stack)
                for item in registry._items.values()
            }
            result[method] = domain.HiringMethodRunner(
                registry, method, config_sha256=config_sha256, bindings=bindings
            ).method_config()
        yield result
