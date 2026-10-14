"""Conservative single disjoint-partition suppression, not an anonymity guarantee."""

import math
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MIN_COHORT = 10
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Month = Annotated[str, Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]
Count = Annotated[int, Field(ge=0, le=2**63 - 1)]
Share = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]
Metric = Literal[
    "ai_engineering_role",
    "portfolio_requested",
    "seniority",
    "work_mode",
    "employment",
    "skills.python",
    "skills.javascript",
    "skills.typescript",
    "skills.go",
    "skills.rust",
    "skills.java",
    "skills.c",
    "skills.cpp",
    "skills.sql",
    "skills.pytorch",
    "skills.tensorflow",
    "skills.jax",
    "skills.llm_apis",
    "skills.agents",
    "skills.rag",
    "skills.evals",
    "skills.fine_tuning",
    "skills.mcp",
    "skills.vector_db",
    "skills.prompt_engineering",
    "skills.mlops",
    "skills.data_pipelines",
    "skills.kubernetes",
    "skills.aws",
    "skills.gcp",
    "skills.react",
    "skills.node",
    "skills.postgres",
    "skills.distributed_systems",
    "skills.security",
    "salary",
    "location_stated",
]
ClassLabel = Literal[
    "positive",
    "negative",
    "not_stated",
    "conflicting",
    "uncertain",
    "error",
    "blocked",
    "junior",
    "mid",
    "senior",
    "staff_or_lead",
    "multiple",
    "remote",
    "hybrid",
    "onsite",
    "full_time",
    "part_time",
    "contract",
    "internship",
    "stated_normalized",
    "stated_unknown_units",
]
FAILURE_CLASSES = ("conflicting", "uncertain", "error", "blocked")
BOOLEAN_CLASSES = ("positive", "negative", "not_stated", *FAILURE_CLASSES)


def class_inventory(metric: str) -> tuple[str, ...]:
    special = {
        "seniority": ("junior", "mid", "senior", "staff_or_lead", "multiple", "not_stated"),
        "work_mode": ("remote", "hybrid", "onsite", "not_stated"),
        "employment": ("full_time", "part_time", "contract", "internship", "not_stated"),
        "salary": ("stated_normalized", "stated_unknown_units", "negative", "not_stated"),
    }
    return (*special[metric], *FAILURE_CLASSES) if metric in special else BOOLEAN_CLASSES


class Closed(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        hide_input_in_errors=True,
        revalidate_instances="always",
    )


class Interval(Closed):
    lower: Share
    upper: Share

    @model_validator(mode="after")
    def ordered(self) -> Self:
        if self.lower > self.upper:
            raise ValueError("interval ordering")
        return self


class Cell(Closed):
    label: ClassLabel
    numerator: Count
    uncertainty: Interval | None


class Partition(Closed):
    """Exactly one exhaustive ordered partition, without arbitrary marginal cuts."""

    month: Month
    metric: Metric
    method: Literal["rules", "jev", "generative", "dev_majority", "human"]
    version_sha256: Digest
    evidence_category: Literal["prediction", "synthetic_expectation", "human_self_attested"]
    coverage: Literal["complete", "partial", "failed"]
    denominator: Count
    cells: Annotated[tuple[Cell, ...], Field(min_length=2, max_length=10)]

    @model_validator(mode="after")
    def exhaustive(self) -> Self:
        if tuple(cell.label for cell in self.cells) != class_inventory(self.metric):
            raise ValueError("one exact exhaustive ordered class partition required")
        if sum(cell.numerator for cell in self.cells) != self.denominator:
            raise ValueError("partition counts must sum to denominator")
        return self


class ReleasedCell(Closed):
    label: ClassLabel
    numerator: Count | None
    share: Share | None
    uncertainty: Interval | None


class ReleasedPartition(Closed):
    month: Month
    metric: Metric
    method: Literal["rules", "jev", "generative", "dev_majority", "human"]
    version_sha256: Digest
    evidence_category: Literal["prediction", "synthetic_expectation", "human_self_attested"]
    coverage: Literal["complete", "partial", "failed"]
    policy: Literal["single-partition-all-siblings-min10-v1"]
    denominator: Count | None
    suppressed: bool
    trend_eligible: bool
    cells: Annotated[tuple[ReleasedCell, ...], Field(min_length=2, max_length=10)]

    @model_validator(mode="after")
    def release_invariants(self) -> Self:
        if tuple(cell.label for cell in self.cells) != class_inventory(self.metric):
            raise ValueError("released class inventory differs")
        if self.denominator is not None and self.denominator < MIN_COHORT:
            raise ValueError("small cohort denominator must be withheld")
        if self.suppressed:
            if any(
                cell.numerator is not None or cell.share is not None or cell.uncertainty is not None
                for cell in self.cells
            ):
                raise ValueError("suppressed partition must withhold every sibling and interval")
        else:
            if self.denominator is None or not self.denominator:
                raise ValueError("released partition needs a supported denominator")
            total = 0
            for cell in self.cells:
                if cell.numerator is None or cell.numerator < MIN_COHORT or cell.share is None:
                    raise ValueError("all released cells require support at least ten")
                if not math.isclose(
                    cell.share, cell.numerator / self.denominator, rel_tol=0, abs_tol=1e-12
                ):
                    raise ValueError("released share differs from numerator/denominator")
                total += cell.numerator
            if total != self.denominator:
                raise ValueError("released counts do not sum to denominator")
        if self.trend_eligible != (self.coverage == "complete" and not self.suppressed):
            raise ValueError("incomplete/suppressed partition cannot be a complete trend")
        return self


def release_partition(partition: Partition) -> ReleasedPartition:
    partition = Partition.model_validate(partition)
    suppressed = any(cell.numerator < MIN_COHORT for cell in partition.cells)
    cells = tuple(
        ReleasedCell(
            label=cell.label,
            numerator=None if suppressed else cell.numerator,
            share=None if suppressed else cell.numerator / partition.denominator,
            uncertainty=None if suppressed else cell.uncertainty,
        )
        for cell in partition.cells
    )
    return ReleasedPartition(
        month=partition.month,
        metric=partition.metric,
        method=partition.method,
        version_sha256=partition.version_sha256,
        evidence_category=partition.evidence_category,
        coverage=partition.coverage,
        policy="single-partition-all-siblings-min10-v1",
        denominator=partition.denominator if partition.denominator >= MIN_COHORT else None,
        suppressed=suppressed,
        trend_eligible=partition.coverage == "complete" and not suppressed,
        cells=cells,
    )


def format_projection(
    bundle: ReleasedPartition, format_name: Literal["json", "table", "chart", "html"]
) -> dict:
    """The same validated scalars for future renderers, not a chart/HTML pipeline."""
    if format_name not in {"json", "table", "chart", "html"}:
        raise ValueError("unsupported projection format")
    return ReleasedPartition.model_validate(bundle).model_dump(mode="json")


def schema_documents() -> dict[str, dict]:
    result = {}
    for name, model in (("partition", Partition), ("released-partition", ReleasedPartition)):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["x-runtime-validators-required"] = True
        result[name] = schema
    return result
