"""Bounded caller-supplied original-synthetic rules workflow and public report IO.

No network, provider, credential loader, Gold authoring or implicit sample data.
Private partial effects are reported honestly if a later step fails.
"""

import hashlib
import json
import math
from pathlib import Path

from hiring_signals import contracts as c
from hiring_signals.extract import rules
from hiring_signals.ingest import redaction, transport
from hiring_signals.ingest.private_state import PrivateState
from hiring_signals.reporting import population as pop
from hiring_signals.reporting import render
from hiring_signals.shared.aggregate_privacy import models as privacy
from hiring_signals.shared.callledger.models import canonical_digest, decode_wire_json
from hiring_signals.shared.skill_dictionary import core as dictionary

MAX_RUN_BYTES = 48 * 1024 * 1024
PRODUCT_ROOT = Path(__file__).resolve().parents[2]
PRIVATE_INPUT_PARTS = {
    ".creds",
    ".chatexports",
    ".agent-registry",
    ".thinking",
    ".agent-work",
    ".git",
}


class WorkflowError(ValueError):
    def __init__(self, code: str, *, private_effects_possible=False):
        super().__init__(code)
        self.code, self.private_effects_possible = code, private_effects_possible


def bounded_json_file(path: Path, *, maximum: int):
    """Owner-selected .json only, not an instruction, credential or export path."""
    path = Path(path)
    try:
        resolved = path.resolve(strict=True)
        if (
            path.suffix.lower() != ".json"
            or path.is_symlink()
            or any(part.lower() in PRIVATE_INPUT_PARTS for part in (*path.parts, *resolved.parts))
            or not resolved.is_file()
            or not 0 < resolved.stat().st_size <= maximum
        ):
            raise WorkflowError("input_file_refused")
        with resolved.open("rb") as handle:
            raw = handle.read(maximum + 1)
        if len(raw) > maximum:
            raise WorkflowError("input_file_refused")
        return decode_wire_json(raw.decode("utf-8"), max_bytes=maximum)
    except WorkflowError:
        raise
    except (OSError, ValueError, RecursionError):
        raise WorkflowError("invalid_bounded_json_input") from None


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise WorkflowError("invalid_synthetic_manifest")


def _source_id(value):
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise WorkflowError("invalid_synthetic_manifest")
    return value


def _review(value):
    _keys(
        value, ("source_id", "identities_reviewed", "identity_terms", "organization", "link_kinds")
    )
    _source_id(value["source_id"])
    terms, links, organization = value["identity_terms"], value["link_kinds"], value["organization"]
    if (
        type(value["identities_reviewed"]) is not bool
        or type(terms) is not list
        or len(terms) > 200
        or any(type(term) is not str or not 1 <= len(term) <= 256 for term in terms)
        or type(links) is not list
        or len(links) > 200
        or any(link not in {"portfolio", "github", "application", "other"} for link in links)
    ):
        raise WorkflowError("invalid_identity_review")
    if organization is not None and (
        type(organization) is not str
        or not organization.strip()
        or len(organization) > 256
        or organization.casefold() not in {term.casefold() for term in terms}
    ):
        raise WorkflowError("organization_must_be_in_reviewed_identity_inventory")
    return value


class _Batch:
    __slots__ = ("months", "reviews")

    def __init__(self, months, reviews):
        self.months, self.reviews = months, reviews

    def __repr__(self):
        return "OriginalSyntheticBatch(<transient source and reviews omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("transient_batch_serialization_forbidden")


def _parse_batch(document) -> _Batch:
    _keys(document, ("schema_version", "origin", "months"))
    if (
        type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["origin"] != "original_synthetic"
        or type(document["months"]) is not list
        or len(document["months"]) != 4
    ):
        raise WorkflowError("original_synthetic_four_month_manifest_required")
    requests, reviews, roots = [], [], set()
    for index, month in enumerate(document["months"]):
        _keys(month, ("month", "root_id", "origin", "response", "reviews"))
        root_id = _source_id(month["root_id"])
        if (
            root_id in roots
            or type(month["response"]) is not dict
            or type(month["reviews"]) is not list
            or len(month["reviews"]) > 600
        ):
            raise WorkflowError("invalid_synthetic_manifest")
        roots.add(root_id)
        by_id = {}
        for value in month["reviews"]:
            review = _review(value)
            source_id = review["source_id"]
            if source_id in by_id:
                raise WorkflowError("duplicate_identity_review")
            by_id[source_id] = review
        reviews.append(by_id)
        requests.append(
            transport.LocalMonthRequest(
                month=month["month"],
                root_id=root_id,
                origin=month["origin"],
                attempts=(
                    transport.LocalAttempt(
                        body=json.dumps(
                            month["response"], ensure_ascii=False, allow_nan=False
                        ).encode(),
                        status=200,
                        started=index * 1.1,
                        duration=0.01,
                        retry_after=None,
                    ),
                ),
            )
        )
    try:
        months = transport.read_synthetic_run(tuple(requests))
        # Validate exact consecutive public month slots before any private state is created.
        render.ReportWindow(
            schema_version=1,
            month_ids=tuple(m.coverage.month for m in months),
            method="rules",
            source_scope="original_synthetic_population",
            quality_status="not_measured",
            months=(),
        )
    except (ValueError, TypeError, RecursionError):
        raise WorkflowError("synthetic_source_or_months_refused") from None
    seen = set(roots)
    for month, inventory in zip(months, reviews, strict=True):
        ids = {post.source_id for post in month.posts}
        if seen & ids:
            raise WorkflowError("duplicate_source_id_across_months")
        seen |= ids
        if month.coverage.status == "complete" and set(inventory) - ids:
            raise WorkflowError("review_inventory_does_not_match_source")
    return _Batch(months, reviews)


def _implementation_sha256():
    paths = {
        "workflow": Path(__file__),
        "rules": Path(rules.__file__),
        "dictionary": Path(dictionary.__file__),
        "privacy": Path(redaction.__file__),
        "contracts": Path(c.__file__),
    }
    return canonical_digest(
        {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()}
    )


def _new_output(destination: Path):
    if Path(destination).exists() or Path(destination).is_symlink():
        raise WorkflowError("output_already_exists")


def execute_rules(
    input_path: Path,
    *,
    private_directory: Path,
    destination: Path,
    lease_seconds: float,
    policy: str,
):
    """No default lease/policy, no live source import, no raw-input copies or model calls."""
    if policy not in {privacy.POLICY_V1, privacy.POLICY_V2}:
        raise WorkflowError("invalid_release_policy")
    if (
        type(lease_seconds) not in {int, float}
        or not math.isfinite(lease_seconds)
        or lease_seconds <= 0
    ):
        raise WorkflowError("finite_explicit_lease_required")
    _new_output(destination)
    private, output = Path(private_directory).resolve(), Path(destination).resolve()
    if private.is_relative_to(output) or output.is_relative_to(private):
        raise WorkflowError("private_state_and_public_output_must_be_separate")
    document = bounded_json_file(input_path, maximum=MAX_RUN_BYTES)
    try:
        batch = _parse_batch(document)
    except WorkflowError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise WorkflowError("invalid_synthetic_manifest") from None
    del document
    taxonomy = canonical_digest(
        {
            "version": "taxonomy-v1",
            "ratification": "pending",
            "fields": list(c.FIELD_IDS),
            "skills": list(c.SKILL_IDS),
        }
    )
    config = canonical_digest(
        {
            "workflow": "original-synthetic-rules/1",
            "policy": policy,
            "rubric": "pending",
            "models": "not_run",
        }
    )
    implementation = _implementation_sha256()
    version = canonical_digest(
        {
            "method": "rules",
            "model_sha256": None,
            "taxonomy_sha256": taxonomy,
            "config_sha256": config,
            "implementation_sha256": implementation,
        }
    )
    state = None
    try:
        state = PrivateState(private_directory, product_root=PRODUCT_ROOT)
        lease = state.begin(lease_seconds=lease_seconds)
        if any(record.method != "rules" for record in state.read_records(lease=lease)):
            raise WorkflowError(
                "other_method_state_requires_separate_run", private_effects_possible=True
            )
        public = []
        for month, inventory in zip(batch.months, batch.reviews, strict=True):
            expected, records = [], []
            for post in month.posts:
                expected.append(state.item_id(post.source_id))
                review = inventory.get(post.source_id)
                if review is None or not review["identities_reviewed"]:
                    continue
                prepared = redaction.prepare_synthetic(
                    post,
                    identity_terms=tuple(review["identity_terms"]),
                    identities_reviewed=True,
                    link_kinds=tuple(review["link_kinds"]),
                )
                if prepared.envelope is None:
                    continue
                try:
                    item_id = state.register_source(
                        source_id=post.source_id,
                        month=month.coverage.month,
                        raw_sha256=prepared.raw_sha256,
                        input_sha256=prepared.envelope.input_sha256,
                        organization=review["organization"],
                        lease=lease,
                    )
                    record = rules.classify_and_store(
                        prepared.envelope,
                        state=state,
                        lease=lease,
                        item_id=item_id,
                        month=month.coverage.month,
                        taxonomy_sha256=taxonomy,
                        config_sha256=config,
                        implementation_sha256=implementation,
                    )
                    records.append(record)
                finally:
                    prepared.envelope.text = ""
                    post.text = ""
            public.append(
                pop.aggregate_month(
                    pop.MonthlyCohort(
                        month=month.coverage.month,
                        method="rules",
                        version_sha256=version,
                        source_scope="original_synthetic_population",
                        source_coverage=month.coverage.status,
                        method_status="run",
                        missing_status="blocked",
                        policy=policy,
                        expected_ids=tuple(expected),
                        records=tuple(records),
                    )
                )
            )
        window = render.ReportWindow(
            schema_version=1,
            month_ids=tuple(month.coverage.month for month in batch.months),
            method="rules",
            source_scope="original_synthetic_population",
            quality_status="not_measured",
            months=tuple(public),
        )
        manifest = render.export_report(window, destination)
        verified = render.verify_report(destination)
        if verified != window:
            raise WorkflowError("report_verification_failed", private_effects_possible=True)
        complete = all(
            m.source_coverage == "complete" and m.method_status == "outcomes_complete"
            for m in public
        )
        status = (
            "partial"
            if not complete
            else "outcomes_complete"
            if any(month.posts for month in batch.months)
            else "no_eligible_input"
        )
        return {
            "schema_version": 1,
            "stage": "original_synthetic_rules",
            "complete_workflow": False,
            "status": status,
            "source_scope": "original_synthetic_population",
            "quality_status": "not_measured",
            "report_sha256": manifest.window_sha256,
            "months": [
                {
                    "month": m.month,
                    "source_coverage": m.source_coverage,
                    "method_status": m.method_status,
                }
                for m in public
            ],
            "required_independent_fixture_gold": "pending",
            "provider_calls": 0,
        }
    except WorkflowError:
        raise
    except Exception:
        raise WorkflowError("synthetic_workflow_failed", private_effects_possible=True) from None
    finally:
        for month in batch.months:
            for post in month.posts:
                post.text = ""
        for inventory in batch.reviews:
            inventory.clear()
        if state is not None:
            state.close()


def export_public_report(input_path: Path, destination: Path):
    _new_output(destination)
    document = bounded_json_file(input_path, maximum=render.MAX_ASSET_BYTES)
    try:
        window = render.ReportWindow.model_validate_json(json.dumps(document))
        manifest = render.export_report(window, destination)
        render.verify_report(destination)
        return {
            "status": "local_report_verified",
            "window_sha256": manifest.window_sha256,
            "quality_status": "not_measured",
            "source_scope": window.source_scope,
        }
    except Exception:
        raise WorkflowError("public_report_failed") from None


def verify_public_report(directory: Path):
    try:
        resolved = Path(directory).resolve(strict=True)
        if any(part.lower() in PRIVATE_INPUT_PARTS for part in resolved.parts):
            raise WorkflowError("input_directory_refused")
        window = render.verify_report(directory)
    except WorkflowError:
        raise
    except Exception:
        raise WorkflowError("public_report_verification_failed") from None
    return {
        "status": "local_report_verified",
        "quality_status": "not_measured",
        "source_scope": window.source_scope,
        "recipient_delivery": "not_established",
    }
