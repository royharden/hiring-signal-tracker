"""S10 synthetic-only Jev replay orchestration over the actual canonical S3 API.

No provider/ledger reimplementation, retries, secret handling, capture or live
dispatch. Generation content-repair runtime awaits its actual owner API.
"""

from typing import Literal

from hiring_signals import contracts as c
from hiring_signals.adapters.rulings import SourceAuthority, generation
from hiring_signals.adapters.screen import POLICY
from hiring_signals.annotation.models import SourcePin
from hiring_signals.extract import jev
from hiring_signals.extract.semantic import DecisionPolicy, SemanticInput, failure
from hiring_signals.shared.callledger.ledger import Ledger
from hiring_signals.shared.callledger.models import (
    BudgetAuthority,
    CallContext,
    Limits,
    OperationPlan,
    Status,
    canonical_digest,
)
from hiring_signals.shared.providers.controller import Provider


class OfflineExtraction(c.ClosedModel):
    stage: Literal["synthetic_offline_control"]
    status: Literal["blocked", "unavailable", "partial", "outcomes_complete"]
    method: Literal["jev"]
    admission_status: Literal["not_attempted", "admitted", "unknown"]
    lookup_statuses: tuple[Status, ...]
    current_external_cost_usd: Literal["0"]
    outbound_attempts: Literal[0]
    quality_status: Literal["not_measured"]
    classification: c.Classification


def policy_sha256(policy: DecisionPolicy):
    policy = DecisionPolicy.model_validate(policy)
    return canonical_digest({"screen": POLICY.sha256, "decisions": policy.model_dump(mode="json")})


def template_sha256(bundle: jev.JevBundle):
    return canonical_digest([r.question_identity() for r in bundle.requests])


def _result(classification, *, admission_status="not_attempted", statuses=(), blocked=False):
    errors = sum(j.process_status == "error" for j in classification.judgments())
    status = (
        "blocked"
        if blocked
        else "unavailable"
        if errors == 37
        else "partial"
        if errors
        else "outcomes_complete"
    )
    return OfflineExtraction(
        stage="synthetic_offline_control",
        status=status,
        method="jev",
        admission_status=admission_status,
        lookup_statuses=tuple(statuses),
        current_external_cost_usd="0",
        outbound_attempts=0,
        quality_status="not_measured",
        classification=classification,
    )


def run_jev_offline(
    source: SemanticInput,
    bundle: jev.JevBundle,
    *,
    policy: DecisionPolicy,
    pin: SourcePin,
    sources: SourceAuthority,
    provider: Provider,
    ledger: Ledger,
    budget: BudgetAuthority,
    context: CallContext,
    limits: Limits,
    plan: OperationPlan,
) -> OfflineExtraction:
    """Admit the whole fixed inventory, validate every child, then exact lookups.

    SourceAuthority's single-process lock covers all current-generation checks
    and ledger reuse writes. An exact replay miss remains an error; no fallback.
    Caller setup must provide actual request evidence and reviewed synthetic
    captures to the canonical Provider/Ledger constructors before this call.
    """
    pin = SourcePin.model_validate(pin)
    policy = DecisionPolicy.model_validate(policy)
    if type(sources) is not SourceAuthority:
        raise ValueError("source_authority_required")
    with sources.guard(pin.item_id) as current:
        if (
            current is None
            or current.pin != pin
            or source.item_id != pin.item_id
            or source.input_sha256 != pin.input_sha256
            or source.generation != generation(pin).evidence_revision
        ):
            return _result(failure(blocked=True), blocked=True)
        admission_status = "not_attempted"
        try:
            source.check()
            bundle.check()
            if bundle._context is not source:
                raise ValueError("source_bundle_mismatch")
            if type(provider) is not Provider or provider.mode not in {"mock", "strict_replay"}:
                raise ValueError("offline_provider_required")
            if policy.provenance != "synthetic_control":
                raise ValueError("actual_dev_calibration_not_provided")
            requests = bundle.requests
            if (
                context.consumer_namespace != "hiring-signals"
                or context.purpose != "hiring.extract.jev"
                or context.source_generation != source.generation
                or context.consumer_context_sha256 != source.generation
                or context.policy_sha256 != policy_sha256(policy)
                or context.template_sha256 != template_sha256(bundle)
                or limits.max_outbound_attempts != 0
                or limits.max_attempts_total > 2
                or len(plan.children) != len(requests)
            ):
                raise ValueError("offline_posting_context_or_inventory_mismatch")
            contexts = []
            for request, child in zip(requests, plan.children, strict=True):
                if (
                    child.max_attempts != 0
                    or child.max_repairs != 0
                    or child.conditional
                    or child.purpose != context.purpose
                    or child.model != request.model
                    or child.provider_config_sha256 != provider.config.sha256
                ):
                    raise ValueError("offline_posting_child_mismatch")
                child_context = context.model_copy(update={"child_id": child.child_id})
                provider.prepare(request, context=child_context, limits=limits)
                contexts.append(child_context)
            before = ledger.totals()["dispatched_attempts"]
            admission_status = "unknown"
            allocation = provider.admit_operation(
                plan, ledger=ledger, budget=budget, context=context, limits=limits
            )
            admission_status = "admitted"
            # Public owner API verifies every child/evidence before the first lookup.
            for request, child_context in zip(requests, contexts, strict=True):
                provider.validate_replay_allocation(
                    request,
                    purpose=context.purpose,
                    ledger=ledger,
                    budget=budget,
                    context=child_context,
                    limits=limits,
                    allocation=allocation,
                )
        except Exception:
            return _result(failure(code="provider_error"), admission_status=admission_status)
        results, statuses = [], []
        for request, child_context in zip(requests, contexts, strict=True):
            try:
                result = provider.run(
                    request,
                    purpose=context.purpose,
                    ledger=ledger,
                    budget=budget,
                    context=child_context,
                    limits=limits,
                    allocation=allocation,
                ).validate_for(request)
                if (
                    (result.status == "ok" and result.origin != "mock")
                    or result.attempt_ids
                    or result.current_external_cost_usd != "0"
                ):
                    raise ValueError("synthetic_zero_dispatch_required")
                statuses.append(result.status)
                results.append(result.typed if result.status == "ok" else None)
            except Exception:
                statuses.append("provider_error")
                results.append(None)
        if ledger.totals()["dispatched_attempts"] != before:
            raise RuntimeError("offline_controller_dispatched_unexpectedly")
        classification = jev.decode(source, bundle, results, policy=policy)
        return _result(classification, admission_status="admitted", statuses=statuses)
