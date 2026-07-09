# GridQuery task runner.

.PHONY: land profile build dbt-test

DBT_FLAGS := --project-dir transform --profiles-dir transform

# Run + test all dbt models on top of the landed DuckDB.
build:
	uv run dbt deps $(DBT_FLAGS)
	uv run dbt build $(DBT_FLAGS)

# Run dbt tests only.
dbt-test:
	uv run dbt test $(DBT_FLAGS)

# Land the EIA-930 subset from PUDL into data/gridquery.duckdb (full replace).
land:
	uv run python ingest/eia930_pipeline.py

# Regenerate the facts behind docs/phase1_data_profile.md from the landed data.
profile:
	uv run python scripts/profile_phase1.py
