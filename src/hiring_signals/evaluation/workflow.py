"""Explicit keyless synthetic DEV rules workflow; private outputs and no heldout reader.

An origin string or hash is not source rights, independent Gold or human authority.
Owners supply and admit inputs before invoking this bounded local workflow.
"""

import hashlib
import os
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter

from hiring_signals import contracts as c
from hiring_signals.adapters.rulings import SourceAuthority
from hiring_signals.annotation.models import SourcePin
from hiring_signals.extract import rules
from hiring_signals.reporting import limitations as report_limitations
from hiring_signals.shared.callledger.models import decode_wire_json
from hiring_signals.shared.evalkit.corpus import contained_corpus_path, load_corpus
from hiring_signals.shared.evalkit.identity import canonical_bytes
from hiring_signals.shared.evalkit.models import Manifest
from hiring_signals.shared.evalkit.runner import MethodConfig
from hiring_signals.shared.skill_dictionary import core as dictionary

from . import domain, metrics, sample_report

PRODUCT_ROOT = Path(__file__).resolve().parents[3]
MAX_SOURCE_BYTES = 8 * 1024 * 1024
MAX_ROWS = 512
DENIED = {
    ".creds",
    ".chatexports",
    ".agent-registry",
    ".thinking",
    ".agent-work",
    ".git",
    "heldout",
    "private-scratch",
}


class EvaluationError(ValueError):
    def __init__(self, code, *, private_effects_possible=False):
        super().__init__(code)
        self.code, self.private_effects_possible = code, private_effects_possible


class SyntheticDevSource(c.ClosedModel):
    item_id: c.Digest
    source_id: Annotated[int, Field(gt=0)]
    month: c.Month
    group_id: c.Digest
    split: Literal["dev"]
    text: Annotated[str, Field(min_length=1, max_length=c.MAX_INPUT_BYTES, repr=False)]
    input_sha256: c.Digest

    def __reduce_ex__(self, protocol):
        raise TypeError("transient_source_serialization_forbidden")


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def bindings():
    """Pathless actual local execution pins for a separately prepared DEV manifest."""
    taxonomy = _sha(canonical_bytes({"fields": c.FIELD_IDS, "skills": c.SKILL_IDS}))
    rubric = _sha((PRODUCT_ROOT / "docs/annotation-guide.md").read_bytes())
    domain_sha = domain._implementation()
    config = _sha(
        canonical_bytes(
            {
                "version": "synthetic-dev-rules/1",
                "taxonomy": taxonomy,
                "rubric": rubric,
                "domain": domain_sha,
                "dictionary_catalog": dictionary.catalog_sha256(),
                "source": {
                    name: _sha(Path(module.__file__).read_bytes())
                    for name, module in (
                        ("workflow", __import__(__name__, fromlist=["*"])),
                        ("rules", rules),
                        ("dictionary", dictionary),
                        ("metrics", metrics),
                        ("sample_report", sample_report),
                        ("report_limitations", report_limitations),
                    )
                },
                "population": "all37fields/allfrozenDEV/1",
                "projection": "private-only/1",
                "method": "rules",
                "methods_not_run": ("jev", "generative", "dev_majority"),
            }
        )
    )
    return {
        "kind": "synthetic-dev-rules-bindings/1",
        "config_sha256": config,
        "domain_adapter_sha256": domain_sha,
        "taxonomy_sha256": taxonomy,
        "rubric_sha256": rubric,
        "scorer_version": "hiring-field-exact/1",
        "private_projection": "private-only/1",
        "support_policy": "no_fit_or_intervals/1",
    }


def _safe_input(path, suffix):
    path = Path(path).absolute()
    if path.suffix.lower() != suffix or any(part.casefold() in DENIED for part in path.parts):
        raise EvaluationError("evaluation_input_refused")
    try:
        return contained_corpus_path(path.parent, path.name)
    except Exception:
        raise EvaluationError("evaluation_input_refused") from None


def _read(path, *, suffix, maximum, sha):
    try:
        TypeAdapter(c.Digest).validate_python(sha, strict=True)
        path = _safe_input(path, suffix)
        if not 0 < path.stat().st_size <= maximum:
            raise ValueError()
        with path.open("rb") as stream:
            data = stream.read(maximum + 1)
        if len(data) > maximum or _sha(data) != sha:
            raise ValueError()
        return data
    except EvaluationError:
        raise
    except Exception:
        raise EvaluationError("evaluation_input_bytes_or_hash_refused") from None


def _new_private_output(destination):
    destination = Path(destination).absolute()
    if (
        os.path.lexists(destination)
        or any(part.casefold() in DENIED for part in destination.parts)
        or not destination.parent.is_dir()
    ):
        raise EvaluationError("new_private_output_required")
    # Reuse canonical ancestor/reparse checks with an actual existing directory member.
    try:
        from hiring_signals.shared.evalkit.corpus import _is_link

        if any(_is_link(part) for part in (*destination.parent.parents, destination.parent)):
            raise ValueError()
        resolved = destination.resolve()
        if resolved.is_relative_to(PRODUCT_ROOT.resolve()) or PRODUCT_ROOT.resolve().is_relative_to(
            resolved
        ):
            raise ValueError()
    except Exception:
        raise EvaluationError("private_output_outside_checkout_required") from None
    return destination


def _wire(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if is_dataclass(value):
        return _wire(asdict(value))
    if type(value) is dict:
        return {key: _wire(item) for key, item in value.items()}
    if type(value) in (tuple, list):
        return [_wire(item) for item in value]
    return value


def _markdown(summary):
    rules_result = summary["methods"]["rules"]
    lines = [
        "# Private synthetic DEV rules evaluation",
        "",
        "Reference labels are synthetic/agent-provisional. This is development functionality,",
        "not heldout quality, human agreement, production calibration or a public release.",
        "",
        "| Field | Eligible | Answered | End-to-end accuracy | Accuracy on answered |",
        "|---|---:|---:|---:|---:|",
    ]

    def number(stat):
        return "NA" if stat["value"] is None else format(stat["value"], ".4f")

    for field, result in rules_result["metrics"]["fields"].items():
        lines.append(
            f"| {field} | {result['eligibility'].get('eligible', 0)} | "
            f"{result['answered_coverage']['numerator']} | "
            f"{number(result['end_to_end_accuracy'])} | "
            f"{number(result['accuracy_on_answered'])} |"
        )
    lines += [
        "",
        "All class supports/confusions/P/R/F1, skill-set and salary coverage details are",
        "in private-summary.json. Missing confidence stays unmeasured. Jev, generative and",
        "dev-majority methods were not run. No thresholds, bootstrap or defaults were fit.",
        "",
    ]
    return "\n".join(lines).encode()


def execute_dev_rules(
    manifest_path,
    *,
    manifest_sha256,
    sources_path,
    sources_sha256,
    destination,
    sample_months=None,
    sample_policy="v1",
):
    """One actual fixed DEV rules pass, with no model/capture/heldout/Gold authoring."""
    created = False
    try:
        output = _new_private_output(destination)
        from hiring_signals.shared.aggregate_privacy import models as privacy

        if sample_policy not in {"v1", "v2"} or (sample_months is None and sample_policy != "v1"):
            raise EvaluationError("sample_window_required_for_release_policy")
        policy = privacy.POLICY_V1 if sample_policy == "v1" else privacy.POLICY_V2
        if sample_months is not None:
            sample_report.validate_window(sample_months, policy)
        actual = bindings()
        manifest_data = _read(
            manifest_path, suffix=".json", maximum=1024 * 1024, sha=manifest_sha256
        )
        manifest = Manifest.model_validate_json(
            canonical_bytes(decode_wire_json(manifest_data.decode("utf-8"), max_bytes=1024 * 1024))
        )
        if (
            manifest.scorer_version != actual["scorer_version"]
            or manifest.domain_adapter_ref.status != "available"
            or manifest.domain_adapter_ref.sha256 != actual["domain_adapter_sha256"]
            or manifest.comparator_config.status != "available"
            or manifest.comparator_config.sha256 != actual["config_sha256"]
        ):
            raise EvaluationError("frozen_execution_binding_changed")
        for field in ("taxonomy", "rubric"):
            ref = manifest.experiment_refs.get(field)
            if ref is None or ref.status != "available" or ref.sha256 != actual[field + "_sha256"]:
                raise EvaluationError("frozen_taxonomy_or_rubric_binding_changed")
        entries = [entry for entry in manifest.splits if entry.split == "dev"]
        if len(entries) != 1 or not 1 <= entries[0].item_count <= MAX_ROWS:
            raise EvaluationError("bounded_nonempty_dev_split_required")
        entry = entries[0]
        root = Path(manifest_path).absolute().parent
        _safe_input(root / entry.items_file, ".jsonl")
        source_data = _read(
            sources_path, suffix=".jsonl", maximum=MAX_SOURCE_BYTES, sha=sources_sha256
        )
        lines = source_data.splitlines()
        if len(lines) != entry.item_count or any(
            not line or len(line) > 64 * 1024 for line in lines
        ):
            raise EvaluationError("source_row_population_or_limit")
        source_rows = tuple(
            SyntheticDevSource.model_validate_json(
                canonical_bytes(decode_wire_json(line.decode("utf-8"), max_bytes=64 * 1024))
            )
            for line in lines
        )
        if sample_months is not None and any(row.month not in sample_months for row in source_rows):
            raise EvaluationError("sample_source_outside_declared_window")
        if tuple(row.item_id for row in source_rows) != entry.ordered_item_ids or len(
            {row.source_id for row in source_rows}
        ) != len(source_rows):
            raise EvaluationError("source_frozen_order_changed")
        sources, items = SourceAuthority(), []
        source_map = {}
        for row in source_rows:
            text = row.text
            if (
                not text.isascii()
                or any(ord(char) < 32 and char not in "\n\t" for char in text)
                or text != text.strip()
                or "\r" in text
                or "<" in text
                or ">" in text
                or _sha(text.encode()) != row.input_sha256
                or row.item_id not in manifest.group_members.get(row.group_id, ())
                or manifest.group_split_map.get(row.group_id) != "dev"
            ):
                raise EvaluationError("synthetic_source_or_group_binding_changed")
            transient = c.TransientInput(text=text, input_sha256=row.input_sha256)
            pin = SourcePin(
                item_id=row.item_id,
                raw_source_sha256=row.input_sha256,
                input_sha256=row.input_sha256,
                evidence_revision_sha256=sources_sha256,
                taxonomy_sha256=actual["taxonomy_sha256"],
                rubric_sha256=actual["rubric_sha256"],
            )
            sources.install(pin, transient)
            items.append(domain.SourceItem(pin, transient, row.month))
            source_map[row.item_id] = row
        registry = domain.ExecutionRegistry(tuple(items), sources)
        adapter = domain.HiringDomainAdapter(registry)
        # Actual canonical frozen reader, only DEV. No human authority is injected.
        gold_data = _read(
            root / entry.items_file,
            suffix=".jsonl",
            maximum=10 * 1024 * 1024,
            sha=entry.items_sha256,
        )
        # Reject duplicate keys/nonfinite literals before the unchanged canonical reader.
        for line in gold_data.splitlines():
            decode_wire_json(line.decode("utf-8"), max_bytes=64 * 1024)
        gold = load_corpus(root, manifest, "dev", adapter, max_rows=MAX_ROWS)
        for reference in gold:
            row = source_map[reference.item_id]
            if (
                reference.label_source not in {"synthetic", "agent_provisional"}
                or reference.input_sha256 != row.input_sha256
                or reference.group_id != row.group_id
                or reference.source_ref.sha256 != row.input_sha256
            ):
                raise EvaluationError("synthetic_reference_source_binding_changed")
        if bindings() != actual:
            raise EvaluationError("execution_changed_before_dispatch")
        runner = domain.HiringMethodRunner(registry, "rules", config_sha256=actual["config_sha256"])
        methods = {"rules": runner.method_config()} | {
            name: MethodConfig("not-run/1", actual["config_sha256"], "synthetic", None)
            for name in ("jev", "generative", "dev_majority")
        }
        # Revalidate through canonical compare without reopening any input after dispatch.
        comparison = domain.compare(
            methods,
            manifest,
            "dev",
            gold,
            adapter,
            "hiring-field-exact/1",
            registry.source_view,
            axis_status_port=adapter,
        )
        summary = metrics.private_summary(comparison, adapter)
        sample = None
        if sample_months is not None:
            sample = sample_report.build(
                registry,
                expected_item_ids=comparison.frozen_item_ids,
                predictions=comparison.methods["rules"].actual_predictions,
                month_ids=sample_months,
                policy=policy,
            )
        if bindings() != actual:
            raise EvaluationError("execution_changed_during_run")
        # Inputs remain frozen; do not manufacture a successor after a concurrent change.
        _read(manifest_path, suffix=".json", maximum=1024 * 1024, sha=manifest_sha256)
        _read(sources_path, suffix=".jsonl", maximum=MAX_SOURCE_BYTES, sha=sources_sha256)
        gold_path = _safe_input(root / entry.items_file, ".jsonl")
        _read(gold_path, suffix=".jsonl", maximum=10 * 1024 * 1024, sha=entry.items_sha256)
        summary = _wire(summary)
        run = {
            "kind": "private-synthetic-dev-run/1",
            "bindings": actual,
            "manifest_sha256": manifest_sha256,
            "sources_sha256": sources_sha256,
            "dev_gold_sha256": entry.items_sha256,
            "ordered_ids_sha256": entry.ordered_ids_sha256,
            "count": len(gold),
            "field_outcomes": len(comparison.methods["rules"].outcomes),
            "method_version": runner.version,
            "reference_origins": sorted({g.label_source for g in gold}),
            "execution": summary["methods"]["rules"]["execution"],
            "provider_attempts": 0,
            "heldout_read": False,
            "public_release": "not_authorized",
            "human_agreement": None,
            "bootstrap": "not_run",
            "threshold_fit": "not_run",
            "semantic_methods": "not_run",
            "sample_projection": {
                "month_ids": sample_months,
                "policy": policy,
                "source_scope": "gold_sample",
            }
            if sample is not None
            else None,
        }
        files = {
            "private-summary.json": canonical_bytes(summary) + b"\n",
            "private-metrics.md": _markdown(summary),
            "run.json": canonical_bytes(run) + b"\n",
        }
        if sum(map(len, files.values())) > 4 * 1024 * 1024:
            raise EvaluationError("private_output_limit")
        output.mkdir(mode=0o700)
        created = True
        for name, data in files.items():
            with (output / name).open("xb") as stream:
                stream.write(data)
        if sample is not None:
            from hiring_signals.reporting import render

            sample_directory = output / "sample-report"
            render.export_report(sample, sample_directory)
            if render.verify_report(sample_directory) != sample:
                raise EvaluationError("sample_report_verification_failed")
            files["sample-limitations.md"] = sample_report.limitations(sample).encode("utf-8")
            with (output / "sample-limitations.md").open("xb") as stream:
                stream.write(files["sample-limitations.md"])
            for name in (*render.ASSETS, "manifest.json"):
                files["sample-report/" + name] = (sample_directory / name).read_bytes()
        seal = {
            "kind": "private-synthetic-dev-artifacts/1",
            "files": {
                name: {"sha256": _sha(data), "bytes": len(data)} for name, data in files.items()
            },
        }
        with (output / "artifact-manifest.json").open("xb") as stream:
            stream.write(canonical_bytes(seal) + b"\n")
        return {
            "status": run["execution"],
            "scope": "synthetic_dev_rules_only",
            "count": run["count"],
            "field_outcomes": run["field_outcomes"],
            "provider_attempts": 0,
            "semantic_methods": "not_run",
            "heldout_read": False,
            "sample_report": "local_closed_projection" if sample is not None else "not_requested",
            "public_release": "not_authorized",
            "artifact_manifest_sha256": _sha((output / "artifact-manifest.json").read_bytes()),
        }
    except EvaluationError as error:
        raise EvaluationError(error.code, private_effects_possible=created) from None
    except (Exception, KeyboardInterrupt):
        raise EvaluationError(
            "evaluation_failed_or_cancelled", private_effects_possible=created
        ) from None
