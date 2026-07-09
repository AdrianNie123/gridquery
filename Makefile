# GridQuery task runner. Phase 1 targets only; later phases add dbt/cube/eval.

.PHONY: land profile

# Land the EIA-930 subset from PUDL into data/gridquery.duckdb (full replace).
land:
	uv run python ingest/eia930_pipeline.py

# Regenerate the facts behind docs/phase1_data_profile.md from the landed data.
profile:
	uv run python scripts/profile_phase1.py
