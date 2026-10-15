"""Closed all37-field generation request/decoder; no hidden repair or model calls."""

import json

from hiring_signals import contracts as c
from hiring_signals.extract.jev import RULE
from hiring_signals.extract.semantic import SemanticInput, assemble, failure
from hiring_signals.shared.callledger.models import canonical_digest
from hiring_signals.shared.providers.models import GenerateRequest, Result
from hiring_signals.shared.providers.schema import check_schema, validate_output


def output_schema(context: SemanticInput):
    context.check()
    fields = {}
    for field in c.FIELD_IDS:
        fields[field] = {
            "type": "object",
            "properties": {
                "label": {"type": "string", "enum": list(context.options(field))},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["label", "confidence"],
            "additionalProperties": False,
        }
    schema = {
        "type": "object",
        "properties": fields,
        "required": list(c.FIELD_IDS),
        "additionalProperties": False,
    }
    check_schema(schema)
    return schema


class GenerationBundle:
    __slots__ = ("_context", "_request", "_identity")

    def __init__(self, context, request):
        self._context, self._request = context, request
        self._identity = canonical_digest(request.identity_payload())

    def __repr__(self):
        return "GenerationBundle(<transient model input omitted>)"

    def __reduce_ex__(self, protocol):
        raise TypeError("transient_request_bundle_serialization_forbidden")

    def check(self):
        self._context.check()
        if canonical_digest(self._request.identity_payload()) != self._identity:
            raise ValueError("semantic_request_bundle_changed")

    @property
    def request(self):
        self.check()
        return GenerateRequest.model_validate_json(self._request.model_dump_json(by_alias=True))


def compile_request(
    context: SemanticInput, *, model: str, max_output_tokens: int
) -> GenerationBundle:
    schema = output_schema(context)
    request = GenerateRequest.model_validate(
        {
            "schema_version": 1,
            "kind": "generate",
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": RULE
                            + (
                                " Return every required field in the exact JSON schema. "
                                "Confidence is your uncalibrated self-report. "
                                "not_stated is absence, excluded is an explicit negative. "
                                "Do not infer employment/work mode. "
                                "Seniority multiple means genuine levels, "
                                "not contradictory evidence. Only choose supplied salary "
                                "candidates or none/unknown. Do not return quotes, locations, "
                                "identities, links or arbitrary explanatory text."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(context.state(), ensure_ascii=False, sort_keys=True),
                        }
                    ],
                },
            ],
            "schema": schema,
            "max_output_tokens": max_output_tokens,
            "stream": False,
        }
    )
    return GenerationBundle(context, request)


def decode_payload(context: SemanticInput, bundle: GenerationBundle, payload):
    context.check()
    bundle.check()
    if bundle._context is not context:
        raise ValueError("semantic_result_source_mismatch")
    try:
        validate_output(payload, bundle._request.output_schema)
        fields = {}
        for field in c.FIELD_IDS:
            entry = payload[field]
            certainty = c.Certainty(kind="self_reported_confidence", value=entry["confidence"])
            fields[field] = context.judgment(field, entry["label"], certainty=certainty)
        return assemble(fields)
    except (ValueError, TypeError, KeyError):
        return failure(code="invalid_output")


def decode(context: SemanticInput, bundle: GenerationBundle, result: Result | None):
    context.check()
    bundle.check()
    if result is None:
        return failure(code="provider_error")
    try:
        result = Result.model_validate_json(result.model_dump_json()).validate_for(bundle._request)
    except (ValueError, TypeError, AttributeError):
        return failure(code="invalid_output")
    if result.status != "ok":
        return failure(
            code="invalid_output" if result.status == "invalid_output" else "provider_error"
        )
    return decode_payload(context, bundle, result.parsed)
