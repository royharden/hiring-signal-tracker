"""Input-free original synthetic wiring demo over the existing rules/report workflow.

Four authored records are not Gold, a benchmark or a population measurement.
Private synthetic processing state is temporary; only closed reports survive.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from hiring_signals import resources, workflow
from hiring_signals.ingest.transport import month_title
from hiring_signals.reporting import render
from hiring_signals.shared.aggregate_privacy.models import POLICY_V1
from hiring_signals.shared.evalkit.corpus import _is_link
from hiring_signals.shared.evalkit.identity import canonical_bytes

MONTHS = ("2026-07", "2026-08", "2026-09", "2026-10")
DEMO_VERSION = "original-four-record-wiring/1"
FIXTURE_SHA256 = "bc6e69698a6346555443d42c33192e6d57819e96cad25715f3ad58ddfc69032e"
IDENTITY = "SYNTHETIC_DEMO_COMPANY_CANARY"
AUTHOR = "SYNTHETIC_DEMO_AUTHOR_CANARY"


class DemoError(ValueError):
    def __init__(self, code, *, effects_possible=False):
        super().__init__(code)
        self.code, self.effects_possible = code, effects_possible


def document():
    """Original tiny owned stimuli, deliberately no reference labels or generator set."""
    texts = (
        "Duties: build ML systems\nRequirements: Python\nWork mode: remote",
        "Duties: sell software\nRequirements: TypeScript\nEmployment: contract",
        "Requirements: Rust\nApplication instructions: send portfolio\nSeniority: senior",
        "Requirements: SQL\nSalary: USD100 per fortnight",
    )
    months = []
    for index, (month, text) in enumerate(zip(MONTHS, texts, strict=True)):
        root_id, source_id = 910000 + index, 920000 + index
        months.append(
            {
                "month": month,
                "root_id": root_id,
                "origin": f"https://hn.algolia.com/api/v1/items/{root_id}",
                "response": {
                    "id": root_id,
                    "type": "story",
                    "title": month_title(month),
                    "children": [
                        {
                            "id": source_id,
                            "type": "comment",
                            "text": IDENTITY + "\n" + text,
                            "author": AUTHOR,
                        }
                    ],
                },
                "reviews": [
                    {
                        "source_id": source_id,
                        "identities_reviewed": True,
                        "identity_terms": [IDENTITY],
                        "organization": IDENTITY,
                        "link_kinds": [],
                    }
                ],
            }
        )
    return {"schema_version": 1, "origin": "original_synthetic", "months": months}


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _destination(value):
    path = Path(value).absolute()
    denied = workflow.PRIVATE_INPUT_PARTS | {"heldout", "private-scratch"}
    if (
        os.path.lexists(path)
        or not path.parent.is_dir()
        or any(part.casefold() in denied for part in path.parts)
        or any(_is_link(parent) for parent in (path.parent, *path.parent.parents))
    ):
        raise DemoError("new_unlinked_demo_destination_required")
    resolved, product = path.resolve(), resources.PRODUCT_ROOT.resolve()
    if resolved.is_relative_to(product) or product.is_relative_to(resolved):
        raise DemoError("demo_destination_outside_product_required")
    return path


def execute(destination=None):
    """Run the real privacy/rules/private-state/report join without caller inputs or keys."""
    output = None
    processing_started = False
    try:
        output = _destination(
            destination
            if destination is not None
            else Path(tempfile.gettempdir()) / ("hst-demo-" + uuid4().hex)
        )
        fixture = canonical_bytes(document())
        if _sha(fixture) != FIXTURE_SHA256:
            raise DemoError("demo_fixture_binding_changed")
        # Validate every built-in record before making even temporary private state.
        workflow._parse_batch(json.loads(fixture))
        implementation = _sha(Path(__file__).read_bytes())
        rules_implementation = workflow._implementation_sha256()
        with tempfile.TemporaryDirectory(prefix="hst-demo-processing-") as scratch:
            processing_started = True
            scratch = Path(scratch)
            source = scratch / "original-synthetic.json"
            source.write_bytes(fixture)
            result = workflow.execute_rules(
                source,
                private_directory=scratch / "private",
                destination=output,
                lease_seconds=30,
                policy=POLICY_V1,
            )
            window = render.verify_report(output)
            if (
                window.month_ids != MONTHS
                or window.source_scope != "original_synthetic_population"
                or result["status"] != "outcomes_complete"
                or result["provider_calls"] != 0
                or workflow._implementation_sha256() != rules_implementation
                or _sha(Path(__file__).read_bytes()) != implementation
                or canonical_bytes(document()) != fixture
            ):
                raise DemoError(
                    "demo_execution_binding_or_completion_changed", effects_possible=True
                )
        return {
            "status": "offline_demo_complete",
            "demo_version": DEMO_VERSION,
            "scope": "four_original_synthetic_wiring_records_only",
            "complete_workflow": False,
            "quality_status": "not_measured",
            "provider_calls": 0,
            "external_cost_usd": "0",
            "semantic_methods": "not_run",
            "human_or_heldout": "not_run",
            "required_independent_fixture_gold": "pending",
            "fixture_sha256": _sha(fixture),
            "demo_implementation_sha256": implementation,
            "rules_implementation_sha256": rules_implementation,
            "report_manifest_sha256": _sha((output / "manifest.json").read_bytes()),
            "report_directory": str(output),
            "report_entry": "report.html",
            "month_ids": list(MONTHS),
            "chart": "suppressed_small_cohorts_no_observed_points",
            "private_processing_state": "temporary_removed",
        }
    except DemoError:
        raise
    except (Exception, KeyboardInterrupt):
        raise DemoError(
            "offline_demo_failed_or_cancelled",
            effects_possible=processing_started or (output is not None and os.path.lexists(output)),
        ) from None
