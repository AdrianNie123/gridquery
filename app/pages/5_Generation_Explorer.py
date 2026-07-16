"""Generation explorer with time-granularity controls and unit totals.

This page focuses on governed generation totals in physical units (MWh/kWh)
with optional fuel-category breakdown.
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
GENERATION_TOTAL_MEASURES = [
    "generation_mix.generation_mwh",
    "generation_mix.denominator_generation_mwh",
    "generation_mix.renewable_generation_mwh",
    "generation_mix.fossil_generation_mwh",
    "generation_mix.carbon_free_generation_mwh",
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
    return [
        {short(k): _convert_unit(k, v, unit) for k, v in row.items()} for row in rows
    ]


st.set_page_config(page_title="Generation explorer", page_icon="⚡")
st.title("Generation explorer")
st.caption(
    "Explore governed generation totals with selectable time granularity. "
    "Use this page for physical unit totals rather than only mix percentages."
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

mode = st.radio(
    "View mode",
    ["Generation totals", "Generation by fuel category"],
    horizontal=True,
)
split_by_ba = st.checkbox("Split by balancing authority", value=True)

selected_measures = st.multiselect(
    "Generation metrics",
    GENERATION_TOTAL_MEASURES,
    default=["generation_mix.generation_mwh"],
    format_func=short,
    disabled=mode == "Generation by fuel category",
)

if not selected_bas:
    st.info("Select at least one balancing authority.")
    st.stop()
if mode == "Generation totals" and not selected_measures:
    st.info("Select at least one generation metric.")
    st.stop()
if start_date > end_date:
    st.error("Start date must be on or before end date.")
    st.stop()

filters = []
if set(selected_bas) != set(BA_CODES):
    filters.append(
        Filter(
            member="generation_mix.ba_code", operator="equals", values=selected_bas
        )
    )

dimensions = []
if split_by_ba:
    dimensions.append("generation_mix.ba_code")
if mode == "Generation by fuel category":
    dimensions.append("generation_mix.unified_fuel_category")
    measures = ["generation_mix.generation_mwh"]
else:
    measures = selected_measures

plan = QueryPlan(
    view="generation_mix",
    measures=measures,
    dimensions=dimensions,
    filters=filters,
    time_dimension=TimeDimension(
        dimension="generation_mix.datetime_utc",
        granularity=granularity,
        date_range=[_iso(start_date), _iso(end_date)],
    ),
    order=[Order(member="generation_mix.datetime_utc", direction="asc")],
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
