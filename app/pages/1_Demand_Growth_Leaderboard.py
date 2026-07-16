"""Demand growth leaderboard: governed demand_growth view only.

Two pre-built plans: year-over-year growth by BA for a selected year, and
window CAGR per BA. Both are validated against the governed surface at
page load and executed through the shipped executor.
"""

import requests
import streamlit as st

from app.governed import (
    COMPLETE_YEARS,
    CUBE_SETUP_HINT,
    PARTIAL_YEAR,
    cached_views,
    humanize_rows,
    run_governed_plan,
)
from nl.catalog import CAVEATS
from nl.schema import Filter, Order, QueryPlan

st.set_page_config(page_title="Demand growth leaderboard", page_icon="⚡")
st.title("Demand growth leaderboard")
st.caption(CAVEATS["growth_complete_years"])

try:
    views = cached_views()
except requests.exceptions.RequestException:
    st.error(CUBE_SETUP_HINT)
    st.stop()

year_options = COMPLETE_YEARS + [PARTIAL_YEAR]
year = st.selectbox(
    "Year (year-over-year growth vs the prior year)",
    year_options,
    index=len(COMPLETE_YEARS) - 1,
    format_func=lambda y: f"{y} (partial year)" if y == PARTIAL_YEAR else str(y),
)

yoy_plan = QueryPlan(
    view="demand_growth",
    measures=["demand_growth.demand_yoy_growth"],
    dimensions=["demand_growth.ba_code"],
    filters=[
        Filter(
            member="demand_growth.year",
            operator="equals",
            values=[str(year)],
        )
    ],
    order=[Order(member="demand_growth.demand_yoy_growth", direction="desc")],
)

cagr_plan = QueryPlan(
    view="demand_growth",
    measures=["demand_growth.demand_cagr"],
    dimensions=["demand_growth.ba_code"],
    order=[Order(member="demand_growth.demand_cagr", direction="desc")],
)

try:
    yoy_rows = run_governed_plan(yoy_plan, views)
    cagr_rows = run_governed_plan(cagr_plan, views)
except requests.exceptions.RequestException:
    st.error(CUBE_SETUP_HINT)
    st.stop()

st.subheader(f"Year-over-year demand growth, {year}")
st.dataframe(humanize_rows(yoy_rows), width="stretch")
if year == PARTIAL_YEAR:
    st.info(
        f"{PARTIAL_YEAR} is a partial year in the landed data, so "
        "year-over-year growth is null by design, not missing: growth is "
        "only defined over complete calendar years. The null is shown "
        "rather than hidden."
    )

st.subheader("Demand CAGR over the complete-year window")
st.caption(
    "Compound annual growth rate between the first and last complete "
    "calendar years in the data, per balancing authority. The metric "
    "definition itself excludes partial years."
)
st.dataframe(humanize_rows(cagr_rows), width="stretch")

with st.expander("Query plans (governed, validator-checked at load)"):
    st.json(yoy_plan.model_dump(exclude_none=True))
    st.json(cagr_plan.model_dump(exclude_none=True))
