"""Generation mix: governed generation_mix view only.

Shares come exclusively from the named share measures. A share is never
computed here by filtering unified_fuel_category; the denominator
decisions live in the semantic layer.
"""

import requests
import streamlit as st

from app.governed import (
    BA_CODES,
    CUBE_SETUP_HINT,
    cached_views,
    run_governed_plan,
    short,
)
from nl.catalog import CAVEATS, DATA_WINDOW_END, SERIES_BREAK_DATE
from nl.schema import Filter, QueryPlan, TimeDimension

ROLLUP_SHARES = [
    "generation_mix.renewable_share",
    "generation_mix.fossil_share",
    "generation_mix.carbon_free_share",
]
FUEL_SHARES = [
    "generation_mix.coal_share",
    "generation_mix.gas_share",
    "generation_mix.oil_share",
    "generation_mix.nuclear_share",
    "generation_mix.hydro_share",
    "generation_mix.solar_share",
    "generation_mix.wind_share",
    "generation_mix.geothermal_share",
    "generation_mix.other_share",
    "generation_mix.unknown_share",
]

st.set_page_config(page_title="Generation mix", page_icon="⚡")
st.title("Generation mix")

try:
    views = cached_views()
except requests.exceptions.RequestException:
    st.error(CUBE_SETUP_HINT)
    st.stop()

col_ba, col_year = st.columns(2)
with col_ba:
    ba = st.selectbox("Balancing authority", BA_CODES)
with col_year:
    year = st.selectbox(
        "Year",
        list(range(2019, 2027)),
        index=2023 - 2019,
        format_func=lambda y: f"{y} (partial, through {DATA_WINDOW_END})" if y == 2026 else str(y),
    )

# The governed data window ends mid-2026; the validator rejects ranges past it.
range_end = DATA_WINDOW_END if year == 2026 else f"{year}-12-31"
date_range = [f"{year}-01-01", range_end]

plan = QueryPlan(
    view="generation_mix",
    measures=ROLLUP_SHARES + FUEL_SHARES,
    filters=[
        Filter(member="generation_mix.ba_code", operator="equals", values=[ba])
    ],
    time_dimension=TimeDimension(
        dimension="generation_mix.datetime_utc", date_range=date_range
    ),
)

try:
    rows = run_governed_plan(plan, views)
except requests.exceptions.RequestException:
    st.error(CUBE_SETUP_HINT)
    st.stop()

if not rows:
    st.info("No rows returned for this slice.")
    st.stop()

row = rows[0]


def as_percent(value) -> str:
    if value is None:
        return "null (fuel not reported by this BA)"
    return f"{float(value) * 100:.2f}%"


st.subheader(f"{ba}, {year}")

st.markdown("**Rollup shares** (renewable = wind/solar/hydro/geothermal; "
            "fossil = coal/gas/oil; carbon-free = renewable + nuclear)")
st.dataframe(
    [{"share": short(m), "value": as_percent(row.get(m))} for m in ROLLUP_SHARES],
    width="stretch",
    hide_index=True,
)

st.markdown("**Per-fuel shares**")
reported = {
    short(m).removesuffix("_share"): float(row[m])
    for m in FUEL_SHARES
    if row.get(m) is not None
}
st.bar_chart(reported, horizontal=True, x_label="share of generation")
st.dataframe(
    [{"fuel": short(m).removesuffix("_share"), "share": as_percent(row.get(m))}
     for m in FUEL_SHARES],
    width="stretch",
    hide_index=True,
)

if any(row.get(m) is None for m in FUEL_SHARES):
    st.caption(f"Note: {CAVEATS['mix_nulls']}")
if date_range[0] <= SERIES_BREAK_DATE <= date_range[1]:
    st.caption(f"Note: {CAVEATS['series_break']}")

with st.expander("Query plan (governed, validator-checked at load)"):
    st.json(plan.model_dump(exclude_none=True))
