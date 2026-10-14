"""Original bounded aliases and explicit local request/exclusion grammar.

This is deterministic syntax coverage, not calibrated semantic extraction. No
match substring or source quotation is returned; only closed IDs/byte offsets.
"""

import hashlib
import json
import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

SkillID = Literal[
    "python",
    "javascript",
    "typescript",
    "go",
    "rust",
    "java",
    "c",
    "cpp",
    "sql",
    "pytorch",
    "tensorflow",
    "jax",
    "llm_apis",
    "agents",
    "rag",
    "evals",
    "fine_tuning",
    "mcp",
    "vector_db",
    "prompt_engineering",
    "mlops",
    "data_pipelines",
    "kubernetes",
    "aws",
    "gcp",
    "react",
    "node",
    "postgres",
    "distributed_systems",
    "security",
]
MAX_BYTES = 32768
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
        revalidate_instances="always",
    )


class Alias(Closed):
    phrase: Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9 +#._-]{0,47}$")]
    case_sensitive: bool
    guard: Literal["none", "go", "c"]


class Entry(Closed):
    skill_id: SkillID
    aliases: Annotated[tuple[Alias, ...], Field(min_length=1, max_length=8)]


class Match(Closed):
    alias_index: Annotated[int, Field(ge=0, le=7)]
    start_byte: Annotated[int, Field(ge=0, lt=MAX_BYTES)]
    end_byte: Annotated[int, Field(gt=0, le=MAX_BYTES)]
    polarity: Literal["requested", "excluded", "uncertain"]

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if self.end_byte <= self.start_byte:
            raise ValueError("match span ordering")
        return self


class SkillSignal(Closed):
    input_sha256: Digest
    skill_id: SkillID
    status: Literal["requested", "excluded", "not_stated", "conflicting", "uncertain"]
    matches: Annotated[tuple[Match, ...], Field(max_length=8)]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        polarities = {match.polarity for match in self.matches}
        expected = _status(polarities)
        if self.status != expected:
            raise ValueError("skill signal/evidence mismatch")
        entry = next(entry for entry in CATALOG if entry.skill_id == self.skill_id)
        if any(match.alias_index >= len(entry.aliases) for match in self.matches):
            raise ValueError("unknown alias reference")
        return self


def _alias(phrase, sensitive=False, guard="none"):
    return Alias(phrase=phrase, case_sensitive=sensitive, guard=guard)


_DEFINITIONS = (
    ("python", (_alias("Python"),)),
    ("javascript", (_alias("JavaScript"), _alias("JS", True))),
    ("typescript", (_alias("TypeScript"), _alias("TS", True))),
    ("go", (_alias("Go", True, "go"), _alias("Golang"))),
    ("rust", (_alias("Rust"),)),
    ("java", (_alias("Java"),)),
    ("c", (_alias("C", True, "c"),)),
    ("cpp", (_alias("C++", True),)),
    ("sql", (_alias("SQL"),)),
    ("pytorch", (_alias("PyTorch"),)),
    ("tensorflow", (_alias("TensorFlow"),)),
    ("jax", (_alias("JAX", True),)),
    ("llm_apis", (_alias("LLM APIs"), _alias("OpenAI API"))),
    ("agents", (_alias("AI agents"), _alias("LLM agents"), _alias("agentic systems"))),
    ("rag", (_alias("RAG", True), _alias("retrieval augmented generation"))),
    ("evals", (_alias("evals"), _alias("LLM evaluation"), _alias("model evaluation"))),
    ("fine_tuning", (_alias("fine-tuning"), _alias("fine tuning"))),
    ("mcp", (_alias("MCP", True), _alias("Model Context Protocol"))),
    ("vector_db", (_alias("vector databases"), _alias("vector database"))),
    ("prompt_engineering", (_alias("prompt engineering"),)),
    ("mlops", (_alias("MLOps"),)),
    ("data_pipelines", (_alias("data pipelines"),)),
    ("kubernetes", (_alias("Kubernetes"), _alias("K8s"))),
    ("aws", (_alias("AWS", True), _alias("Amazon Web Services"))),
    ("gcp", (_alias("GCP", True), _alias("Google Cloud Platform"))),
    ("react", (_alias("React"), _alias("React.js"))),
    ("node", (_alias("Node.js"), _alias("NodeJS"))),
    ("postgres", (_alias("PostgreSQL"), _alias("Postgres"))),
    ("distributed_systems", (_alias("distributed systems"),)),
    ("security", (_alias("security"),)),
)
CATALOG = tuple(Entry(skill_id=skill, aliases=aliases) for skill, aliases in _DEFINITIONS)


def catalog_sha256() -> str:
    data = [entry.model_dump(mode="json") for entry in CATALOG]
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _status(polarities: set[str]) -> str:
    if {"requested", "excluded"} <= polarities:
        return "conflicting"
    if "uncertain" in polarities:
        return "uncertain"
    if "requested" in polarities:
        return "requested"
    if "excluded" in polarities:
        return "excluded"
    return "not_stated"


def _polarity(text: str, start: int, end: int) -> str | None:
    # Clause-local negation, including comma-separated requirements; do not let
    # "No Python, Go required" negate Go or let one sentence negate the next.
    clause_start = max((text.rfind(mark, 0, start) for mark in ".;\n,"), default=-1) + 1
    clause_end = min(
        (position for mark in ".;\n," if (position := text.find(mark, end)) >= 0), default=len(text)
    )
    before, after = text[clause_start:start], text[end:clause_end]
    if re.search(
        r"\b(?:no(?: experience with)?|without|exclude(?:d)?|do not require)\s*$", before, re.I
    ):
        return "excluded"
    if re.match(r"\s+(?:is\s+)?(?:not required|not needed|excluded)\b", after, re.I):
        return "excluded"
    if re.search(r"\b(?:maybe|optional|might use)\s*$", before, re.I) or re.match(
        r"\s+(?:is\s+)?optional\b", after, re.I
    ):
        return "uncertain"
    if re.search(r"\b(?:no|without)\b[^.;\n,]{1,60}\b(?:and|or)\s*$", before, re.I):
        return "uncertain"
    # A line heading applies across comma-separated terms. Other positive cues
    # stay local, avoiding incidental mentions outside a declared request/stack.
    line_start = text.rfind("\n", 0, start) + 1
    heading = re.match(
        r"\s*(?:skills|requirements|tech stack|stack)\s*:", text[line_start:start], re.I
    )
    if (
        heading
        or re.search(
            r"\b(?:requires?|must know|experience with|proficiency in|we use|preferred)"
            r"\s+(?:[\w+.-]+\s+(?:and|or)\s+)*$",
            before,
            re.I,
        )
        or re.match(r"\s+(?:is\s+)?(?:required|preferred)\b", after, re.I)
    ):
        return "requested"
    return None


def scan(text: str) -> tuple[SkillSignal, ...]:
    if not isinstance(text, str):
        raise ValueError("dictionary input must be text")
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        raise ValueError("dictionary input must be valid UTF-8") from None
    if size > MAX_BYTES:
        raise ValueError("dictionary input byte limit")
    offsets, total = [0], 0
    for character in text:
        total += len(character.encode("utf-8"))
        offsets.append(total)
    signals = []
    input_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    for entry in CATALOG:
        matches = []
        seen = set()
        for index, alias in enumerate(entry.aliases):
            expression = re.compile(
                r"(?<!\w)" + re.escape(alias.phrase) + r"(?!\w)",
                0 if alias.case_sensitive else re.I,
            )
            for found in expression.finditer(text):
                start, end = found.span()
                before, after = text[max(0, start - 20) : start], text[end : end + 20]
                if alias.guard == "go" and re.match(r"(?:[- ]to[- ]market|\s+to\b)", after, re.I):
                    continue
                if alias.guard == "c" and (
                    re.match(r"(?:\+|#|[- ](?:level|suite)\b)", after, re.I)
                    or re.search(r"\b(?:series|vitamin|grade)\s*$", before, re.I)
                ):
                    continue
                polarity = _polarity(text, start, end)
                if polarity is None or (start, end) in seen:
                    continue
                seen.add((start, end))
                matches.append(
                    Match(
                        alias_index=index,
                        start_byte=offsets[start],
                        end_byte=offsets[end],
                        polarity=polarity,
                    )
                )
        polarities = {match.polarity for match in matches}
        # Keep at least one of each observed polarity when bounding references.
        selected = []
        for polarity in ("requested", "excluded", "uncertain"):
            candidate = next((match for match in matches if match.polarity == polarity), None)
            if candidate is not None:
                selected.append(candidate)
        for match in matches:
            if match not in selected and len(selected) < 8:
                selected.append(match)
        selected.sort(key=lambda match: (match.start_byte, match.end_byte))
        signals.append(
            SkillSignal(
                input_sha256=input_sha256,
                skill_id=entry.skill_id,
                status=_status(polarities),
                matches=tuple(selected),
            )
        )
    return tuple(signals)


def schema_documents() -> dict[str, dict]:
    result = {}
    for name, model in (("entry", Entry), ("skill-signal", SkillSignal)):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["x-runtime-validators-required"] = True
        result[name] = schema
    return result
