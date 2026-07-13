# Verifies the governed `generation_mix` view against direct SQL over
# marts.fct_hourly_generation. Share metrics divide by the mix denominator
# (in_mix_denominator, which excludes storage categories). A null share
# means the fuel is absent from that BA's reporting, not zero.

import math

import pytest

from conftest import to_float

REL_TOL = 1e-9

YEAR_2023 = ["2023-01-01", "2023-12-31"]

PER_FUEL_SHARE_MEASURES = [
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


def gen_query(ba_code, measures, date_range, dimensions=None):
    query = {
        "measures": measures,
        "filters": [
            {
                "member": "generation_mix.ba_code",
                "operator": "equals",
                "values": [ba_code],
            }
        ],
        "timeDimensions": [
            {"dimension": "generation_mix.datetime_utc", "dateRange": date_range}
        ],
    }
    if dimensions:
        query["dimensions"] = dimensions
    return query


def sql_sum_2023(db, ba_code, extra_where=""):
    value = db.execute(
        f"""
        select sum(net_generation_mwh)
        from marts.fct_hourly_generation
        where ba_code = ?
          and datetime_utc >= timestamp '2023-01-01'
          and datetime_utc < timestamp '2024-01-01'
          {extra_where}
        """,
        [ba_code],
    ).fetchone()[0]
    return value


def test_generation_by_fuel_erco_2023_vs_sql(cube_query, db):
    """generation_mwh grouped by unified_fuel_category, ERCO 2023, vs SQL."""
    rows = cube_query(
        gen_query(
            "ERCO",
            ["generation_mix.generation_mwh"],
            YEAR_2023,
            dimensions=["generation_mix.unified_fuel_category"],
        )
    )
    cube_by_fuel = {
        row["generation_mix.unified_fuel_category"]: to_float(
            row["generation_mix.generation_mwh"]
        )
        for row in rows
    }

    sql_by_fuel = dict(
        db.execute(
            """
            select unified_fuel_category, sum(net_generation_mwh)
            from marts.fct_hourly_generation
            where ba_code = 'ERCO'
              and datetime_utc >= timestamp '2023-01-01'
              and datetime_utc < timestamp '2024-01-01'
            group by 1
            """
        ).fetchall()
    )

    assert set(cube_by_fuel) == set(sql_by_fuel), (
        f"fuel category sets differ: cube={sorted(cube_by_fuel)} sql={sorted(sql_by_fuel)}"
    )
    for fuel, want in sql_by_fuel.items():
        got = cube_by_fuel[fuel]
        assert math.isclose(got, want, rel_tol=REL_TOL), (
            f"generation_mwh {fuel}: cube={got} sql={want}"
        )


@pytest.mark.parametrize("ba_code", ["PJM", "ERCO", "CISO"])
def test_bucket_shares_2023_vs_sql(cube_query, db, ba_code):
    """renewable_share, fossil_share, carbon_free_share for each BA, 2023, vs SQL."""
    rows = cube_query(
        gen_query(
            ba_code,
            [
                "generation_mix.renewable_share",
                "generation_mix.fossil_share",
                "generation_mix.carbon_free_share",
            ],
            YEAR_2023,
        )
    )
    assert len(rows) == 1
    row = rows[0]

    denominator = sql_sum_2023(db, ba_code, "and in_mix_denominator")
    assert denominator and denominator > 0

    expected = {
        "generation_mix.renewable_share": sql_sum_2023(db, ba_code, "and is_renewable")
        / denominator,
        "generation_mix.fossil_share": sql_sum_2023(db, ba_code, "and is_fossil")
        / denominator,
        "generation_mix.carbon_free_share": sql_sum_2023(
            db, ba_code, "and is_carbon_free"
        )
        / denominator,
    }
    for measure, want in expected.items():
        got = to_float(row[measure])
        assert got is not None, f"{measure} came back null for {ba_code}"
        assert math.isclose(got, want, rel_tol=REL_TOL), (
            f"{measure} {ba_code}: cube={got} sql={want}"
        )


@pytest.mark.parametrize(
    "ba_code, measure, fuel",
    [
        ("ERCO", "generation_mix.gas_share", "gas"),
        ("CISO", "generation_mix.hydro_share", "hydro"),
    ],
)
def test_per_fuel_share_spot_checks_vs_sql(cube_query, db, ba_code, measure, fuel):
    """Per-fuel share spot checks (gas_share ERCO, hydro_share CISO), 2023, vs SQL."""
    rows = cube_query(gen_query(ba_code, [measure], YEAR_2023))
    assert len(rows) == 1
    got = to_float(rows[0][measure])
    assert got is not None

    denominator = sql_sum_2023(db, ba_code, "and in_mix_denominator")
    numerator = sql_sum_2023(db, ba_code, f"and unified_fuel_category = '{fuel}'")
    want = numerator / denominator
    assert math.isclose(got, want, rel_tol=REL_TOL), (
        f"{measure} {ba_code}: cube={got} sql={want}"
    )


def test_oil_share_erco_is_null(cube_query, db):
    """oil_share is null for ERCO: petroleum is absent from its reporting, not zero."""
    oil_rows = db.execute(
        "select count(*) from marts.fct_hourly_generation "
        "where ba_code = 'ERCO' and unified_fuel_category = 'oil'"
    ).fetchone()[0]
    assert oil_rows == 0, "precondition: ERCO reports no petroleum rows"

    rows = cube_query(gen_query("ERCO", ["generation_mix.oil_share"], YEAR_2023))
    assert len(rows) == 1
    assert rows[0]["generation_mix.oil_share"] is None, (
        "oil_share for ERCO must be null (absence of data, not zero)"
    )


@pytest.mark.parametrize("ba_code", ["PJM", "ERCO", "CISO"])
def test_per_fuel_shares_sum_to_one(cube_query, ba_code):
    """Share coherence: the 10 per-fuel shares (null as 0) sum to 1.0 per BA, 2023."""
    rows = cube_query(gen_query(ba_code, PER_FUEL_SHARE_MEASURES, YEAR_2023))
    assert len(rows) == 1
    row = rows[0]

    total = 0.0
    for measure in PER_FUEL_SHARE_MEASURES:
        value = to_float(row[measure])
        if value is not None:
            total += value
    assert math.isclose(total, 1.0, rel_tol=1e-9, abs_tol=1e-9), (
        f"per-fuel shares for {ba_code} sum to {total}, expected 1.0"
    )


def test_denominator_vs_sql_ciso_2023(cube_query, db):
    """denominator_generation_mwh for CISO 2023 equals the SQL sum filtered on
    in_mix_denominator. Note: this warehouse has no storage rows for CISO 2023
    (storage categories appear only for ERCO, 2024 onward), so the denominator
    equals the total here; the actual storage exclusion is tested below."""
    rows = cube_query(
        gen_query(
            "CISO",
            ["generation_mix.denominator_generation_mwh"],
            YEAR_2023,
        )
    )
    assert len(rows) == 1
    denominator = to_float(rows[0]["generation_mix.denominator_generation_mwh"])
    assert denominator is not None

    want = sql_sum_2023(db, "CISO", "and in_mix_denominator")
    assert math.isclose(denominator, want, rel_tol=REL_TOL), (
        f"denominator_generation_mwh: cube={denominator} sql={want}"
    )


def test_storage_exclusion_erco_2025(cube_query, db):
    """denominator_generation_mwh excludes storage categories. Verified on
    ERCO 2025, the only BA/year span with storage rows in this warehouse.
    Storage nets negative over the year (charging exceeds discharge), so
    excluding it moves the denominator above the raw total; the test pins
    the exact relationship: total - denominator == storage sum, and the
    denominator matches the filtered SQL sum."""
    rows = cube_query(
        gen_query(
            "ERCO",
            [
                "generation_mix.generation_mwh",
                "generation_mix.denominator_generation_mwh",
            ],
            ["2025-01-01", "2025-12-31"],
        )
    )
    assert len(rows) == 1
    total = to_float(rows[0]["generation_mix.generation_mwh"])
    denominator = to_float(rows[0]["generation_mix.denominator_generation_mwh"])
    assert total is not None and denominator is not None

    year_2025 = (
        "and datetime_utc >= timestamp '2025-01-01' "
        "and datetime_utc < timestamp '2026-01-01'"
    )
    storage_sum = db.execute(
        f"""
        select sum(net_generation_mwh)
        from marts.fct_hourly_generation
        where ba_code = 'ERCO' and not in_mix_denominator {year_2025}
        """
    ).fetchone()[0]
    denominator_sql = db.execute(
        f"""
        select sum(net_generation_mwh)
        from marts.fct_hourly_generation
        where ba_code = 'ERCO' and in_mix_denominator {year_2025}
        """
    ).fetchone()[0]

    assert storage_sum is not None and storage_sum != 0, (
        "precondition: ERCO 2025 has nonzero storage generation to exclude"
    )
    assert denominator != total, "denominator must differ from total when storage exists"
    assert math.isclose(denominator, denominator_sql, rel_tol=REL_TOL), (
        f"denominator_generation_mwh: cube={denominator} sql={denominator_sql}"
    )
    assert math.isclose(total - denominator, storage_sum, rel_tol=1e-9, abs_tol=1e-6), (
        f"total - denominator = {total - denominator}, storage sum = {storage_sum}"
    )


def test_series_break_seam_is_served(cube_query):
    """generation_mwh grouped by source_regime across the 2024-07-01 series break
    returns rows from both the legacy and post_2024_break regimes."""
    rows = cube_query(
        gen_query(
            "CISO",
            ["generation_mix.generation_mwh"],
            ["2024-06-01", "2024-07-31"],
            dimensions=["generation_mix.source_regime"],
        )
    )
    regimes = {row["generation_mix.source_regime"] for row in rows}
    assert {"legacy", "post_2024_break"} <= regimes, (
        f"expected both sides of the series break in the seam window, got {regimes}"
    )
