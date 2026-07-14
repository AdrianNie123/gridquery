"""Structured outcome schema for the NL planner.

The LLM must return exactly one of three outcomes: a query plan against a
governed view, a refusal, or a clarification request. The schema is the
contract between the planner (Phase 4), the eval harness (Phase 5), and
the front end (Phase 6). Members are always fully qualified
("view.member"), matching Cube's REST API format.
"""

from typing import Literal, Union

from pydantic import BaseModel, Field

GOVERNED_VIEWS = ("demand", "demand_growth", "generation_mix")

FilterOperator = Literal[
    "equals",
    "notEquals",
    "gt",
    "gte",
    "lt",
    "lte",
    "set",
    "notSet",
]

Granularity = Literal["hour", "day", "week", "month", "quarter", "year"]


class Filter(BaseModel):
    member: str = Field(description="Fully qualified member, e.g. demand.ba_code")
    operator: FilterOperator
    values: list[str] = Field(
        default_factory=list,
        description="Filter values as strings. Empty for set/notSet.",
    )


class TimeDimension(BaseModel):
    dimension: str = Field(description="Fully qualified time dimension, e.g. demand.datetime_utc")
    granularity: Granularity | None = Field(
        default=None,
        description="Grouping granularity. Omit to aggregate over the whole range.",
    )
    date_range: list[str] | None = Field(
        default=None,
        description='Inclusive [start, end] as ISO dates, e.g. ["2023-01-01", "2023-12-31"]',
    )


class Order(BaseModel):
    member: str
    direction: Literal["asc", "desc"]


class QueryPlan(BaseModel):
    view: Literal["demand", "demand_growth", "generation_mix"]
    measures: list[str] = Field(description="Fully qualified measures from the view")
    dimensions: list[str] = Field(default_factory=list)
    filters: list[Filter] = Field(default_factory=list)
    time_dimension: TimeDimension | None = None
    order: list[Order] = Field(default_factory=list)
    limit: int | None = Field(default=None, description="Row cap; omit for default")


class QueryOutcome(BaseModel):
    action: Literal["query"]
    metric: str = Field(
        description="The named governed metric from the catalog this plan answers with"
    )
    plan: QueryPlan


class RefuseOutcome(BaseModel):
    action: Literal["refuse"]
    reason: str = Field(description="Why the question maps to no governed metric")


class ClarifyOutcome(BaseModel):
    action: Literal["clarify"]
    question: str = Field(description="The single clarifying question to ask the user")


class PlannerResponse(BaseModel):
    outcome: Union[QueryOutcome, RefuseOutcome, ClarifyOutcome] = Field(
        discriminator="action"
    )
