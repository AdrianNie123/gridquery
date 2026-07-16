"""Demand explorer with time-granularity controls.

This page focuses on governed demand totals in physical units and lets the
user choose the time bucket (hour/day/week/month/quarter/year). Growth logic
remains on the annual-only demand growth page.
"""

from datetime import date

import requests
import streamlit as st

from app.governed import (
    BA_CODES,
    CUBE_SETUP_HINT,
    cached_views,
    run_governed_plan,
    short,
)
from nl.catalog import DATA_WINDOW_END
from nl.schema import Filter, Order, QueryPlan, TimeDimension

DATA_WINDOW_START = "2019-01-01"
DEMAND_MEASURES = [
    "demand.total_demand_mwh",
    "demand.peak_demand_mwh",
    "demand.average_demand_mwh",
]


def _iso(d: date) -> str:
    return d.isoformat()


def _convert_unit(member: str, value, unit: str):
    if value is None:
        return None
    if member.endswith("_mwh") and unit == "kWh":
        return float(value) * 1000.0
    return value


def _render_rows(rows: list[dict], unit: str) -> list[dict]:
    rendered = []
    for row in rows:
        rendered.append(
            {short(k): _convert_unit(k, v, unit) for k, v in row.items()}
        )
    return rendered


st.set_page_config(page_title="Demand explorer", page_icon="⚡")
st.title("Demand explorer")
st.caption(
    "Explore governed demand metrics with time buckets. "
    "For year-over-year growth and CAGR, use the annual demand growth page."
)

try:
    views = cached_views()
except requests.exceptions.RequestException:
    st.error(CUBE_SETUP_HINT)
    st.stop()

col_ba, col_grain, col_unit = st.columns(3)
with col_ba:
    selected_bas = st.multiselect(
        "Balancing authorities",
        BA_CODES,
        default=BA_CODES,
    )
with col_grain:
    granularity = st.selectbox(
        "Time granularity",
        ["hour", "day", "week", "month", "quarter", "year"],
        index=3,
    )
with col_unit:
    unit = st.selectbox("Display unit", ["MWh", "kWh"], index=0)

col_start, col_end = st.columns(2)
with col_start:
    start_date = st.date_input("Start date", value=date(2023, 1, 1))
with col_end:
    end_date = st.date_input("End date", value=date(2023, 12, 31))

selected_measures = st.multiselect(
    "Demand metrics",
    DEMAND_MEASURES,
    default=["demand.total_demand_mwh"],
    format_func=short,
)
split_by_ba = st.checkbox("Split by balancing authority", value=True)

if not selected_bas:
    st.info("Select at least one balancing authority.")
    st.stop()
if not selected_measures:
    st.info("Select at least one demand metric.")
    st.stop()
if start_date > end_date:
    st.error("Start date must be on or before end date.")
    st.stop()

filters = []
if set(selected_bas) != set(BA_CODES):
    filters.append(
        Filter(member="demand.ba_code", operator="equals", values=selected_bas)
    )

dimensions = ["demand.ba_code"] if split_by_ba else []
plan = QueryPlan(
    view="demand",
    measures=selected_measures,
    dimensions=dimensions,
    filters=filters,
    time_dimension=TimeDimension(
        dimension="demand.datetime_utc",
        granularity=granularity,
        date_range=[_iso(start_date), _iso(end_date)],
    ),
    order=[Order(member="demand.datetime_utc", direction="asc")],
)

try:
    rows = run_governed_plan(plan, views)
except requests.exceptions.RequestException:
    st.error(CUBE_SETUP_HINT)
    st.stop()

st.subheader("Results")
if not rows:
    st.info("No rows returned for this slice.")
else:
    st.dataframe(_render_rows(rows, unit), width="stretch")
    st.caption(
        "Metrics ending in `_mwh` come from governed Cube measures. "
        f"Current display unit: {unit}."
    )

with st.expander("Query plan (governed, validator-checked at load)"):
    st.json(plan.model_dump(exclude_none=True))
    st.caption(f"Governed data window: {DATA_WINDOW_START} through {DATA_WINDOW_END}.")
