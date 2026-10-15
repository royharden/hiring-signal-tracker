"""Original closed-output controls, not model performance or a repair runtime."""

import json
from pathlib import Path

import pytest

from hiring_signals import contracts as c
from hiring_signals.adapters.screen import screen_redacted
from hiring_signals.extract import generative as g
from hiring_signals.extract.semantic import SemanticInput
from hiring_signals.ingest.redaction import prepare_synthetic
from hiring_signals.ingest.transport import SyntheticPost
from hiring_signals.shared.providers.schema import check_schema


def context(text="Requirements: Python\nSalary: USD100 per fortnight"):
    redacted = prepare_synthetic(
        SyntheticPost(1, text), identity_terms=(), identities_reviewed=True, link_kinds=()
    )
    gate = screen_redacted(redacted, item_id="a" * 64, generation="b" * 64)
    return SemanticInput(redacted.envelope, gate=gate, generation="b" * 64)


def payload():
    return {field: {"label": "not_stated", "confidence": 0.75} for field in c.FIELD_IDS}


def test_full37_closed_supported_schema_and_self_confidence_domain_mapping():
    """Catches a partial model schema or self confidence represented as native probability."""
    ctx = context()
    bundle = g.compile_request(ctx, model="synthetic-luna", max_output_tokens=4096)
    request = bundle.request
    assert set(request.output_schema["properties"]) == set(c.FIELD_IDS)
    check_schema(request.output_schema)
    data = payload()
    data.update(
        {
            "ai_engineering_role": {"label": "excluded", "confidence": 0.8},
            "skills.python": {"label": "requested", "confidence": 0.9},
            "seniority": {"label": "multiple_junior__senior", "confidence": 0.9},
            "salary": {"label": "candidate_0", "confidence": 0.6},
        }
    )
    result = g.decode_payload(ctx, bundle, data)
    assert result.ai_engineering_role.value is False and result.portfolio_requested.value is None
    assert result.work_mode.value == result.employment.value == "not_stated"
    assert (
        result.skills.python.value is True
        and result.skills.python.certainty.kind == "self_reported_confidence"
    )
    assert result.seniority.levels == ("junior", "senior")
    assert (
        result.salary.presence.value is True and result.salary.normalization_status == "abstained"
    )
    assert result.salary.period is None and result.salary.normalized is None


@pytest.mark.parametrize(
    "change",
    ["missing", "extra", "bool_confidence", "nan", "large", "extra_label", "invented_candidate"],
)
def test_invalid_output_has_all37_errors_no_defaults_or_source_echo(change):
    """Catches missing/default fields or malformed confidence/candidates accepted as predictions."""
    ctx = context()
    bundle = g.compile_request(ctx, model="synthetic-luna", max_output_tokens=4096)
    data = payload()
    if change == "missing":
        del data["skills.security"]
    elif change == "extra":
        data["PRIVATE_CANARY_833"] = {"label": "not_stated", "confidence": 1.0}
    elif change == "extra_label":
        data["salary"]["free_text"] = "PRIVATE_CANARY_833"
    elif change == "invented_candidate":
        data["salary"]["label"] = "candidate_99"
    else:
        data["skills.python"]["confidence"] = {
            "bool_confidence": True,
            "nan": float("nan"),
            "large": 1.1,
        }[change]
    result = g.decode_payload(ctx, bundle, data)
    assert all(
        j.process_status == "error" and j.error_code == "invalid_output" for j in result.judgments()
    )
    assert "PRIVATE_CANARY_833" not in result.model_dump_json()


def test_missing_salary_candidate_is_not_offered_or_fabricated_by_decoder():
    """Catches the bounded salary candidate grammar silently inventing a range."""
    ctx = context("An original ordinary role without a supplied salary range.")
    bundle = g.compile_request(ctx, model="synthetic-luna", max_output_tokens=4096)
    assert (
        "candidate_0"
        not in bundle.request.output_schema["properties"]["salary"]["properties"]["label"]["enum"]
    )
    data = payload()
    data["salary"]["label"] = "candidate_0"
    assert g.decode_payload(ctx, bundle, data).salary.presence.process_status == "error"
    data["salary"]["label"] = "none"
    result = g.decode_payload(ctx, bundle, data)
    assert (
        result.salary.presence.value is False
        and result.salary.normalization_status == "not_applicable"
    )


def test_salary_prompt_alternatives_agree_with_the_closed_schema():
    """Catches prompt-suggested unknown labels forcing needless invalid outputs and repairs."""
    ctx = context()
    request = g.compile_request(ctx, model="synthetic-luna", max_output_tokens=4096).request
    instruction = " ".join(
        part.text for message in request.messages[:1] for part in message.content
    )
    salary_options = request.output_schema["properties"]["salary"]["properties"]["label"]["enum"]
    assert "unknown" not in salary_options and "none/unknown" not in instruction
    assert all(
        label in salary_options and label in instruction
        for label in ("none", "not_stated", "conflicting", "uncertain")
    )


def test_request_no_tools_or_model_confidence_calibration_and_actual_source_binding():
    """Catches extra execution channels or mutated request/source bundles reused for decoding."""
    ctx = context()
    bundle = g.compile_request(ctx, model="synthetic-luna", max_output_tokens=4096)
    wire = bundle.request.model_dump(mode="json", by_alias=True)
    assert not {"tools", "api_key", "credentials", "image"} & set(wire)
    assert "untrusted-" in wire["messages"][1]["content"][0]["text"]
    assert "uncalibrated self-report" in wire["messages"][0]["content"][0]["text"]
    bundle._request.messages.clear()
    with pytest.raises(ValueError, match="bundle_changed"):
        bundle.check()


def test_config_schema_matches_actual_supported_prototype():
    """Catches emitted generation config drifting from the actual closed schema."""
    doc = json.loads((Path(__file__).parents[2] / "config/schema-generation.json").read_text())
    assert doc["schema"] == g.output_schema(context())
    assert doc["repair_runtime"] == "pending_owner_api"
