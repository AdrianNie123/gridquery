"""Shared helpers for the Streamlit pages.

Every pre-built view on these pages is a hardcoded governed QueryPlan,
passed through nl.validator.validate_plan at page load and executed via
nl.executor.execute_plan. No SQL, no DuckDB, no numbers from anywhere
but Cube result rows (integrity rule 1).
"""

import streamlit as st

from nl.catalog import CAVEATS, SERIES_BREAK_DATE, fetch_meta, governed_views
from nl.executor import execute_plan
from nl.schema import QueryPlan
from nl.validator import validate_plan

BA_CODES = ["PJM", "ERCO", "CISO"]
COMPLETE_YEARS = [2020, 2021, 2022, 2023, 2024, 2025]
PARTIAL_YEAR = 2026

CUBE_SETUP_HINT = (
    "Could not reach the Cube semantic layer. Start it with `make cube-up` "
    "and reload this page."
)


@st.cache_data(ttl=3600, show_spinner="Fetching governed surface...")
def cached_views() -> dict:
    """One /v1/meta fetch per session, shared across pages."""
    return governed_views(fetch_meta())


def refresh_views() -> None:
    cached_views.clear()


def run_governed_plan(plan: QueryPlan, views: dict) -> list[dict]:
    """Validate then execute a pre-built plan.

    A validator violation here is a build error in this page, not a user
    error: fail loudly so it cannot ship (proves the pre-built views sit
    on the governed surface).
    """
    violations = validate_plan(plan, views)
    if violations:
        raise RuntimeError(
            "pre-built plan left the governed surface: " + "; ".join(violations)
        )
    return execute_plan(plan)


def short(member: str) -> str:
    """demand.ba_code -> ba_code, for display column names."""
    return member.split(".", 1)[1] if "." in member else member


# Members rendered as percentages, same rule as the shipped renderer
# (nl/answer.py): ratios in the data model, formatted for display only.
_PERCENT_HINTS = ("_share", "yoy_growth", "cagr")


def _display_value(member: str, value):
    if value is None:
        return None
    if any(h in member for h in _PERCENT_HINTS):
        return f"{float(value) * 100:.2f}%"
    if member.endswith("_mwh"):
        return f"{float(value):,.0f}"
    return value


def humanize_rows(rows: list[dict]) -> list[dict]:
    """Shorten column names and format ratio/MWh values for display.

    Formatting only: every value still comes straight from the Cube rows.
    Nulls stay null so absence-of-data remains visible.
    """
    return [{short(k): _display_value(k, v) for k, v in row.items()} for row in rows]


def parameters_line(plan: QueryPlan) -> str:
    """One-line description of a plan's parameters, for display next to
    the metric name (PRD section 9 auditability). Mirrors the shipped
    renderer's wording using only public QueryPlan fields; display
    formatting only, no values."""
    parts = []
    for f in plan.filters:
        vals = ",".join(f.values) if f.values else f.operator
        parts.append(f"{short(f.member)} {f.operator} {vals}")
    td = plan.time_dimension
    if td is not None and td.date_range:
        parts.append(f"period {td.date_range[0]}..{td.date_range[1]}")
        if td.granularity:
            parts.append(f"by {td.granularity}")
    if plan.dimensions:
        parts.append("grouped by " + ", ".join(short(d) for d in plan.dimensions))
    return "; ".join(parts) if parts else "no filters (all BAs, full window)"


def caveat_notes(plan: QueryPlan, rows: list[dict]) -> list[str]:
    """The standing catalog caveats a queried slice warrants. Same
    conditions as the shipped renderer, built on the public caveat text
    and series-break constants from nl.catalog."""
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
