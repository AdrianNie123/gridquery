# Verifies the governed `demand` view against direct SQL over
# marts.fct_hourly_demand. Calendar-year slices are UTC; the Cube
# dateRange ["Y-01-01", "Y-12-31"] is inclusive of the whole end day,
# equivalent to datetime_utc >= Y-01-01 and < (Y+1)-01-01.

import math

from conftest import to_float

REL_TOL = 1e-9

DEMAND_SQL = """
    select
        sum(demand_mwh) as total_demand_mwh,
        max(demand_mwh) as peak_demand_mwh,
        avg(demand_mwh) as average_demand_mwh,
        count(*) as hours,
        count(case when is_imputed then 1 end) as imputed_hours
    from marts.fct_hourly_demand
    where ba_code = ?
      and datetime_utc >= cast(? as timestamp)
      and datetime_utc < cast(? as timestamp)
"""


def demand_year_query(ba_code, year, measures):
    return {
        "measures": measures,
        "filters": [
            {"member": "demand.ba_code", "operator": "equals", "values": [ba_code]}
        ],
        "timeDimensions": [
            {
                "dimension": "demand.datetime_utc",
                "dateRange": [f"{year}-01-01", f"{year}-12-31"],
            }
        ],
    }


def test_anchor_erco_2023_total_demand(cube_query):
    """Recorded verification anchor for total_demand_mwh: ERCO 2023."""
    rows = cube_query(demand_year_query("ERCO", 2023, ["demand.total_demand_mwh"]))
    assert len(rows) == 1
    actual = to_float(rows[0]["demand.total_demand_mwh"])
    assert actual is not None
    assert abs(actual - 446_793_938) <= 1.0


def test_anchor_ciso_2023_peak_demand(cube_query):
    """Recorded verification anchor for peak_demand_mwh: CISO 2023."""
    rows = cube_query(demand_year_query("CISO", 2023, ["demand.peak_demand_mwh"]))
    assert len(rows) == 1
    actual = to_float(rows[0]["demand.peak_demand_mwh"])
    assert actual is not None
    assert abs(actual - 44_007) <= 0.5


def test_demand_measures_vs_sql_erco_2023(cube_query, db):
    """All six demand view measures for ERCO 2023 vs direct DuckDB SQL."""
    measures = [
        "demand.total_demand_mwh",
        "demand.peak_demand_mwh",
        "demand.average_demand_mwh",
        "demand.hours",
        "demand.imputed_hours",
        "demand.imputed_demand_share",
    ]
    rows = cube_query(demand_year_query("ERCO", 2023, measures))
    assert len(rows) == 1
    row = rows[0]

    total, peak, average, hours, imputed_hours = db.execute(
        DEMAND_SQL, ["ERCO", "2023-01-01", "2024-01-01"]
    ).fetchone()
    assert hours > 0

    expected = {
        "demand.total_demand_mwh": total,
        "demand.peak_demand_mwh": peak,
        "demand.average_demand_mwh": average,
        "demand.hours": hours,
        "demand.imputed_hours": imputed_hours,
        "demand.imputed_demand_share": imputed_hours / hours,
    }
    for measure, want in expected.items():
        got = to_float(row[measure])
        assert got is not None, f"{measure} came back null"
        assert math.isclose(got, want, rel_tol=REL_TOL), (
            f"{measure}: cube={got} sql={want}"
        )
