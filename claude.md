# CLAUDE.md — GridQuery

Standing instructions for this repository. Read this and `PRD.md` before planning or writing any code.

## What this project is
A small, governed data product over U.S. grid demand data: clean hourly data → dbt marts → a Cube semantic layer of governed metrics → an evaluated natural-language query interface → a Streamlit front end. The point of the project is **architecture, governance, and evaluation**, not model complexity. Full scope, datasets, and metric definitions are in `PRD.md` — read it before proposing any plan.

## Locked technical stack
- **Ingestion:** dlt (data load tool)
- **Storage / compute:** DuckDB (local, Parquet)
- **Transformation:** dbt Core, with dbt tests on every model
- **Semantic layer:** Cube (governed metric definitions live here)
- **NL interface:** an LLM constrained to query the Cube semantic layer only — never free-form SQL against raw tables
- **Evaluation:** a golden-set harness (~50 questions) run on every change
- **Front end:** Streamlit
- **Orchestration:** simple task runner first (Makefile/wrapper); Dagster only as a week-3 stretch
- Do not introduce new tools or dependencies without asking first.

## Data
- **Primary source:** PUDL (Catalyst Cooperative), analysis-ready Parquet.
- **Primary dataset:** EIA-930 hourly grid data — demand, net generation by fuel, by balancing authority.
- **Scope:** a bounded subset of balancing authorities (PJM, ERCOT, CISO/California, plus an optional contrast region), calendar years ~2019–2024. Confirm exact BA codes, fuel-category labels, and imputation-flag columns against the actual data in phase one — do NOT assume schema from memory.
- Deferred, do not build without asking: FERC Form 1, LMP/price data, external carbon feeds.

## Non-negotiable integrity rules
1. **Never invent a formula or a number.** Every figure shown anywhere (docs, README, front end) must be produced by the pipeline. No illustrative/placeholder numbers.
2. **Metrics requiring a judgment call are already decided in `PRD.md`** (growth basis = total-annual YoY + window CAGR; renewable = wind/solar/hydro; carbon-free = renewable + nuclear as a separate metric; fossil = coal/gas/petroleum). Do not silently redefine them. If the data makes a definition untenable, stop and flag it.
3. **Surface imputation status.** EIA-930 contains imputed values. Do not silently mix imputed and reported values where the distinction matters.
4. **The LLM never writes raw SQL against source tables.** It selects and parameterizes governed Cube metrics, or it refuses/clarifies.
5. **Refusal is a feature.** Questions that don't map to a governed metric should be refused or clarified, not answered by guessing.
6. **Weather-normalization is explicitly out of scope for v1** and named as documented future work. Do not build it.

## Workflow expectations
- **Use plan mode before building each component.** Propose the approach, wait for approval, then build. Do not build a whole layer unprompted.
- **Work the open-decisions and phases in order** (see `PRD.md` §11–12). Ingestion → marts+tests → Cube metrics → NL interface → eval harness → front end.
- **Delegate bounded, verifiable tasks to subagents** (e.g., writing dbt tests, scaffolding the eval harness, generating the metric-catalog docs). Keep whole-architecture reasoning with the primary agent.
- **Commit at every working checkpoint** with clear messages so state is recoverable.
- **Verify before advancing.** After each phase, expect the human to check outputs (run tests, hand-check a metric against a known number, read eval results). Do not treat a phase as done until it's verified.

## Scope-control (hard rule at 2–3 week ceiling)
If the semantic layer + eval harness is consuming more than ~40% of total time by end of week 2, cut the free-form NL interface down to parameterized queries and keep everything else. Never cut: dbt tests, metric-definition docs, the honest limitations section.

## Documentation standard
- README foregrounds the architecture + grounding + evaluation story, states datasets and access methods explicitly, and includes an honest limitations section.
- Report eval accuracy as-measured, with a failure-mode breakdown. Do not round up or hide failures.
- Architecture inspired by Snowflake Cortex Analyst / Databricks Genie; any vendor performance figures are vendor claims, not reproduced as fact.

## Style
- Prose and comments: clear and direct, no filler. No em-dashes.
- Prefer explicit, readable SQL and Python over clever one-liners.
- When a choice involves a tradeoff, state it briefly rather than hiding it.
