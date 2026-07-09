"""Profile the landed EIA-930 subset for the Phase 1 verification checklist.

Prints every fact recorded in docs/phase1_data_profile.md, computed from the
landed DuckDB database. Run with: make profile

Sections map 1:1 to the checklist in docs/plans/phase1.md section 4.
"""

from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gridquery.duckdb"

OPS = "landing.core_eia930__hourly_operations"
GEN = "landing.core_eia930__hourly_net_generation_by_energy_source"
OUT_OPS = "landing.out_eia930__hourly_operations"

CORE_FUEL_TARGETS = ["wind", "solar", "hydro", "nuclear", "coal", "gas", "oil"]


def show(con, title, sql):
    print(f"\n--- {title} ---")
    print(con.sql(sql))


def dump(con, title, sql):
    """Print full result as CSV lines (show() truncates long tables)."""
    print(f"\n--- {title} ---")
    rows = con.execute(sql).fetchall()
    cols = [d[0] for d in con.execute(sql).description]
    print(",".join(cols))
    for r in rows:
        print(",".join(str(x) for x in r))


def main():
    con = duckdb.connect(str(DB_PATH), read_only=True)
    # dlt landed datetime_utc as TIMESTAMPTZ; pin the session to UTC so
    # year() groupings and printed timestamps are UTC, not machine-local.
    con.execute("SET TimeZone='UTC'")

    print("=" * 70)
    print("SECTION 0: landed tables and row counts")
    print("=" * 70)
    show(con, "tables in landing schema", """
        SELECT table_name, estimated_size AS row_count
        FROM duckdb_tables() WHERE schema_name = 'landing'
        ORDER BY table_name""")

    print("\n" + "=" * 70)
    print("SECTION 1: balancing-authority codes present")
    print("=" * 70)
    for t in (OPS, GEN, OUT_OPS):
        show(con, f"distinct BA codes in {t}", f"""
            SELECT balancing_authority_code_eia, count(*) AS rows
            FROM {t} GROUP BY 1 ORDER BY 1""")

    print("\n" + "=" * 70)
    print("SECTION 2: fuel-category labels (net generation by energy source)")
    print("=" * 70)
    show(con, "all categories: rows, date range, total net gen (reported)", f"""
        SELECT generation_energy_source,
               count(*) AS rows,
               min(datetime_utc) AS first_hour,
               max(datetime_utc) AS last_hour,
               round(sum(net_generation_reported_mwh)) AS total_reported_mwh
        FROM {GEN} GROUP BY 1 ORDER BY 1""")
    show(con, "categories per BA (rows with non-null reported gen)", f"""
        SELECT generation_energy_source,
               sum(CASE WHEN balancing_authority_code_eia='PJM'  AND net_generation_reported_mwh IS NOT NULL THEN 1 ELSE 0 END) AS pjm,
               sum(CASE WHEN balancing_authority_code_eia='ERCO' AND net_generation_reported_mwh IS NOT NULL THEN 1 ELSE 0 END) AS erco,
               sum(CASE WHEN balancing_authority_code_eia='CISO' AND net_generation_reported_mwh IS NOT NULL THEN 1 ELSE 0 END) AS ciso
        FROM {GEN} GROUP BY 1 ORDER BY 1""")

    print("\n" + "=" * 70)
    print("SECTION 3: mapping checks for the seven core fuels + overlap tests")
    print("=" * 70)
    present = {r[0] for r in con.execute(
        f"SELECT DISTINCT generation_energy_source FROM {GEN}").fetchall()}
    for f in CORE_FUEL_TARGETS:
        print(f"  target '{f}': {'PRESENT' if f in present else 'MISSING'}")
    print(f"  note: petroleum appears as 'oil', natural gas as 'gas'")

    # Overlap test A: is 'hydro' a superset that includes pumped storage,
    # or does it run alongside 'hydro_excluding_pumped_storage'?
    show(con, "hydro family: yearly sums per BA (reported)", f"""
        SELECT balancing_authority_code_eia AS ba,
               year(datetime_utc) AS yr,
               round(sum(CASE WHEN generation_energy_source='hydro' THEN net_generation_reported_mwh END)) AS hydro,
               round(sum(CASE WHEN generation_energy_source='hydro_excluding_pumped_storage' THEN net_generation_reported_mwh END)) AS hydro_excl_ps,
               round(sum(CASE WHEN generation_energy_source='pumped_storage' THEN net_generation_reported_mwh END)) AS pumped_storage
        FROM {GEN}
        WHERE generation_energy_source LIKE 'hydro%' OR generation_energy_source='pumped_storage'
        GROUP BY 1, 2 ORDER BY 1, 2""")

    # Overlap test B: solar vs solar_w/wo integrated battery storage.
    show(con, "solar family: yearly sums per BA (reported)", f"""
        SELECT balancing_authority_code_eia AS ba,
               year(datetime_utc) AS yr,
               round(sum(CASE WHEN generation_energy_source='solar' THEN net_generation_reported_mwh END)) AS solar,
               round(sum(CASE WHEN generation_energy_source='solar_w_integrated_battery_storage' THEN net_generation_reported_mwh END)) AS solar_w_bat,
               round(sum(CASE WHEN generation_energy_source='solar_wo_integrated_battery_storage' THEN net_generation_reported_mwh END)) AS solar_wo_bat
        FROM {GEN}
        WHERE generation_energy_source LIKE 'solar%'
        GROUP BY 1, 2 ORDER BY 1, 2""")

    show(con, "wind family: yearly sums per BA (reported)", f"""
        SELECT balancing_authority_code_eia AS ba,
               year(datetime_utc) AS yr,
               round(sum(CASE WHEN generation_energy_source='wind' THEN net_generation_reported_mwh END)) AS wind,
               round(sum(CASE WHEN generation_energy_source='wind_w_integrated_battery_storage' THEN net_generation_reported_mwh END)) AS wind_w_bat,
               round(sum(CASE WHEN generation_energy_source='wind_wo_integrated_battery_storage' THEN net_generation_reported_mwh END)) AS wind_wo_bat
        FROM {GEN}
        WHERE generation_energy_source LIKE 'wind%'
        GROUP BY 1, 2 ORDER BY 1, 2""")

    # The yearly tables above show legacy categories ending in 2024 and new
    # ones starting there. Pin down the exact switch boundary per category.
    show(con, "non-null reported date range per category (regime boundaries)", f"""
        SELECT generation_energy_source,
               min(datetime_utc) FILTER (WHERE net_generation_reported_mwh IS NOT NULL) AS first_nonnull,
               max(datetime_utc) FILTER (WHERE net_generation_reported_mwh IS NOT NULL) AS last_nonnull,
               count(*) FILTER (WHERE net_generation_reported_mwh IS NOT NULL) AS nonnull_rows
        FROM {GEN} GROUP BY 1 ORDER BY 1""")

    print("\n" + "=" * 70)
    print("SECTION 4: imputation signal")
    print("=" * 70)
    show(con, "columns of out_eia930__hourly_operations", f"""
        SELECT column_name, data_type FROM duckdb_columns()
        WHERE schema_name='landing' AND table_name='out_eia930__hourly_operations'
        ORDER BY column_index""")
    show(con, "distinct PUDL imputation codes with counts", f"""
        SELECT demand_imputed_pudl_mwh_imputation_code AS code, count(*) AS rows
        FROM {OUT_OPS} GROUP BY 1 ORDER BY rows DESC""")
    show(con, "imputed share of hours per BA per year (PUDL imputation code not null)", f"""
        SELECT balancing_authority_code_eia AS ba, year(datetime_utc) AS yr,
               count(*) AS hours,
               sum(CASE WHEN demand_imputed_pudl_mwh_imputation_code IS NOT NULL THEN 1 ELSE 0 END) AS imputed_hours,
               round(100.0 * sum(CASE WHEN demand_imputed_pudl_mwh_imputation_code IS NOT NULL THEN 1 ELSE 0 END) / count(*), 2) AS imputed_pct
        FROM {OUT_OPS} GROUP BY 1, 2 ORDER BY 1, 2""")
    show(con, "reported vs EIA-imputed vs adjusted demand: null counts (core ops)", f"""
        SELECT balancing_authority_code_eia AS ba,
               count(*) AS rows,
               sum(CASE WHEN demand_reported_mwh IS NULL THEN 1 ELSE 0 END) AS reported_null,
               sum(CASE WHEN demand_imputed_eia_mwh IS NULL THEN 1 ELSE 0 END) AS imputed_eia_null,
               sum(CASE WHEN demand_adjusted_mwh IS NULL THEN 1 ELSE 0 END) AS adjusted_null
        FROM {OPS} GROUP BY 1 ORDER BY 1""")

    print("\n" + "=" * 70)
    print("SECTION 5: coverage and gaps per BA per year")
    print("=" * 70)
    show(con, "hours per BA per year vs expected (core ops)", f"""
        SELECT balancing_authority_code_eia AS ba,
               year(datetime_utc) AS yr,
               count(*) AS hours_present,
               CASE WHEN (yr % 4 = 0 AND yr % 100 != 0) OR yr % 400 = 0 THEN 8784 ELSE 8760 END AS hours_expected,
               count(*) - (CASE WHEN (yr % 4 = 0 AND yr % 100 != 0) OR yr % 400 = 0 THEN 8784 ELSE 8760 END) AS diff
        FROM {OPS} GROUP BY 1, 2 ORDER BY 1, 2""")
    show(con, "first/last hour per BA (core ops)", f"""
        SELECT balancing_authority_code_eia AS ba,
               min(datetime_utc) AS first_hour, max(datetime_utc) AS last_hour
        FROM {OPS} GROUP BY 1 ORDER BY 1""")
    show(con, "null demand_reported per BA per year (data-quality view)", f"""
        SELECT balancing_authority_code_eia AS ba, year(datetime_utc) AS yr,
               sum(CASE WHEN demand_reported_mwh IS NULL THEN 1 ELSE 0 END) AS demand_reported_null,
               round(100.0 * sum(CASE WHEN demand_reported_mwh IS NULL THEN 1 ELSE 0 END) / count(*), 2) AS null_pct
        FROM {OPS} GROUP BY 1, 2 ORDER BY 1, 2""")

    print("\n" + "=" * 70)
    print("SECTION 6: grain and timestamp handling")
    print("=" * 70)
    show(con, "duplicate (BA, hour) rows in core ops (expect 0)", f"""
        SELECT count(*) AS duplicate_rows FROM (
            SELECT balancing_authority_code_eia, datetime_utc, count(*) AS n
            FROM {OPS} GROUP BY 1, 2 HAVING n > 1)""")
    show(con, "timestamp spacing distribution in hours (core ops, PJM)", f"""
        WITH d AS (
            SELECT datetime_utc - lag(datetime_utc) OVER (ORDER BY datetime_utc) AS gap
            FROM {OPS} WHERE balancing_authority_code_eia='PJM')
        SELECT gap, count(*) AS n FROM d WHERE gap IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 5""")
    show(con, "timestamp column type (all landed tables)", """
        SELECT table_name, column_name, data_type FROM duckdb_columns()
        WHERE schema_name='landing' AND column_name LIKE 'datetime%'
        ORDER BY table_name""")

    print("\n" + "=" * 70)
    print("SECTION 7: sanity ranges for demand")
    print("=" * 70)
    show(con, "demand_reported_mwh stats per BA (core ops)", f"""
        SELECT balancing_authority_code_eia AS ba,
               round(min(demand_reported_mwh)) AS min_mwh,
               round(quantile_cont(demand_reported_mwh, 0.5)) AS median_mwh,
               round(quantile_cont(demand_reported_mwh, 0.999)) AS p999_mwh,
               round(max(demand_reported_mwh)) AS max_mwh,
               sum(CASE WHEN demand_reported_mwh < 0 THEN 1 ELSE 0 END) AS negative_hours,
               sum(CASE WHEN demand_reported_mwh = 0 THEN 1 ELSE 0 END) AS zero_hours
        FROM {OPS} GROUP BY 1 ORDER BY 1""")
    # PJM showed max reported demand near INT32_MAX: locate sentinel garbage
    # values and confirm the adjusted / PUDL-imputed series are sane there.
    show(con, "hours with reported demand > 500000 MWh (sentinel outliers)", f"""
        SELECT c.balancing_authority_code_eia AS ba, c.datetime_utc,
               c.demand_reported_mwh, c.demand_adjusted_mwh,
               o.demand_imputed_pudl_mwh, o.demand_imputed_pudl_mwh_imputation_code AS code
        FROM {OPS} c
        JOIN {OUT_OPS} o USING (balancing_authority_code_eia, datetime_utc)
        WHERE c.demand_reported_mwh > 500000
        ORDER BY 1, 2""")
    show(con, "demand_imputed_pudl_mwh stats per BA (out ops)", f"""
        SELECT balancing_authority_code_eia AS ba,
               round(min(demand_imputed_pudl_mwh)) AS min_mwh,
               round(max(demand_imputed_pudl_mwh)) AS max_mwh,
               sum(CASE WHEN demand_imputed_pudl_mwh < 0 THEN 1 ELSE 0 END) AS negative_hours,
               sum(CASE WHEN demand_imputed_pudl_mwh IS NULL THEN 1 ELSE 0 END) AS null_hours
        FROM {OUT_OPS} GROUP BY 1 ORDER BY 1""")

    print("\n" + "=" * 70)
    print("SECTION 8: 2024-07-01 series-break discontinuity quantification")
    print("=" * 70)
    # Legacy fuel labels end and replacement labels begin at 2024-07-01.
    # Unifying each pair into one series is only legitimate if the two labels
    # measure close to the same physical quantity. Three checks per family:
    # (a) overlap hours (both labels non-null at once), (b) a seam comparison
    # of mean daily generation in adjacent 28-day windows, (c) each
    # cross-regime monthly YoY ratio vs the range of same-calendar-month YoY
    # ratios observed entirely within the legacy regime (2020-01..2024-06,
    # i.e. the approved 2019+ window).
    families = {
        "hydro": ("hydro", "hydro_excluding_pumped_storage"),
        "solar": ("solar", "solar_wo_integrated_battery_storage"),
        "wind": ("wind", "wind_wo_integrated_battery_storage"),
    }

    for fam, (old, new) in families.items():
        show(con, f"{fam}: hours where BOTH labels are non-null (double-count risk)", f"""
            SELECT o.balancing_authority_code_eia AS ba, count(*) AS overlap_hours
            FROM {GEN} o JOIN {GEN} n
              ON o.balancing_authority_code_eia = n.balancing_authority_code_eia
             AND o.datetime_utc = n.datetime_utc
            WHERE o.generation_energy_source = '{old}'
              AND n.generation_energy_source = '{new}'
              AND o.net_generation_reported_mwh IS NOT NULL
              AND n.net_generation_reported_mwh IS NOT NULL
            GROUP BY 1 ORDER BY 1""")

    for fam, (old, new) in families.items():
        show(con, f"{fam}: seam comparison, mean daily MWh "
                  f"(legacy 2024-06-02..06-29 vs new 2024-07-02..07-29)", f"""
            WITH daily AS (
                SELECT balancing_authority_code_eia AS ba,
                       date_trunc('day', datetime_utc) AS d,
                       sum(CASE WHEN generation_energy_source = '{old}'
                                THEN net_generation_reported_mwh END) AS old_mwh,
                       sum(CASE WHEN generation_energy_source = '{new}'
                                THEN net_generation_reported_mwh END) AS new_mwh
                FROM {GEN} GROUP BY 1, 2)
            SELECT ba,
                   round(avg(old_mwh) FILTER (WHERE d BETWEEN DATE '2024-06-02' AND DATE '2024-06-29')) AS legacy_daily_mwh,
                   round(avg(new_mwh) FILTER (WHERE d BETWEEN DATE '2024-07-02' AND DATE '2024-07-29')) AS new_daily_mwh,
                   round(100.0 * (new_daily_mwh - legacy_daily_mwh) / legacy_daily_mwh, 1) AS step_pct,
                   round((new_daily_mwh - legacy_daily_mwh) * 365) AS annualized_gap_mwh
            FROM daily GROUP BY ba ORDER BY ba""")

    for fam, (old, new) in families.items():
        dump(con, f"{fam}: cross-regime monthly YoY ratio vs legacy-regime "
                  f"same-month YoY range (2020-01..2024-06 baseline)", f"""
            WITH monthly AS (
                SELECT balancing_authority_code_eia AS ba,
                       date_trunc('month', datetime_utc) AS m,
                       sum(CASE WHEN generation_energy_source IN ('{old}', '{new}')
                                THEN net_generation_reported_mwh END) AS mwh
                FROM {GEN} GROUP BY 1, 2),
            yoy AS (
                SELECT a.ba, a.m, a.mwh / b.mwh AS ratio
                FROM monthly a
                JOIN monthly b ON a.ba = b.ba AND b.m = a.m - INTERVAL 1 YEAR
                WHERE a.mwh IS NOT NULL AND b.mwh > 0),
            baseline AS (
                SELECT ba, month(m) AS cal_month,
                       min(ratio) AS hist_min, median(ratio) AS hist_med,
                       max(ratio) AS hist_max, count(*) AS n_years
                FROM yoy
                WHERE m BETWEEN TIMESTAMPTZ '2020-01-01' AND TIMESTAMPTZ '2024-06-01'
                GROUP BY 1, 2),
            cross_regime AS (
                SELECT ba, m, month(m) AS cal_month, ratio FROM yoy
                WHERE m BETWEEN TIMESTAMPTZ '2024-07-01' AND TIMESTAMPTZ '2025-06-01')
            SELECT c.ba, strftime(c.m, '%Y-%m') AS month,
                   round(c.ratio, 3) AS cross_ratio,
                   round(b.hist_min, 3) AS hist_min,
                   round(b.hist_med, 3) AS hist_med,
                   round(b.hist_max, 3) AS hist_max,
                   c.ratio BETWEEN b.hist_min AND b.hist_max AS inside_range
            FROM cross_regime c JOIN baseline b USING (ba, cal_month)
            ORDER BY c.ba, c.m""")

    show(con, "materiality: family share of gross non-storage generation, 2019-2025", f"""
        WITH g AS (
            SELECT balancing_authority_code_eia AS ba,
                   CASE WHEN generation_energy_source IN ('hydro', 'hydro_excluding_pumped_storage') THEN 'hydro'
                        WHEN generation_energy_source IN ('solar', 'solar_wo_integrated_battery_storage') THEN 'solar'
                        WHEN generation_energy_source IN ('wind', 'wind_wo_integrated_battery_storage') THEN 'wind'
                        ELSE 'all_other_non_storage' END AS fam,
                   sum(net_generation_reported_mwh) AS mwh
            FROM {GEN}
            WHERE datetime_utc >= TIMESTAMPTZ '2019-01-01'
              AND datetime_utc < TIMESTAMPTZ '2026-01-01'
              AND generation_energy_source NOT IN (
                  'battery_storage', 'pumped_storage', 'other_energy_storage',
                  'unknown_energy_storage')
            GROUP BY 1, 2)
        SELECT ba, fam, round(mwh) AS mwh,
               round(100.0 * mwh / sum(mwh) OVER (PARTITION BY ba), 2) AS share_pct
        FROM g ORDER BY ba, fam""")

    show(con, "summary: cross-regime months inside legacy YoY range, per BA x family", f"""
        WITH monthly AS (
            SELECT balancing_authority_code_eia AS ba,
                   CASE WHEN generation_energy_source IN ('hydro', 'hydro_excluding_pumped_storage') THEN 'hydro'
                        WHEN generation_energy_source IN ('solar', 'solar_wo_integrated_battery_storage') THEN 'solar'
                        WHEN generation_energy_source IN ('wind', 'wind_wo_integrated_battery_storage') THEN 'wind'
                   END AS fam,
                   date_trunc('month', datetime_utc) AS m,
                   sum(net_generation_reported_mwh) AS mwh
            FROM {GEN} WHERE generation_energy_source IN (
                'hydro', 'hydro_excluding_pumped_storage',
                'solar', 'solar_wo_integrated_battery_storage',
                'wind', 'wind_wo_integrated_battery_storage')
            GROUP BY 1, 2, 3),
        yoy AS (
            SELECT a.ba, a.fam, a.m, a.mwh / b.mwh AS ratio
            FROM monthly a
            JOIN monthly b ON a.ba = b.ba AND a.fam = b.fam AND b.m = a.m - INTERVAL 1 YEAR
            WHERE a.mwh IS NOT NULL AND b.mwh > 0),
        baseline AS (
            SELECT ba, fam, month(m) AS cal_month, min(ratio) AS lo, max(ratio) AS hi
            FROM yoy WHERE m BETWEEN TIMESTAMPTZ '2020-01-01' AND TIMESTAMPTZ '2024-06-01'
            GROUP BY 1, 2, 3)
        SELECT c.ba, c.fam,
               count(*) AS cross_months,
               sum(CASE WHEN c.ratio BETWEEN b.lo AND b.hi THEN 1 ELSE 0 END) AS inside_range
        FROM yoy c JOIN baseline b
          ON c.ba = b.ba AND c.fam = b.fam AND month(c.m) = b.cal_month
        WHERE c.m BETWEEN TIMESTAMPTZ '2024-07-01' AND TIMESTAMPTZ '2025-06-01'
        GROUP BY 1, 2 ORDER BY 1, 2""")


if __name__ == "__main__":
    main()
