# GridQuery task runner.

.PHONY: land profile build dbt-test cube-up cube-down cube-test ask nl-test eval eval-pin eval-score eval-report eval-test app

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

# Start the Cube semantic layer (Docker, pinned image; see semantic/docker-compose.yml).
cube-up:
	docker compose -f semantic/docker-compose.yml up -d --wait

cube-down:
	docker compose -f semantic/docker-compose.yml down

# Run the semantic-layer metric tests against a running Cube instance.
cube-test:
	uv run pytest semantic/tests -v

# Ask the NL interface one question (needs Cube running and ANTHROPIC_API_KEY in .env).
ask:
	uv run python -m nl "$(Q)"

# Run the NL-interface tests (offline unless ANTHROPIC_API_KEY is set).
nl-test:
	uv run pytest nl/tests -v

# Pin expected eval results by executing the golden plans against running Cube.
eval-pin:
	uv run python -m eval pin

# Full eval run: submit the golden set via the Batches API, score, write artifact + report.
eval:
	uv run python -m eval run

# Re-score a saved raw batch (no API cost): make eval-score RAW=eval/results/raw_<id>.jsonl
eval-score:
	uv run python -m eval score --raw "$(RAW)"

# Regenerate docs/eval_report.md from eval/results/latest.json.
eval-report:
	uv run python -m eval report

# Run the eval-harness tests (offline, no API key needed).
eval-test:
	uv run pytest eval/tests -v

# Launch the Streamlit front end (needs Cube running and ANTHROPIC_API_KEY in .env).
# PYTHONPATH=. because the repo is not an installed package (same reason as
# the pytest pythonpath setting): the pages import nl/ from the repo root.
app:
	PYTHONPATH=. uv run streamlit run app/Home.py
