"""Full hiring generation through the canonical fixed-repair simulation controller.

No SDK/authentication, network transport, retry loop or budget implementation.
Only explicitly injected test transports are supported by the canonical mode.
"""

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from hiring_signals import contracts as c
from hiring_signals.adapters.rulings import SourceAuthority, generation
from hiring_signals.adapters.screen import POLICY
from hiring_signals.annotation.models import SourcePin
from hiring_signals.extract import generative, semantic
from hiring_signals.shared.callledger.ledger import ChildCounters, Ledger
from hiring_signals.shared.callledger.models import (
    BudgetAuthority,
    CallContext,
    Identifier,
    Limits,
    OperationPlan,
    Status,
    canonical_digest,
)
from hiring_signals.shared.providers import GenerationRepairPolicy
from hiring_signals.shared.providers import schema as provider_schema
from hiring_signals.shared.providers.controller import Provider
from hiring_signals.shared.providers.models import SourceCaptureRef

Money = Annotated[Decimal, Field(ge=0, allow_inf_nan=False)]


class GenerationContentValidator:
    """Pure full37 decoder validation, bound to its actual implementation and schema.

    Uncertainty is a valid abstention, not a reason to fish for another answer.
    """

    def __init__(
        self,
        source: semantic.SemanticInput,
        bundle: generative.GenerationBundle,
        *,
        pin: SourcePin,
        sources: SourceAuthority,
    ):
        source.check()
        bundle.check()
        if bundle._context is not source:
            raise ValueError("generation_bundle_source_mismatch")
        self.source, self.bundle = source, bundle
        self.pin, self.sources = SourcePin.model_validate(pin), sources
        self._check_current()
        self.revision_sha256 = canonical_digest(
            {
                "version": "hiring-generation-content/1",
                "implementation": {
                    name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                    for name, module in (
                        ("contracts", c),
                        ("generative", generative),
                        ("semantic", semantic),
                        ("provider_schema", provider_schema),
                    )
                },
                "adapter_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "schema": bundle.request.output_schema,
            }
        )

    def _check_current(self):
        if type(self.sources) is not SourceAuthority:
            raise ValueError("source_authority_required")
        with self.sources.guard(self.pin.item_id) as current:
            if current is None or current.pin != self.pin:
                raise ValueError("generation_source_changed")

    def validate(self, parsed_json: object) -> bool:
        self._check_current()
        result = generative.decode_payload(self.source, self.bundle, parsed_json)
        return all(j.process_status not in {"error", "blocked"} for j in result.judgments())


def generation_policy_sha256(validator: GenerationContentValidator) -> str:
    return canonical_digest({"screen": POLICY.sha256, "content": validator.revision_sha256})


def generation_template_sha256(bundle: generative.GenerationBundle) -> str:
    return canonical_digest(bundle.request.identity_payload())


class SimulatedGeneration(c.ClosedModel):
    stage: Literal["injected_generation_simulation"]
    status: Literal["blocked", "unavailable", "partial", "outcomes_complete"]
    method: Literal["generative"]
    reason: Literal[
        "decoded", "source_hold", "preflight_error", "controller_error", "source_changed"
    ]
    admission_status: Literal["not_attempted", "admitted", "unknown"]
    native_status: Status | None
    native_origin: Literal["mock", "replay", "live"] | None
    item_id: c.Digest
    input_sha256: c.Digest
    source_generation: c.Digest
    provider_config_sha256: c.Digest
    requested_model: Annotated[str, Field(min_length=1, max_length=256)]
    attempt_ids: Annotated[tuple[str, ...], Field(max_length=2)]
    child_used_attempts: Annotated[int, Field(ge=0, le=2)] | None
    child_repairs_used: Annotated[int, Field(ge=0, le=1)] | None
    final_physical_request_sha256: c.Digest | None
    source_capture: SourceCaptureRef | None
    accounting_ref: Identifier | None
    child_counters: ChildCounters | None
    canonical_current_external_cost_usd: Money | None
    authority_simulation_known_spend_usd: Money | None
    authority_simulation_unknown_liability_usd: Money | None
    authority_simulation_future_holds_usd: Money | None
    live_provider_evidence: Literal[False]
    quality_status: Literal["not_measured"]
    classification: c.Classification


def run_generation_simulation(
    source: semantic.SemanticInput,
    bundle: generative.GenerationBundle,
    *,
    pin: SourcePin,
    sources: SourceAuthority,
    provider: Provider,
    ledger: Ledger,
    budget: BudgetAuthority,
    context: CallContext,
    limits: Limits,
    plan: OperationPlan,
    repair_policy: GenerationRepairPolicy,
) -> SimulatedGeneration:
    """Use the real controller once: its two-total cap owns transport/content retries.

    Constructors must already contain both original/repair exact request proofs.
    A failed preflight may leave an admitted hold; actual cumulative authority
    totals and child counters are retained, never relabelled as provider bills.
    """
    pin = SourcePin.model_validate(pin)
    if type(sources) is not SourceAuthority:
        raise ValueError("source_authority_required")
    if type(provider) is not Provider or type(ledger) is not Ledger:
        raise ValueError("canonical_generation_objects_required")
    if (
        type(bundle) is not generative.GenerationBundle
        or type(source) is not semantic.SemanticInput
    ):
        raise ValueError("generation_source_bundle_required")
    selected_model = bundle._request.model
    provider_config_sha = provider.config.sha256
    source_generation = generation(pin).evidence_revision
    allocation = result = counters = None
    child_context = None
    admission, reason = "not_attempted", "source_hold"
    classification = semantic.failure(blocked=True)
    with sources.guard(pin.item_id) as current:
        valid_source = (
            current is not None
            and current.pin == pin
            and source.item_id == pin.item_id
            and source.input_sha256 == pin.input_sha256
            and source.generation == generation(pin).evidence_revision
        )
        if valid_source:
            reason = "preflight_error"
            classification = semantic.failure(code="provider_error")
            try:
                validator = GenerationContentValidator(source, bundle, pin=pin, sources=sources)
                request = bundle.request
                repair_policy = GenerationRepairPolicy.model_validate(repair_policy)
                if (
                    type(provider) is not Provider
                    or provider.mode != "injected_simulation"
                    or provider.capture_mode != "disabled"
                    or context.consumer_namespace != "hiring-signals"
                    or context.purpose != "hiring.extract.generative"
                    or context.source_generation != source.generation
                    or context.consumer_context_sha256 != source.generation
                    or context.policy_sha256 != generation_policy_sha256(validator)
                    or context.template_sha256 != generation_template_sha256(bundle)
                    or context.config_sha256 != repair_policy.bound_config_sha256
                    or repair_policy.content_validator_revision_sha256 != validator.revision_sha256
                    or limits.max_attempts_total != 2
                    or limits.max_content_repairs != 1
                    or limits.max_outbound_attempts is None
                    or len(plan.children) != 1
                ):
                    raise ValueError("generation_context_or_profile_mismatch")
                child = plan.children[0]
                if (
                    child.max_attempts != 2
                    or child.max_repairs != 1
                    or child.conditional
                    or child.purpose != context.purpose
                    or child.model != request.model
                    or child.provider_config_sha256 != provider.config.sha256
                ):
                    raise ValueError("generation_child_mismatch")
                child_context = context.model_copy(update={"child_id": child.child_id})
                provider.prepare(request, context=child_context, limits=limits)
                admission = "unknown"
                allocation = provider.admit_operation(
                    plan, ledger=ledger, budget=budget, context=context, limits=limits
                )
                admission, reason = "admitted", "controller_error"
                result = provider.run(
                    request,
                    purpose=context.purpose,
                    ledger=ledger,
                    budget=budget,
                    context=child_context,
                    limits=limits,
                    allocation=allocation,
                    generation_repair=repair_policy,
                    content_validator=validator,
                ).validate_for(request)
                if result.origin != "mock" or provider.config.sha256 != provider_config_sha:
                    raise ValueError("injected_result_origin_mismatch")
                validator._check_current()
                classification = generative.decode(source, bundle, result)
                reason = "decoded"
            except Exception:
                try:
                    source.check()
                    bundle.check()
                    with sources.guard(pin.item_id) as latest:
                        if latest is None or latest.pin != pin:
                            raise ValueError("generation_source_changed")
                except Exception:
                    classification, reason = semantic.failure(blocked=True), "source_changed"
            if allocation is not None:
                counters = ledger.child_counters(allocation, context=child_context)
        totals = ledger.totals()
        errors = sum(j.process_status == "error" for j in classification.judgments())
        blocked = any(j.process_status == "blocked" for j in classification.judgments())
        status = (
            "blocked"
            if blocked
            else "unavailable"
            if errors == 37
            else ("partial" if errors else "outcomes_complete")
        )
        capture = result.source_capture if result else None
        return SimulatedGeneration(
            stage="injected_generation_simulation",
            status=status,
            method="generative",
            reason=reason,
            admission_status=admission,
            native_status=result.status if result else None,
            native_origin=result.origin if result else None,
            item_id=pin.item_id,
            input_sha256=pin.input_sha256,
            source_generation=source_generation,
            provider_config_sha256=provider_config_sha,
            requested_model=selected_model,
            attempt_ids=tuple(result.attempt_ids) if result else (),
            child_used_attempts=counters.used_attempts if counters else None,
            child_repairs_used=counters.repairs_used if counters else None,
            final_physical_request_sha256=capture.request_identity_sha256 if capture else None,
            source_capture=capture,
            accounting_ref=result.accounting_ref if result else None,
            child_counters=counters,
            canonical_current_external_cost_usd=Decimal(result.current_external_cost_usd)
            if result
            else None,
            authority_simulation_known_spend_usd=Decimal(totals["known_spend_usd"]),
            authority_simulation_unknown_liability_usd=Decimal(totals["unknown_liability_usd"]),
            authority_simulation_future_holds_usd=Decimal(totals["future_holds_usd"]),
            live_provider_evidence=False,
            quality_status="not_measured",
            classification=classification,
        )
