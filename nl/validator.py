"""Deterministic validation of planner output against the governed surface.

This is the code-level enforcement of integrity rule 4: the LLM's plan is
checked member-by-member against /v1/meta before anything executes. An
invalid plan is converted to a refusal, never silently repaired. The LLM
is not trusted to stay on the governed surface; this module guarantees it.
"""

import re

from nl.catalog import ALLOWED_BA_CODES, DATA_WINDOW_END, DATA_WINDOW_START
from nl.schema import QueryPlan

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
YEAR_VALUE = re.compile(r"^\d{4}$")
MAX_LIMIT = 5000

WINDOW_START_YEAR = int(DATA_WINDOW_START[:4])
WINDOW_END_YEAR = int(DATA_WINDOW_END[:4])

# The lowest/highest year each operator may carry without requesting data
# outside the governed window, by the interval the operator implies
# (gt 2018 implies years >= 2019, so 2018 is the lowest valid gt value).
# notEquals excludes rather than requests, so it has no bound here.
_YEAR_LOWER_BOUND = {"equals": WINDOW_START_YEAR, "gte": WINDOW_START_YEAR, "gt": WINDOW_START_YEAR - 1}
_YEAR_UPPER_BOUND = {"equals": WINDOW_END_YEAR, "lte": WINDOW_END_YEAR, "lt": WINDOW_END_YEAR + 1}


def validate_plan(plan: QueryPlan, views: dict) -> list[str]:
    """Return a list of violations. An empty list means the plan is valid."""
    violations: list[str] = []

    view = views.get(plan.view)
    if view is None:
        return [f"view '{plan.view}' is not a governed view"]

    measures = view["measures"]
    dimensions = view["dimensions"]
    members = set(measures) | set(dimensions)

    def check_prefix(member: str) -> bool:
        return member.startswith(plan.view + ".")

    if not plan.measures:
        violations.append("plan has no measures")
    for m in plan.measures:
        if m not in measures:
            violations.append(f"measure '{m}' is not on the governed view '{plan.view}'")
        elif not check_prefix(m):
            violations.append(f"measure '{m}' does not belong to view '{plan.view}'")

    for d in plan.dimensions:
        if d not in dimensions:
            violations.append(f"dimension '{d}' is not on the governed view '{plan.view}'")

    for f in plan.filters:
        if f.member not in members:
            violations.append(f"filter member '{f.member}' is not on the governed view '{plan.view}'")
            continue
        if f.operator in ("set", "notSet"):
            if f.values:
                violations.append(f"filter on '{f.member}' with operator '{f.operator}' must not carry values")
            continue
        if not f.values:
            violations.append(f"filter on '{f.member}' with operator '{f.operator}' has no values")
        if f.member.endswith(".ba_code"):
            bad = [v for v in f.values if v not in ALLOWED_BA_CODES]
            if bad:
                violations.append(
                    f"ba_code values {bad} are outside the governed set {list(ALLOWED_BA_CODES)}"
                )
        if f.member.endswith(".year"):
            bad = [v for v in f.values if not YEAR_VALUE.match(v)]
            if bad:
                violations.append(f"year filter values {bad} are not plain years")
            else:
                lower = _YEAR_LOWER_BOUND.get(f.operator)
                upper = _YEAR_UPPER_BOUND.get(f.operator)
                out = [
                    v
                    for v in f.values
                    if (lower is not None and int(v) < lower)
                    or (upper is not None and int(v) > upper)
                ]
                if out:
                    violations.append(
                        f"year filter '{f.operator}' {out} requests data outside "
                        f"the governed window {WINDOW_START_YEAR}..{WINDOW_END_YEAR}"
                    )

    td = plan.time_dimension
    if td is not None:
        if dimensions.get(td.dimension) != "time":
            violations.append(
                f"'{td.dimension}' is not a time dimension on the governed view '{plan.view}'"
            )
        if td.date_range is not None:
            if len(td.date_range) != 2:
                violations.append("date_range must be [start, end]")
            else:
                start, end = td.date_range
                if not (ISO_DATE.match(start) and ISO_DATE.match(end)):
                    violations.append(f"date_range {td.date_range} is not ISO YYYY-MM-DD")
                elif start > end:
                    violations.append(f"date_range start {start} is after end {end}")
                elif start < DATA_WINDOW_START or end > DATA_WINDOW_END:
                    violations.append(
                        f"date_range {td.date_range} is outside the governed data "
                        f"window {DATA_WINDOW_START}..{DATA_WINDOW_END}"
                    )

    selected = set(plan.measures) | set(plan.dimensions)
    if td is not None:
        selected.add(td.dimension)
    for o in plan.order:
        if o.member not in selected:
            violations.append(f"order member '{o.member}' is not selected in the plan")

    if plan.limit is not None and not (1 <= plan.limit <= MAX_LIMIT):
        violations.append(f"limit {plan.limit} outside 1..{MAX_LIMIT}")

    return violations
