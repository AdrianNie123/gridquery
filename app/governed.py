"""Shared helpers for the Streamlit pages.

Every pre-built view on these pages is a hardcoded governed QueryPlan,
passed through nl.validator.validate_plan at page load and executed via
nl.executor.execute_plan. No SQL, no DuckDB, no numbers from anywhere
but Cube result rows (integrity rule 1).
"""

import streamlit as st

from nl.catalog import fetch_meta, governed_views
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
