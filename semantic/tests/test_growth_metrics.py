# Verifies the governed `demand_growth` view (annual grain, UTC calendar
# years) against direct SQL over marts.fct_hourly_demand. Includes the
# partial-year guard: 2026 data ends 2026-05-03, so growth metrics for
# 2026 selections must be null while the annual total still returns.

import math

import pytest

from conftest import to_float

REL_TOL = 1e-9

ANNUAL_TOTAL_SQL = """
    select sum(demand_mwh)
    from marts.fct_hourly_demand
    where ba_code = ?
      and datetime_utc >= cast(? as timestamp)
      and datetime_utc < cast(? as timestamp)
"""


def annual_total(db, ba_code, year):
    value = db.execute(
        ANNUAL_TOTAL_SQL, [ba_code, f"{year}-01-01", f"{year + 1}-01-01"]
    ).fetchone()[0]
    assert value is not None, f"no demand data for {ba_code} {year}"
    return value


def growth_query(ba_code, measures, year_filters):
    filters = [
        {"member": "demand_growth.ba_code", "operator": "equals", "values": [ba_code]}
    ] + year_filters
    return {"measures": measures, "filters": filters}


@pytest.mark.parametrize(
    "ba_code, year",
    [("ERCO", 2023), ("PJM", 2021)],
)
def test_demand_yoy_growth_vs_sql(cube_query, db, ba_code, year):
    """demand_yoy_growth vs SQL ratio of calendar-year demand sums."""
    rows = cube_query(
        growth_query(
            ba_code,
            ["demand_growth.demand_yoy_growth"],
            [
                {
                    "member": "demand_growth.year",
                    "operator": "equals",
                    "values": [str(year)],
                }
            ],
        )
    )
    assert len(rows) == 1
    got = to_float(rows[0]["demand_growth.demand_yoy_growth"])
    assert got is not None, f"yoy growth null for {ba_code} {year}"

    want = annual_total(db, ba_code, year) / annual_total(db, ba_code, year - 1) - 1
    assert math.isclose(got, want, rel_tol=REL_TOL), (
        f"yoy {ba_code} {year}: cube={got} sql={want}"
    )


@pytest.mark.parametrize("ba_code", ["PJM", "ERCO", "CISO"])
def test_demand_cagr_2019_2023_vs_sql(cube_query, db, ba_code):
    """demand_cagr over 2019-2023 vs SQL pow(y2023/y2019, 1/4) - 1."""
    rows = cube_query(
        growth_query(
            ba_code,
            ["demand_growth.demand_cagr"],
            [
                {"member": "demand_growth.year", "operator": "gte", "values": ["2019"]},
                {"member": "demand_growth.year", "operator": "lte", "values": ["2023"]},
            ],
        )
    )
    assert len(rows) == 1
    got = to_float(rows[0]["demand_growth.demand_cagr"])
    assert got is not None, f"cagr null for {ba_code} 2019-2023"

    want = (annual_total(db, ba_code, 2023) / annual_total(db, ba_code, 2019)) ** (
        1 / 4
    ) - 1
    assert math.isclose(got, want, rel_tol=REL_TOL), (
        f"cagr {ba_code}: cube={got} sql={want}"
    )


def test_partial_year_guard_2026(cube_query, db):
    """Growth metrics are null for the partial year 2026; the annual total is not."""
    rows = cube_query(
        growth_query(
            "ERCO",
            [
                "demand_growth.annual_total_demand_mwh",
                "demand_growth.demand_yoy_growth",
                "demand_growth.demand_cagr",
            ],
            [
                {"member": "demand_growth.year", "operator": "equals", "values": ["2026"]}
            ],
        )
    )
    assert len(rows) == 1
    row = rows[0]

    assert row["demand_growth.demand_yoy_growth"] is None, (
        "yoy growth must be null for partial year 2026"
    )
    assert row["demand_growth.demand_cagr"] is None, (
        "cagr must be null for a selection with fewer than two complete years"
    )

    got_total = to_float(row["demand_growth.annual_total_demand_mwh"])
    assert got_total is not None, "annual total must still return for a partial year"
    want_total = annual_total(db, "ERCO", 2026)
    assert math.isclose(got_total, want_total, rel_tol=REL_TOL), (
        f"annual total 2026: cube={got_total} sql={want_total}"
    )
