"""Golden-set loading and structural validation.

The golden set (eval/golden_set.yaml) is hand-authored and contains no
numbers by design: expected numeric rows live in eval/golden_results.json,
written only by eval/pin.py executing the golden plans against the tested
Cube layer. This module validates the hand-authored file offline, before
any API spend: ids unique, kinds valid, every golden plan parses as
nl.schema.QueryPlan and passes the real validator against the governed
surface. A golden plan that is itself invalid is a build error.
"""

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from nl.schema import QueryPlan
from nl.validator import validate_plan

GOLDEN_SET_PATH = Path(__file__).resolve().parent / "golden_set.yaml"


class PeriodSpec(BaseModel):
    """The period the question asks about, in whichever shape the entry
    declares. Exactly one of the fields is set."""

    years: list[int] | None = None
    date_range: list[str] | None = None
    full_window: bool = False


class Checks(BaseModel):
    """Parameter-level expectations for a query entry.

    These express what the question pins down, independent of how the
    model chooses to encode it (year filter vs covering date range both
    satisfy the same period spec).
    """

    ba_filter: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    period: PeriodSpec | None = None
    ordered: bool = False
    metric_aliases: list[str] = Field(
        default_factory=list,
        description="Metric names accepted in addition to expected_metric",
    )


class GoldenEntry(BaseModel):
    id: str
    question: str
    kind: Literal["query", "refuse", "clarify"]
    expected_metric: str | None = None
    golden_plan: QueryPlan | None = None
    checks: Checks | None = None
    notes: str = ""


def load_golden_set(path: Path = GOLDEN_SET_PATH) -> list[GoldenEntry]:
    """Load and structurally validate the golden set. Raises on any defect."""
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path} must be a YAML list of entries")

    entries = [GoldenEntry.model_validate(item) for item in raw]

    ids = [e.id for e in entries]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"duplicate golden ids: {duplicates}")

    for entry in entries:
        if entry.kind == "query":
            missing = [
                name
                for name, value in (
                    ("expected_metric", entry.expected_metric),
                    ("golden_plan", entry.golden_plan),
                    ("checks", entry.checks),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"{entry.id}: query entry missing {missing}")
        else:
            if entry.golden_plan is not None or entry.checks is not None:
                raise ValueError(
                    f"{entry.id}: {entry.kind} entry must not carry a plan or checks"
                )
    return entries


def validate_golden_plans(entries: list[GoldenEntry], views: dict) -> list[str]:
    """Run every golden plan through the real validator. Returns violations
    as '<id>: <violation>' strings; empty means all plans are governed."""
    problems = []
    for entry in entries:
        if entry.golden_plan is None:
            continue
        for violation in validate_plan(entry.golden_plan, views):
            problems.append(f"{entry.id}: {violation}")
    return problems
