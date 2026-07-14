# Offline edge tests for plan-to-Cube-query translation, deterministic
# answer rendering (value formatting and caveat boundaries), and
# system-prompt stability under meta reordering. Complements
# test_executor_answer.py and test_catalog.py. No Cube, no API key.

import copy
import datetime
import random
import re

import pytest

from nl.answer import _format_value, render_answer
from nl.catalog import (
    GROUNDING_RULES,
    METRIC_CATALOG_PATH,
    build_system_prompt,
    governed_views,
)
from nl.executor import to_cube_query
from nl.schema import Filter, Order, QueryPlan, TimeDimension

# --- 5. to_cube_query translation edges (pure function) ---


def test_minimal_plan_emits_only_measures():
    p = QueryPlan(view="demand", measures=["demand.total_demand_mwh"])
    q = to_cube_query(p)
    assert q == {"measures": ["demand.total_demand_mwh"]}
    for absent in ("dimensions", "filters", "timeDimensions", "order", "limit"):
        assert absent not in q


def test_granularity_included_only_when_set():
    base = dict(view="demand", measures=["demand.total_demand_mwh"])
    without = QueryPlan(
        **base,
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc", date_range=["2023-01-01", "2023-12-31"]
        ),
    )
    td = to_cube_query(without)["timeDimensions"][0]
    assert "granularity" not in td
    with_gran = QueryPlan(
        **base,
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc",
            granularity="month",
            date_range=["2023-01-01", "2023-12-31"],
        ),
    )
    td = to_cube_query(with_gran)["timeDimensions"][0]
    assert td["granularity"] == "month"


def test_date_range_omitted_when_none():
    p = QueryPlan(
        view="demand",
        measures=["demand.total_demand_mwh"],
        time_dimension=TimeDimension(dimension="demand.datetime_utc", granularity="year"),
    )
    td = to_cube_query(p)["timeDimensions"][0]
    assert td == {"dimension": "demand.datetime_utc", "granularity": "year"}
    assert "dateRange" not in td


def test_multiple_filters_preserved_in_order():
    p = QueryPlan(
        view="demand_growth",
        measures=["demand_growth.demand_cagr"],
        filters=[
            Filter(member="demand_growth.year", operator="gte", values=["2019"]),
            Filter(member="demand_growth.year", operator="lte", values=["2023"]),
            Filter(member="demand_growth.ba_code", operator="equals", values=["PJM"]),
        ],
    )
    q = to_cube_query(p)
    assert [f["member"] for f in q["filters"]] == [
        "demand_growth.year",
        "demand_growth.year",
        "demand_growth.ba_code",
    ]
    assert [f["operator"] for f in q["filters"]] == ["gte", "lte", "equals"]


def test_multiple_order_entries_preserved():
    p = QueryPlan(
        view="demand",
        measures=["demand.total_demand_mwh"],
        dimensions=["demand.ba_code"],
        order=[
            Order(member="demand.total_demand_mwh", direction="desc"),
            Order(member="demand.ba_code", direction="asc"),
        ],
    )
    q = to_cube_query(p)
    assert list(q["order"].items()) == [
        ("demand.total_demand_mwh", "desc"),
        ("demand.ba_code", "asc"),
    ]


# --- 6. answer-rendering edges (pure functions in nl/answer.py) ---


def mix_plan(date_range):
    return QueryPlan(
        view="generation_mix",
        measures=["generation_mix.renewable_share"],
        dimensions=["generation_mix.ba_code"],
        time_dimension=(
            TimeDimension(dimension="generation_mix.datetime_utc", date_range=date_range)
            if date_range is not None
            else None
        ),
    )


MIX_ROWS = [
    {"generation_mix.ba_code": "CISO", "generation_mix.renewable_share": "0.42"}
]


def test_zero_rows_message():
    ans = render_answer("renewable_share", mix_plan(["2023-01-01", "2023-12-31"]), [], usage={})
    assert "(no rows returned for this slice)" in ans.text
    # Fully pre-break window, no rows, no nulls: no caveats at all.
    assert "note:" not in ans.text


def test_mix_window_entirely_before_break_has_no_series_break_note():
    ans = render_answer(
        "renewable_share", mix_plan(["2023-01-01", "2023-12-31"]), MIX_ROWS, usage={}
    )
    assert "recategorization" not in ans.text


def test_mix_window_entirely_after_break_has_no_series_break_note():
    ans = render_answer(
        "renewable_share", mix_plan(["2024-08-01", "2024-12-31"]), MIX_ROWS, usage={}
    )
    assert "recategorization" not in ans.text


def test_mix_window_spanning_break_has_series_break_note():
    ans = render_answer(
        "renewable_share", mix_plan(["2024-01-01", "2024-12-31"]), MIX_ROWS, usage={}
    )
    assert "recategorization" in ans.text


def test_mix_without_date_range_has_series_break_note():
    # No time dimension at all: window is the full data range, spans the break.
    ans = render_answer("renewable_share", mix_plan(None), MIX_ROWS, usage={})
    assert "recategorization" in ans.text
    # Time dimension present but no date_range: same conclusion.
    p = QueryPlan(
        view="generation_mix",
        measures=["generation_mix.renewable_share"],
        dimensions=["generation_mix.ba_code"],
        time_dimension=TimeDimension(
            dimension="generation_mix.datetime_utc", granularity="year"
        ),
    )
    ans = render_answer("renewable_share", p, MIX_ROWS, usage={})
    assert "recategorization" in ans.text


def test_demand_with_is_imputed_filter_has_no_imputation_note():
    p = QueryPlan(
        view="demand",
        measures=["demand.total_demand_mwh"],
        dimensions=["demand.ba_code"],
        filters=[Filter(member="demand.is_imputed", operator="equals", values=["false"])],
    )
    rows = [{"demand.ba_code": "PJM", "demand.total_demand_mwh": "1000"}]
    ans = render_answer("total_demand", p, rows, usage={})
    assert "imputed_demand_share metric" not in ans.text


@pytest.mark.parametrize(
    "member,value,expected",
    [
        # mwh values: thousands separators, rounded to integers
        ("demand.total_demand_mwh", "812345678.9", "812,345,679"),
        ("demand_growth.annual_total_demand_mwh", 1234567.4, "1,234,567"),
        # percent members: ratio x100, two decimals
        ("generation_mix.renewable_share", "0.4567", "45.67%"),
        ("demand.imputed_demand_share", "0.005", "0.50%"),
        ("demand_growth.demand_yoy_growth", "0.021", "2.10%"),
        ("demand_growth.demand_cagr", 0.0312, "3.12%"),
        # year and hour counts: plain ints
        ("demand_growth.year", "2023", "2023"),
        ("demand.hours", "8760.0", "8760"),
        ("demand.imputed_hours", 12, "12"),
        # None renders as null everywhere
        ("demand.total_demand_mwh", None, "null"),
        ("generation_mix.oil_share", None, "null"),
        # string dimensions pass through untouched
        ("demand.ba_code", "PJM", "PJM"),
        ("generation_mix.unified_fuel_category", "solar", "solar"),
    ],
)
def test_format_value(member, value, expected):
    assert _format_value(member, value) == expected


# --- 7. prompt-stability regression ---


def test_prompt_dates_all_come_from_static_sources(views):
    # The prompt is a cached prefix; anything derived from "today" would
    # silently break caching. Every date-shaped string in the prompt must
    # already exist in the static sources (grounding rules, the fixed data
    # window, the checked-in metric catalog). A generated current date is
    # not in those sources, so it fails here whenever the test runs.
    date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
    static = (
        GROUNDING_RULES
        + METRIC_CATALOG_PATH.read_text()
        + " 2019-01-01 2026-05-03"  # the data-window line in the prompt
    )
    allowed = set(date_re.findall(static))
    prompt_dates = set(date_re.findall(build_system_prompt(views)))
    assert prompt_dates <= allowed, f"unexpected dates: {prompt_dates - allowed}"
    # Belt and braces: today's date must not appear unless it happens to be
    # one of the fixed static dates.
    today = datetime.date.today().isoformat()
    if today not in allowed:
        assert today not in build_system_prompt(views)


def test_prompt_insensitive_to_meta_ordering(meta, views):
    baseline = build_system_prompt(views)
    shuffled = copy.deepcopy(meta)
    random.Random(93).shuffle(shuffled["cubes"])
    for cube in shuffled["cubes"]:
        cube.get("measures", []).reverse()
        cube.get("dimensions", []).reverse()
    assert build_system_prompt(governed_views(shuffled)) == baseline
