# plan.md — Phase 3: Cube semantic layer (governed metrics)

## Context

Phase 2 passed its gate (47/47 dbt build, anchors verified, sign-off 2026-07-13). Phase 3 builds the Cube semantic layer over the Phase 2 marts: ~11 governed metrics with explicit definitions, exposed through Cube's REST + meta APIs, each with at least one test (PRD §2.3, §6). This is the ROADMAP's "core of project" phase. The Phase 4 NL interface grounds itself in Cube's `/v1/meta` catalog, so the governed surface built here is what makes the whole product trustworthy.

Decisions locked at Phase 3 planning (2026-07-13, recorded in `docs/ROADMAP.md`):
- **Carbon-intensity proxy: deferred to future work** (PRD §11 open decision 5 resolved). Named in README limitations later; not built.
- **Cube runtime: Docker, pinned image.** Pinned at execution time to `cubejs/cube:v1.6.69` (the tag `latest`/`v1` tracked on Docker Hub as of 2026-07-13; the 1.6 line is the actively maintained stable line). Docker 29.2.1 confirmed installed.
- The landed DuckDB file is format v1.5.4; Cube's bundled DuckDB driver must read it (smoke-tested in step 1).

## New dependencies (approved with this plan, per CLAUDE.md)

- `cubejs/cube:v1.6.69` Docker image in `semantic/docker-compose.yml`.
- Python dev deps via uv: `pytest`, `requests` — for the metric test harness that queries Cube's REST API.
- No other new tools. Streamlit/LLM deps belong to later phases.

## Structure

New top-level `semantic/` directory:
- `docker-compose.yml` — pinned Cube image, mounts `semantic/` as `/cube/conf` and `data/` (for the DuckDB file), env: `CUBEJS_DB_TYPE=duckdb`, `CUBEJS_DB_DUCKDB_DATABASE_PATH`, dev-mode API secret.
- `model/cubes/*.yml`, `model/views/*.yml` — the data model (YAML, checked in).
- `tests/` — pytest suite hitting `/cubejs-api/v1/load` and `/v1/meta`.
- Makefile targets: `make cube-up`, `make cube-down`, `make cube-test`.

**Known risk, named up front — resolved at step 1:** Cube and dbt both open the same DuckDB file; write locks could conflict. Findings: the stock DuckDB driver opens `CUBEJS_DB_DUCKDB_DATABASE_PATH` read-write with no read-only option (fails on a `:ro` mount), so `semantic/cube.js` uses a `driverFactory` that opens in-memory DuckDB and attaches the warehouse `READ_ONLY`; the data volume is mounted `:ro` as a second guarantee. Verified empirically: `make build` (dbt, 47/47) succeeds while Cube holds the read-only attach, and Cube keeps serving afterward. Caveat: after a rebuild, restart Cube (`make cube-down && make cube-up`) to guarantee it reads the fresh state rather than a stale snapshot. No Parquet fallback needed.

## Data model design

**Cubes (internal building blocks):**
- `hourly_demand` ← `marts.fct_hourly_demand`. Measures: sum/max/avg of `demand_mwh`, hour count, imputed-hour count. Dimensions: `ba_code`, `datetime_utc` (time), `is_imputed`, `imputation_code`.
- `hourly_generation` ← `marts.fct_hourly_generation`. Measures: total generation; denominator generation (filtered `in_mix_denominator`); renewable / fossil / carbon-free generation (filtered on the seed-derived flags — the classification stays in the seed, Cube only references the flags). Dimensions: `ba_code`, `unified_fuel_category`, `source_regime`, `is_imputed_eia`, time.
- `annual_demand` — SQL-defined cube aggregating demand to BA × calendar-year grain with a `lag()` window for YoY growth. **Partial-year guard:** the landed window ends 2026-05-03, so 2026 is incomplete; the cube carries an `is_complete_year` flag (8,760/8,784 expected hours) and growth metrics are defined over complete years only. Silently computing "2026 growth" from five months would violate integrity rule 1.

**Views (the governed surface the LLM and front end are allowed to see):** Cube views exposing only the named governed metrics and their allowed dimensions/filters. Phase 4's grounding contract is: the LLM sees `/v1/meta` for these views only.

**The ~11 governed metrics** (locked definitions from ROADMAP/PRD; formulas documented in catalog):
1. `total_demand` (sum, PUDL-imputed basis)
2. `peak_demand` (max hourly)
3. `average_demand`
4. `demand_yoy_growth` (calendar-year totals, complete years only)
5. `demand_cagr` (window CAGR over complete years; if this can't be expressed as a governed Cube measure, it becomes a documented formula in the catalog computed from the governed annual series — never ad-hoc math; escalate if even that feels ungoverned)
6. `generation_by_fuel` (sum of adjusted net generation by unified category)
7. `generation_mix_share` (fuel ÷ denominator generation; storage excluded per locked decision)
8. `renewable_share` (wind/solar/hydro/geothermal ÷ denominator)
9. `fossil_share` (coal/gas/oil ÷ denominator)
10. `carbon_free_share` (renewable + nuclear ÷ denominator)
11. `imputed_demand_share` (imputed hours ÷ total hours — surfaces integrity rule 3 as a queryable metric)

Divide metrics guard against zero denominators and document missing-period behavior (PRD §6.3). Series-break surfacing: `source_regime` is an exposed dimension and the catalog states that metrics spanning 2024-07-01 are affected (CISO hydro caveat). ERCOT petroleum absence noted in catalog (absence of data, not zero).

## Tests (every metric ≥ 1, PRD §2.3)

Pytest harness queries Cube's REST API and compares against independently computed DuckDB SQL over the marts:
- Anchor reproduction through the full stack: ERCOT 2023 total = 446.79 TWh; CISO 2023 peak = 44,007 MWh.
- Per-metric slice checks (each metric, at least one BA/period, Cube result == direct mart SQL within float tolerance).
- Share coherence: named-bucket shares + other/unknown sum to 1.0 for a sample slice; storage excluded.
- Growth guard: no growth value returned for incomplete years.
- `/v1/meta` exposes exactly the governed views/metrics (catalog completeness test — Phase 4 depends on it).

## Delegation (pause for explicit go-ahead when reached)

After the data model is built and serving in the primary session:
1. **Subagent A — pytest metric test suite** from the spec above. Bounded, verifiable.
2. **Subagent B — metric catalog doc** (`docs/metric_catalog.md`): every metric's plain-language definition, formula, grain, parameters, imputation/series-break caveats. Reviewed for decision-fidelity before integration.

Model structure, metric encoding, and growth/partial-year handling stay in the primary session.

## Execution order

0. Commit the Phase 2 gate close: ROADMAP phase table flip + the two new locked decisions. (Done: commit 01f90fa.)
1. Materialize this plan as `docs/plans/phase3.md`. Scaffold `semantic/` (compose file, config, first cube), verify Cube starts and answers one query against the DuckDB marts. Commit.
2. Build the full data model: cubes, views, all 11 metrics, partial-year guard. Verify via `/v1/meta` + spot queries. Commit.
3. Delegation checkpoint (pause for go-ahead) → test suite + metric catalog via subagents; review, integrate, re-run. Commit.
4. Full verification pass (below). Commit.
5. Stop for phase-gate review: metric list + catalog + test results.

## Verification (phase done conditions)

- `make cube-up` starts Cube from a clean checkout; `make cube-test` runs the pytest suite green.
- `/v1/meta` exposes exactly the three governed views and their documented members (the 11 named metrics plus the supporting measures listed in `docs/metric_catalog.md`), and nothing else.
- Both anchors reproduce through the Cube API path exactly.
- Every metric traceable to a locked definition; catalog documents formula, grain, caveats.
- Human review before Phase 4.

## Stop-and-ask triggers

- DuckDB file locking forces the Parquet-export fallback (architecture change).
- Any locked metric definition that cannot be expressed as a governed Cube measure/view.
- CAGR cannot stay governed under the documented-formula approach.
- Cube's DuckDB driver is incompatible with the DuckDB v1.5.4 file format.
