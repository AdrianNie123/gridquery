"""Land the bounded EIA-930 subset from PUDL into DuckDB.

Reads three EIA-930 tables from the pinned PUDL stable release on the public
S3 bucket, filters to the target balancing authorities, and loads full
available history into the `landing` schema of data/gridquery.duckdb.

dlt is used for the load so the refresh is a single reproducible command.
For static parquet a plain COPY would also work; dlt is the stack choice
and stays thin here: full replace on every run, no incremental state.

Reload with: make land
"""

from pathlib import Path

import dlt
import duckdb

PUDL_RELEASE = "v2026.6.1"
BASE_URL = f"https://s3.us-west-2.amazonaws.com/pudl.catalyst.coop/{PUDL_RELEASE}"

# Codes confirmed against the release data (see docs/phase1_data_profile.md):
# PJM = PJM Interconnection, ERCO = ERCOT, CISO = California ISO.
BA_CODES = ("PJM", "ERCO", "CISO")

# core = as-reported plus EIA's own imputed/adjusted series.
# out_eia930__hourly_operations additionally carries PUDL's imputed demand
# and its imputation-code column, needed for the imputation-status rules.
TABLES = (
    "core_eia930__hourly_operations",
    "core_eia930__hourly_net_generation_by_energy_source",
    "out_eia930__hourly_operations",
)

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "gridquery.duckdb"
BATCH_ROWS = 500_000


def make_resource(table: str):
    @dlt.resource(name=table, write_disposition="replace")
    def read_table():
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        ba_list = ", ".join(f"'{ba}'" for ba in BA_CODES)
        result = con.execute(
            f"""
            SELECT *
            FROM read_parquet('{BASE_URL}/{table}.parquet')
            WHERE balancing_authority_code_eia IN ({ba_list})
            """
        )
        reader = result.to_arrow_reader(BATCH_ROWS)
        for batch in reader:
            yield batch

    return read_table


def main():
    DB_PATH.parent.mkdir(exist_ok=True)
    pipeline = dlt.pipeline(
        pipeline_name="eia930_landing",
        destination=dlt.destinations.duckdb(str(DB_PATH)),
        dataset_name="landing",
    )
    info = pipeline.run([make_resource(t) for t in TABLES])
    print(info)


if __name__ == "__main__":
    main()
