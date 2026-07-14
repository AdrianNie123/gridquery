"""Deterministic answer rendering.

Every number shown comes straight from Cube result rows; the LLM never
produces or restates a figure (integrity rule 1). Every answer displays
the governed metric and the parameters used (PRD section 9 auditability),
plus catalog caveats where the queried slice warrants them.
"""

from dataclasses import dataclass, field

from nl.catalog import CAVEATS, SERIES_BREAK_DATE
from nl.schema import QueryPlan

# Members rendered as percentages (ratios in the data model).
_PERCENT_HINTS = ("_share", "yoy_growth", "cagr")


@dataclass
class Answer:
    kind: str  # "answer" | "refusal" | "clarification"
    text: str
    metric: str | None = None
    plan: QueryPlan | None = None
    rows: list[dict] | None = None
    usage: dict = field(default_factory=dict)


def _is_percent(member: str) -> bool:
    return any(h in member for h in _PERCENT_HINTS)


def _format_value(member: str, value):
    if value is None:
        return "null"
    if _is_percent(member):
        return f"{float(value) * 100:.2f}%"
    if member.endswith("_mwh"):
        return f"{float(value):,.0f}"
    if member.endswith((".year", ".hours", ".imputed_hours")):
        return f"{int(float(value))}"
    if isinstance(value, str):
        return value
    return f"{value}"


def _short(member: str) -> str:
    return member.split(".", 1)[1] if "." in member else member


def _render_table(columns: list[str], rows: list[dict]) -> str:
    headers = [_short(c) for c in columns]
    cells = [[_format_value(c, row.get(c)) for c in columns] for row in rows]
    widths = [
        max(len(headers[i]), *(len(r[i]) for r in cells)) if cells else len(headers[i])
        for i in range(len(columns))
    ]
    lines = [
        "  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)),
        "  ".join("-" * w for w in widths),
    ]
    for r in cells:
        lines.append("  ".join(r[i].ljust(widths[i]) for i in range(len(columns))))
    return "\n".join(lines)


def _parameters_line(plan: QueryPlan) -> str:
    parts = []
    for f in plan.filters:
        vals = ",".join(f.values) if f.values else f.operator
        parts.append(f"{_short(f.member)} {f.operator} {vals}")
    td = plan.time_dimension
    if td is not None and td.date_range:
        parts.append(f"period {td.date_range[0]}..{td.date_range[1]}")
        if td.granularity:
            parts.append(f"by {td.granularity}")
    if plan.dimensions:
        parts.append("grouped by " + ", ".join(_short(d) for d in plan.dimensions))
    return "; ".join(parts) if parts else "no filters (all BAs, full window)"


def _caveats(plan: QueryPlan, rows: list[dict]) -> list[str]:
    notes = []
    td = plan.time_dimension
    spans_break = (
        td is not None
        and td.date_range is not None
        and td.date_range[0] <= SERIES_BREAK_DATE <= td.date_range[1]
    )
    if plan.view == "generation_mix" and (spans_break or td is None or td.date_range is None):
        notes.append(CAVEATS["series_break"])
    if plan.view == "demand" and not any(
        f.member.endswith(".is_imputed") for f in plan.filters
    ):
        notes.append(CAVEATS["imputation_mix"])
    if plan.view == "demand_growth":
        notes.append(CAVEATS["growth_complete_years"])
    has_nulls = any(v is None for row in rows for v in row.values())
    if plan.view == "generation_mix" and has_nulls:
        notes.append(CAVEATS["mix_nulls"])
    return notes


def render_answer(metric: str, plan: QueryPlan, rows: list[dict], usage: dict) -> Answer:
    columns = list(plan.dimensions)
    if plan.time_dimension is not None and plan.time_dimension.granularity:
        columns.append(plan.time_dimension.dimension)
    columns += plan.measures

    lines = [
        f"metric: {metric}  |  view: {plan.view}",
        f"parameters: {_parameters_line(plan)}",
        "",
    ]
    if rows:
        lines.append(_render_table(columns, rows))
    else:
        lines.append("(no rows returned for this slice)")
    caveats = _caveats(plan, rows)
    if caveats:
        lines.append("")
        lines.extend(f"note: {c}" for c in caveats)
    return Answer(
        kind="answer", text="\n".join(lines), metric=metric, plan=plan, rows=rows, usage=usage
    )


def render_refusal(reason: str, usage: dict | None = None) -> Answer:
    return Answer(
        kind="refusal",
        text=f"Not answerable through the governed metrics: {reason}",
        usage=usage or {},
    )


def render_clarification(question: str, usage: dict | None = None) -> Answer:
    return Answer(kind="clarification", text=f"Clarification needed: {question}", usage=usage or {})
