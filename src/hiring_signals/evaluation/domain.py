"""Trusted hiring execution/37-axis adapter over the unchanged canonical comparison runner.

The issuance registry is trusted in-process code, not authentication against hostile
Python callers. Hashes bind actual execution; they do not establish rights or human Gold.
"""

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from hiring_signals import contracts as c
from hiring_signals.adapters import generation as generation_adapter
from hiring_signals.adapters import providers as jev_adapter
from hiring_signals.adapters.rulings import SourceAuthority, generation
from hiring_signals.annotation.models import SourcePin
from hiring_signals.extract import generative, jev, rules, semantic
from hiring_signals.shared.callledger.models import canonical_digest
from hiring_signals.shared.evalkit.axis_status import (
    AxisStatus,
    AxisStatusBinding,
    prediction_digest,
    raw_machine_digest,
)
from hiring_signals.shared.evalkit.corpus import load_corpus
from hiring_signals.shared.evalkit.models import (
    GoldRecord,
    MetricSpec,
    Outcome,
    Prediction,
    PublicMethodInput,
    PublicProjectionPolicy,
    SourceRef,
)
from hiring_signals.shared.evalkit.runner import MethodConfig, SourceView, compare
from hiring_signals.shared.evalkit.statistics import typed_equal

from . import labels, majority

AXES = tuple((field, None) for field in c.FIELD_IDS)


class DomainError(ValueError):
    """Closed domain failure code, without source/Gold/rejected payloads."""


@dataclass(frozen=True, repr=False)
class SourceItem:
    pin: SourcePin
    source: c.TransientInput
    month: str

    def __repr__(self):
        return "SourceItem(<transient source omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("transient_source_serialization_forbidden")


@dataclass(frozen=True, repr=False)
class JevBinding:
    source: semantic.SemanticInput
    bundle: jev.JevBundle
    policy: semantic.DecisionPolicy
    provider: object
    ledger: object
    budget: object
    context: object
    limits: object
    plan: object


@dataclass(frozen=True, repr=False)
class GenerationBinding:
    source: semantic.SemanticInput
    bundle: generative.GenerationBundle
    repair_policy: object
    provider: object
    ledger: object
    budget: object
    context: object
    limits: object
    plan: object


def _implementation() -> str:
    return canonical_digest(
        {
            name: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
            for name, module in (
                ("domain", __import__(__name__, fromlist=["*"])),
                ("contracts", c),
                ("rules", rules),
                ("jev", jev),
                ("generative", generative),
                ("semantic", semantic),
                ("jev_adapter", jev_adapter),
                ("generation_adapter", generation_adapter),
                ("labels", labels),
                ("majority", majority),
            )
        }
    )


def _field_status(row: labels.MachineField) -> str:
    if row.process_status == "error":
        return "provider_error" if row.error_code == "provider_error" else "invalid"
    return row.process_status


def _controller_status(classification: c.Classification) -> str:
    rows = classification.judgments()
    if any(row.process_status == "blocked" for row in rows):
        return "blocked"
    n = sum(row.process_status == "error" for row in rows)
    return "unavailable" if n == 37 else "partial" if n else "outcomes_complete"


class ExecutionRegistry:
    """Current source authority plus actual concrete-runner issuance, without a public mint API."""

    def __init__(self, items: tuple[SourceItem, ...], sources: SourceAuthority):
        if type(sources) is not SourceAuthority or len({x.pin.item_id for x in items}) != len(
            items
        ):
            raise DomainError("invalid_source_registry")
        self.sources = sources
        self._items = {item.pin.item_id: item for item in items}
        self._issued = {}
        for item in items:
            SourcePin.model_validate(item.pin)
            TypeAdapter(c.Month).validate_python(item.month, strict=True)
            if type(item.source) is not c.TransientInput or (
                item.source.input_sha256 != item.pin.input_sha256
                or hashlib.sha256(item.source.text.encode()).hexdigest() != item.pin.input_sha256
            ):
                raise DomainError("source_input_binding_mismatch")

    def _current(self, item: SourceItem) -> bool:
        with self.sources.guard(item.pin.item_id) as current:
            return bool(
                current is not None
                and current.pin == item.pin
                and hashlib.sha256(item.source.text.encode()).hexdigest() == item.pin.input_sha256
            )

    def source_view(self, record: GoldRecord) -> SourceView:
        item = self._items.get(record.item_id)
        if item is None:
            return SourceView("unavailable", None, {})
        if not self._current(item):
            return SourceView("stale", item.pin.input_sha256, {})
        return SourceView("available", item.pin.input_sha256, {"text": item.source.text})

    def _lookup(self, prediction: Prediction):
        issued = self._issued.get((prediction.method, prediction.item_id))
        if issued is None or prediction_digest(prediction) != prediction_digest(issued[0]):
            raise DomainError("unissued_or_changed_prediction")
        item = self._items.get(prediction.item_id)
        if item is None or not self._current(item):
            raise DomainError("issued_source_no_longer_current")
        if issued[1].implementation_sha256 != _implementation():
            raise DomainError("issued_implementation_no_longer_current")
        if type(issued[1]) is BaselineRecord:
            majority.validate_fit(issued[1].fit)
        return issued


@dataclass(frozen=True)
class BaselineRecord:
    """Actual learned-baseline values, deliberately not extraction evidence/candidates."""

    method: str
    config_sha256: str
    implementation_sha256: str
    fit: majority.MajorityFit


def project_record(record):
    if type(record) is BaselineRecord:
        # Decode fresh values from the immutable fit, not shared mutable composite rows.
        return majority.project_fit(record.fit)
    return labels.project_machine(record)


def _check_child_receipts(binding, packet):
    """Validate actual returned public refs against the concrete current binding, not Gold."""
    if packet.status not in {"outcomes_complete", "partial"}:
        return
    if type(binding) is JevBinding:
        children = packet.native_children
        if (
            len(children) != len(binding.plan.children)
            or tuple(x.status for x in children) != packet.lookup_statuses
        ):
            raise DomainError("native_child_inventory_mismatch")
        allocation_ids = set()
        for receipt, child, request in zip(
            children, binding.plan.children, binding.bundle.requests, strict=True
        ):
            context = binding.context.model_copy(update={"child_id": child.child_id})
            prepared = binding.provider.prepare(request, context=context, limits=binding.limits)
            count = receipt.counters
            if (
                receipt.child_id != child.child_id
                or receipt.request_identity_sha256 != prepared.request_identity_sha256
                or count.operation_id != binding.context.operation_id
                or count.child_id != child.child_id
                or count.mode != "offline"
                or count.used_attempts != 0
                or count.repairs_used != 0
            ):
                raise DomainError("native_child_reference_mismatch")
            allocation_ids.add(count.allocation_id)
            if receipt.status == "ok" and (
                receipt.origin != "mock" or receipt.source_capture is None
            ):
                raise DomainError("native_child_capture_required")
            capture = receipt.source_capture
            if capture is not None and (
                capture.origin != "synthetic"
                or capture.request_identity_sha256 != prepared.request_identity_sha256
                or capture.model_requested != request.model
            ):
                raise DomainError("native_capture_binding_mismatch")
        if len(allocation_ids) != 1:
            raise DomainError("mixed_native_allocations")
    else:
        count, capture = packet.child_counters, packet.source_capture
        child = binding.plan.children[0]
        if (
            count is None
            or capture is None
            or (
                count.child_id != child.child_id
                or count.operation_id != binding.context.operation_id
                or count.mode != "simulation"
                or count.used_attempts != packet.child_used_attempts
                or count.repairs_used != packet.child_repairs_used
                or packet.native_origin != "mock"
                or capture.origin != "synthetic"
                or capture.model_requested != binding.bundle.request.model
            )
        ):
            raise DomainError("generation_child_reference_mismatch")
        request = binding.bundle.request
        if count.repairs_used:
            from hiring_signals.shared.providers import build_generation_repair_request

            request = build_generation_repair_request(request, binding.repair_policy)
        context = binding.context.model_copy(update={"child_id": child.child_id})
        expected = binding.provider.prepare(
            request, context=context, limits=binding.limits
        ).request_identity_sha256
        if (
            capture.request_identity_sha256 != expected
            or packet.final_physical_request_sha256 != expected
        ):
            raise DomainError("generation_physical_request_mismatch")


class HiringMethodRunner:
    """Concrete actual rules/controller execution. Its input contains no scorer Gold."""

    def __init__(
        self,
        registry: ExecutionRegistry,
        method: str,
        *,
        config_sha256: str,
        bindings: Mapping[str, JevBinding | GenerationBinding] | None = None,
        majority_fit: majority.MajorityFit | None = None,
    ):
        if type(registry) is not ExecutionRegistry or method not in {
            "rules",
            "jev",
            "generative",
            "dev_majority",
        }:
            raise DomainError("concrete_hiring_method_required")
        if (method == "dev_majority") != (majority_fit is not None):
            raise DomainError("explicit_majority_fit_required")
        self.majority_fit = (
            majority.validate_fit(majority_fit) if majority_fit is not None else None
        )
        TypeAdapter(c.Digest).validate_python(config_sha256, strict=True)
        self.registry, self.method, self.config_sha256 = registry, method, config_sha256
        self.bindings = dict(bindings or {})
        self.implementation_sha256 = _implementation()
        definitions = set()
        for item_id, binding in self.bindings.items():
            if item_id not in registry._items:
                raise DomainError("unrequested_execution_binding")
            expected = JevBinding if method == "jev" else GenerationBinding
            if type(binding) is not expected:
                raise DomainError("wrong_concrete_execution_binding")
            base = (
                binding.context.config_sha256
                if method == "jev"
                else binding.repair_policy.base_config_sha256
            )
            if base != config_sha256:
                raise DomainError("method_configuration_binding_mismatch")
            definition = {
                "provider": binding.provider.config.sha256,
                "model": binding.bundle.requests[0].model
                if method == "jev"
                else binding.bundle.request.model,
                "policy": binding.policy.model_dump(mode="json")
                if method == "jev"
                else {"mode": binding.repair_policy.mode, "total": 2, "repairs": 1},
                "partition": len(binding.bundle.requests) if method == "jev" else 1,
            }
            definitions.add(canonical_digest(definition))
        if len(definitions) > 1 or (method in {"rules", "dev_majority"} and self.bindings):
            raise DomainError("mixed_method_configuration")
        self.version = "hiring/" + canonical_digest(
            {
                "implementation": self.implementation_sha256,
                "config": config_sha256,
                "method": method,
                "definition": sorted(definitions),
                "reference_model": self.majority_fit.model_sha256 if self.majority_fit else None,
            }
        )

    def method_config(self) -> MethodConfig:
        return MethodConfig(self.version, self.config_sha256, "synthetic", self)

    def predict(self, public: PublicMethodInput) -> Prediction:
        if _implementation() != self.implementation_sha256:
            raise DomainError("method_implementation_changed")
        if (self.method, public.item_id) in self.registry._issued:
            raise DomainError("execution_already_issued_no_automatic_reuse")
        public = PublicMethodInput.model_validate_json(public.model_dump_json(warnings="error"))
        item = self.registry._items.get(public.item_id)
        if (
            item is None
            or not self.registry._current(item)
            or (
                public.input_sha256 != item.pin.input_sha256
                or set(public.public_payload) != {"text"}
                or public.public_payload["text"] != item.source.text
            )
        ):
            raise DomainError("method_public_source_mismatch")
        with self.registry.sources.guard(item.pin.item_id):
            if self.method == "dev_majority":
                return self._predict_majority(item)
            controller, refs, model_sha = {}, (), None
            if self.method == "rules":
                classification = rules.classify(item.source)
                controller = {"kind": "rules", "status": _controller_status(classification)}
            else:
                binding = self.bindings.get(item.pin.item_id)
                if binding is None or (
                    binding.source.item_id != item.pin.item_id
                    or binding.source.input_sha256 != item.pin.input_sha256
                    or binding.source.generation != generation(item.pin).evidence_revision
                ):
                    raise DomainError("missing_or_wrong_semantic_source_binding")
                common = dict(
                    pin=item.pin,
                    sources=self.registry.sources,
                    provider=binding.provider,
                    ledger=binding.ledger,
                    budget=binding.budget,
                    context=binding.context,
                    limits=binding.limits,
                    plan=binding.plan,
                )
                if self.method == "jev":
                    packet = jev_adapter.run_jev_offline(
                        binding.source, binding.bundle, policy=binding.policy, **common
                    )
                    controller = json.loads(packet.model_dump_json())
                    controller.pop("classification")
                    controller["kind"] = "jev_offline"
                    refs = tuple(
                        dict.fromkeys(
                            child.accounting_ref
                            for child in packet.native_children
                            if child.accounting_ref is not None
                        )
                    )
                else:
                    packet = generation_adapter.run_generation_simulation(
                        binding.source,
                        binding.bundle,
                        repair_policy=binding.repair_policy,
                        **common,
                    )
                    controller = json.loads(packet.model_dump_json())
                    controller.pop("classification")
                    controller["kind"] = "generation_injected"
                    refs = tuple(
                        dict.fromkeys(
                            ([packet.accounting_ref] if packet.accounting_ref else [])
                            + list(packet.attempt_ids)
                        )
                    )
                classification = packet.classification
                _check_child_receipts(binding, packet)
                if packet.status != _controller_status(classification):
                    raise DomainError("controller_field_status_mismatch")
                model_sha = canonical_digest(
                    {
                        "provider": binding.provider.config.sha256,
                        "model": binding.bundle.requests[0].model
                        if self.method == "jev"
                        else binding.bundle.request.model,
                    }
                )
            record = c.PrivateDerivedRecord(
                schema_version=1,
                item_id=item.pin.item_id,
                month=item.month,
                input_sha256=item.pin.input_sha256,
                taxonomy_sha256=item.pin.taxonomy_sha256,
                config_sha256=self.config_sha256,
                implementation_sha256=self.implementation_sha256,
                method=self.method,
                model_sha256=model_sha,
                provenance=c.LabelProvenance(
                    source="unprovided", actor_ref=None, attestation_sha256=None
                ),
                classification=classification,
            )
            rows = labels.project_machine(record)
            state = controller["status"]
            whole = (
                "ok"
                if state in {"outcomes_complete", "partial"}
                else (
                    "blocked"
                    if state == "blocked"
                    else "invalid"
                    if all(row.error_code == "invalid_output" for row in rows)
                    else "provider_error"
                )
            )
            prediction = Prediction(
                item_id=item.pin.item_id,
                method=self.method,
                method_version=self.version,
                config_sha256=self.config_sha256,
                model=model_sha,
                origin="synthetic",
                status=whole,
                domain_payload={
                    "kind": "hiring-machine/1",
                    "controller_status": state,
                    "rubric_sha256": item.pin.rubric_sha256,
                    "source_generation": generation(item.pin).evidence_revision,
                },
                machine_output={
                    "record": json.loads(record.model_dump_json()),
                    "controller": controller,
                },
                human_effective_output=None,
                human_provenance_ref=None,
                issues=("partial_execution",) if state == "partial" else (),
                ledger_refs=refs,
                source_refs=(SourceRef(handle=item.pin.item_id, sha256=item.pin.input_sha256),),
            )
            # Only concrete execution may issue; supplied/hash-shaped packets are insufficient.
            self.registry._issued[self.method, item.pin.item_id] = (prediction, record)
            return Prediction.model_validate_json(prediction.model_dump_json(warnings="error"))

    def _predict_majority(self, item):
        fit = majority.validate_fit(self.majority_fit)
        fields = majority.project_fit(fit)
        record = BaselineRecord(self.method, self.config_sha256, self.implementation_sha256, fit)
        prediction = Prediction(
            item_id=item.pin.item_id,
            method=self.method,
            method_version=self.version,
            config_sha256=self.config_sha256,
            model=fit.model_sha256,
            origin="synthetic",
            status="ok",
            domain_payload={
                "kind": "hiring-dev-majority/1",
                "controller_status": "outcomes_complete",
                "rubric_sha256": item.pin.rubric_sha256,
                "source_generation": generation(item.pin).evidence_revision,
            },
            machine_output={
                "kind": "learned-dev-constant-values/1",
                "model_sha256": fit.model_sha256,
                "fields": [
                    {"field": row.field_id, "value": row.value, "status": row.process_status}
                    for row in fields
                ],
            },
            human_effective_output=None,
            human_provenance_ref=None,
            issues=("dev_training_resubstitution",),
            ledger_refs=(),
            source_refs=(SourceRef(handle=item.pin.item_id, sha256=item.pin.input_sha256),),
        )
        self.registry._issued[self.method, item.pin.item_id] = (prediction, record)
        return Prediction.model_validate_json(prediction.model_dump_json(warnings="error"))


class HiringDomainAdapter:
    """Actual canonical DomainAdapter plus the optional trusted raw-axis port."""

    def __init__(self, registry: ExecutionRegistry, *, human_authority: Callable | None = None):
        self.registry, self.human_authority = registry, human_authority

    def validate_gold(self, record: GoldRecord) -> None:
        labels.project_reference(record, human_authority=self.human_authority)

    def to_public_input(self, record: GoldRecord, source_view: SourceView) -> PublicMethodInput:
        if type(source_view) is not SourceView or set(source_view.public_payload) != {"text"}:
            raise DomainError("closed_public_source_required")
        item = self.registry._items.get(record.item_id)
        if (
            item is None
            or source_view.input_sha256 != record.input_sha256
            or (source_view.public_payload["text"] != item.source.text)
        ):
            raise DomainError("public_source_binding_mismatch")
        return PublicMethodInput(
            item_id=record.item_id,
            input_sha256=record.input_sha256,
            public_payload={"text": item.source.text},
            public_config_refs=(),
        )

    def validate_prediction(self, prediction: Prediction) -> None:
        if (
            prediction.human_effective_output is not None
            or prediction.human_provenance_ref is not None
        ):
            raise DomainError("human_effective_not_machine")
        _, record = self.registry._lookup(prediction)
        if (
            prediction.origin != "synthetic"
            or record.method != prediction.method
            or (
                record.config_sha256 != prediction.config_sha256
                or tuple(row.field_id for row in project_record(record)) != c.FIELD_IDS
            )
        ):
            raise DomainError("raw_prediction_profile_mismatch")

    def bind(self, prediction: Prediction) -> AxisStatusBinding:
        self.validate_prediction(prediction)
        if prediction.status != "ok":
            raise DomainError("whole_failed_prediction_has_no_axis_authority")
        _, record = self.registry._lookup(prediction)
        return AxisStatusBinding(
            prediction_digest(prediction),
            raw_machine_digest(prediction),
            tuple(
                AxisStatus(row.field_id, None, _field_status(row)) for row in project_record(record)
            ),
        )

    def to_outcomes(
        self, machine: Prediction, gold: GoldRecord, policy: object
    ) -> tuple[Outcome, ...]:
        if policy != "hiring-field-exact/1":
            raise DomainError("fixed_hiring_scoring_policy_required")
        if machine.status == "not_run":
            raise DomainError("never_run_has_no_fake_outcomes")
        reference = labels.project_reference(gold, human_authority=self.human_authority)
        projected = None
        if machine.status == "ok":
            self.validate_prediction(machine)
            projected = project_record(self.registry._lookup(machine)[1])
        elif machine.machine_output is not None:
            # A canonical invalid demotion retains raw execution, never field successes.
            issued = self.registry._issued.get((machine.method, machine.item_id))
            if issued is None or raw_machine_digest(machine) != raw_machine_digest(issued[0]):
                raise DomainError("unissued_failed_raw_output")
        rows = []
        for index, ref in enumerate(reference):
            value = projected[index].value if projected else None
            status = _field_status(projected[index]) if projected else machine.status
            rows.append(
                Outcome(
                    item_id=gold.item_id,
                    group_id=gold.group_id,
                    dataset=gold.dataset,
                    split=gold.split,
                    method=machine.method,
                    field=ref.field_id,
                    **{"class": None},
                    eligibility="eligible" if ref.eligible else "unlabelled",
                    status=status,
                    correct=typed_equal(value, ref.value)
                    if ref.eligible and status == "ok"
                    else None,
                    predicted=value,
                    expected=ref.value,
                    human_touched_prediction=False,
                    evidence_origin=machine.origin,
                    issues=machine.issues,
                    ledger_refs=machine.ledger_refs,
                )
            )
        return tuple(rows)

    def metric_specs(self) -> tuple[MetricSpec, ...]:
        return (
            MetricSpec(
                metric="accuracy",
                statistic_version="hiring-field-exact/1",
                population="as_frozen",
                denominator_policy="all-eligible/1",
                zero_denominator_reason="zero_support",
                averaging="none",
            ),
        )

    def public_projection_policy(self) -> PublicProjectionPolicy:
        # Private comparator implementation emits no public quality metrics by default.
        return PublicProjectionPolicy(
            mode="aggregate_only",
            allowed_dimensions=(),
            allowed_value_sets={},
            allowed_numeric_metrics=(),
            synthetic_example_refs=(),
        )


def compare_hiring(corpus_root, manifest, split, methods, adapter, **heldout_authority):
    """Actual frozen reader and canonical compare, with no disabled-live bypass or custom runner.

    Heldout still requires its separate actual seal/history/admission. This library
    supplies none and authors no Gold. Returned outcomes/Gold remain private.
    """
    if type(adapter) is not HiringDomainAdapter:
        raise DomainError("trusted_hiring_adapter_required")
    if set(heldout_authority) - {"heldout_admission", "heldout_history"}:
        raise DomainError("unknown_hiring_comparison_authority")
    if split == "heldout" and any(
        heldout_authority.get(name) is None for name in ("heldout_admission", "heldout_history")
    ):
        # The canonical runner checks the full seal/config/history before dispatch.
        # The caller additionally needs actual separate rights to read these bodies;
        # merely supplying these objects does not confer that permission.
        raise DomainError("heldout_admission_and_history_required_before_data_read")
    for method, config in methods.items():
        if (
            method not in {"rules", "jev", "generative", "dev_majority"}
            or type(config) is not MethodConfig
        ):
            raise DomainError("declared_hiring_methods_required")
        runner = config.runner
        if runner is not None and (
            type(runner) is not HiringMethodRunner
            or (
                runner.registry is not adapter.registry
                or runner.method != method
                or config.version != runner.version
                or config.config_sha256 != runner.config_sha256
                or config.origin != "synthetic"
            )
        ):
            raise DomainError("untrusted_or_changed_method_configuration")
    records = load_corpus(corpus_root, manifest, split, adapter)
    return compare(
        methods,
        manifest,
        split,
        records,
        adapter,
        "hiring-field-exact/1",
        adapter.registry.source_view,
        axis_status_port=adapter,
        **heldout_authority,
    )
