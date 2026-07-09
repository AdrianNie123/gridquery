# plan.md — Phase 2: dbt staging, marts, and tests

## Context

Phase 1 landed and verified the EIA-930 subset (PJM/ERCO/CISO, PUDL v2026.6.1) in `data/gridquery.duckdb` schema `landing`, and the six gate decisions are locked in `docs/ROADMAP.md`. Phase 2 turns that landed data into clean, tested, analysis-ready marts for the Phase 3 Cube semantic layer. Metric math (growth, shares, CAGR) stays out of the marts; the Phase 1 decisions get encoded once each, in documented models. No Cube, no NL interface, no front end.

## Series-break quantification: already done, encoded here

The ROADMAP's condition ("quantify before unifying") was satisfied at the Phase 1 gate: `docs/phase1_data_profile.md` §10 records the full quantification (zero label-overlap hours; seam and cross-regime-YoY analysis). Result: no detectable level break for wind, solar, or PJM hydro; an immaterial one for ERCO hydro (0.12% of its generation); CISO hydro (10.5%) ambiguous between hydrology and definitional narrowing. Consequence, per the approved decision: the unified series is built AND every row carries the break signal, and metrics spanning 2024-07-01 are documented as affected. This plan does not re-derive the analysis; it encodes its consequences and adds dbt tests that enforce the boundary behavior permanently.

## One new basis decision (approval requested as part of this plan)

**Generation value basis: `net_generation_adjusted_mwh`** (EIA's cleaned series), with an `is_imputed_eia` flag (true where `net_generation_imputed_eia_mwh` is non-null) so imputation status is surfaced, and `net_generation_reported_mwh` carried for transparency. Evidence from the landed data (2019+, non-storage labels): adjusted never drops a reported value, fills 168–1,552 gaps per BA, and differs from reported in only 0–476 rows per BA. There is no PUDL-imputed series for generation, so this parallels the demand decision as closely as the data allows.

## Tooling (new dependencies named for approval)

- Python deps via uv: `dbt-core`, `dbt-duckdb` (the locked stack's transformation layer + its DuckDB adapter).
- dbt package: `dbt_utils` (for `unique_combination_of_columns`, `accepted_range`); declared in `packages.yml`.
- dbt project in `transform/` with a checked-in `profiles.yml` targeting `data/gridquery.duckdb`. Makefile gains `make build` (dbt build: run + test) and `make dbt-test`.

## Model DAG

```
sources (schema landing)
  out_eia930__hourly_operations           core_eia930__hourly_net_generation_by_energy_source
        │                                        │
  stg_eia930__hourly_demand              stg_eia930__hourly_generation        seeds:
        │                                        │                            fuel_category_mapping
        │                                int_generation__fuel_mapped  ◄───────  balancing_authorities
        │                                        │
  fct_hourly_demand                      fct_hourly_generation      dim_fuel_category   dim_balancing_authority
```

**Seeds (versioned CSVs — the decisions as data):**
- `fuel_category_mapping.csv` — one row per source label (all 19 observed; accepted-values keeps surprises loud). Columns: `source_label`, `unified_fuel_category`, `source_regime` (`legacy` / `post_2024_break` / `both`), `is_storage`, `in_mix_denominator` (false exactly for storage), `is_renewable`, `is_fossil`, `is_carbon_free`, `notes`. Mapping: `hydro`+`hydro_excluding_pumped_storage`→`hydro`; `solar`+`solar_wo_…`+`solar_w_…`→`solar` (the `_w_` labels are empty today; mapped so a future release lands correctly); same for wind; `coal`/`gas`/`oil`/`nuclear`/`other`/`geothermal`/`unknown` map to themselves; storage labels map to storage categories with `in_mix_denominator=false`. Classification flags encode the locked definitions (renewable = wind/solar/hydro/geothermal-when-present; fossil = coal/gas/oil; carbon-free = renewable + nuclear). The share/growth *math* stays in Cube; the *classification* lives here once, documented and testable.
- `balancing_authorities.csv` — `ba_code`, `ba_name`, `iana_timezone`, `notes` (ERCO: petroleum absent from EIA-930 reporting — absence of data, not zero; CISO: geothermal only from 2025-12).

**Staging (views, schema `staging`) — light cleaning, no business logic:**
- `stg_eia930__hourly_demand`: from `out_eia930__hourly_operations`. Selects `demand_imputed_pudl_mwh AS demand_mwh` (locked basis), `demand_reported_mwh`, `imputation_code`, `is_imputed` (code not null), `ba_code`, `datetime_utc` **cast to naive UTC TIMESTAMP** (dlt landed TIMESTAMPTZ; normalizing at staging kills the session-timezone bug class found in Phase 1).
- `stg_eia930__hourly_generation`: same treatment; selects adjusted/reported/imputed-EIA columns and `source_label`.

**Intermediate (view, schema `intermediate`) — the decisions, encoded once:**
- `int_generation__fuel_mapped`: staging generation joined to `fuel_category_mapping`; outputs `unified_fuel_category`, `source_regime` (derived from the source label, the truthful break signal — no date arithmetic), `net_generation_mwh` (adjusted basis), `is_imputed_eia`, the denominator/classification flags. Model doc states the 2024-07-01 break, cites profile §10, and names the CISO-hydro caveat.

**Marts (tables, schema `marts`) — hourly grain only; Cube aggregates:**
- `fct_hourly_demand` — grain BA × UTC hour, window ≥ 2019-01-01 (locked start year). Columns: ba_code, datetime_utc, demand_mwh, is_imputed, imputation_code, demand_reported_mwh.
- `fct_hourly_generation` — grain BA × UTC hour × unified_fuel_category, ≥ 2019-01-01, rows with non-null generation only. Columns: + net_generation_mwh, source_regime, in_mix_denominator, is_storage, is_renewable/is_fossil/is_carbon_free, is_imputed_eia.
- `dim_fuel_category` (from seed: one row per unified category) and `dim_balancing_authority`.
- Deliberately no daily/annual marts: DuckDB aggregates 95k-row/BA hourly facts instantly, and one grain avoids duplicated truth. If Phase 3 wants materialized rollups, they're added then.

## Where each locked decision is encoded

| Decision | Encoded in |
|---|---|
| BA set (PJM/ERCO/CISO) | staging filter + `dim_balancing_authority` + relationship test |
| Start year 2019 | mart window filter, documented in mart schema.yml |
| Demand basis = PUDL-imputed, code surfaced | `stg_eia930__hourly_demand` |
| Series-break unified mapping + flag | seed + `int_generation__fuel_mapped` (`source_regime`) + boundary tests |
| ERCOT petroleum absent, not zero | `balancing_authorities` seed note + singular test (ERCO has zero oil rows — fails loudly if ERCOT ever starts reporting oil) + model docs |
| Storage/geothermal/other denominator | `in_mix_denominator` flag in seed, exposed in the fact table |
| Generation basis = adjusted (new, this plan) | `stg_eia930__hourly_generation` |

## Test suite

Generic (schema.yml):
- `fct_hourly_demand`: unique combination (ba_code, datetime_utc); not_null on ba_code, datetime_utc, demand_mwh; accepted_range demand_mwh between 5,000 and 250,000 (envelope of landed data — observed PUDL-imputed min 14,372 / max 160,560 — with headroom; bounds documented with this basis, catching the sentinel-garbage error class); accepted_values on imputation_code (the 8 observed codes, null allowed).
- `fct_hourly_generation`: unique combination (ba_code, datetime_utc, unified_fuel_category); not_null on grain + net_generation_mwh; accepted_range net_generation_mwh between -20,000 and 100,000 (observed adjusted min -9,504 / max 75,926, headroom, documented); accepted_values on unified_fuel_category (exact seed set — a surprise category fails loudly); relationships to dim_fuel_category and dim_balancing_authority.
- Staging: accepted_values on source_label (the 19 observed labels) — a new PUDL label fails loudly before it reaches marts.
- Seeds: unique + not_null on keys.

All accepted-range bounds follow the change policy added to ROADMAP.md in Step 0(c): documented basis, stop-and-investigate on failure, never widened just to pass.

Singular tests:
- Break boundary: no legacy-regime label has non-null generation after 2024-07-02; no post-break label has any before 2024-06-30.
- Break continuity: for each BA, unified hydro/solar/wind each have rows within 48h on both sides of 2024-07-01 (the flag and mapping actually meet at the seam).
- Regime-label consistency: `source_regime` in the mart always matches the seed's regime for that source label.
- Mapping completeness: zero distinct source labels in staging that are missing from the seed.
- Join consistency: every (ba, hour) in `fct_hourly_generation` exists in `fct_hourly_demand` (demand is the complete spine).
- ERCO-oil absence test (above).

## Second plausibility anchor (done condition)

Sum `fct_hourly_demand.demand_mwh` for CISO 2023 (already known to be 218.19 TWh from landing; the mart must reproduce it) and compare against the operator's/EIA's publicly reported annual figure, found via web search at execution time with the source cited. Record both numbers, source, date, and the delta in a new `docs/verification_anchors.md` alongside the ERCOT anchor. Review thresholds (for this plausibility check, stated up front): within ~1% = pass; 1–5% = investigate the definitional difference (EIA-930 BA demand vs operator settlement load are not identical concepts) and document it; >5% or unexplained = stop and ask before proceeding. If CISO sourcing proves ambiguous, PJM 2023 (784.81 TWh landed) is the fallback anchor.

## Delegation (named now; I will pause for explicit go-ahead when reached)

After the model structure is built and compiling in the primary session:
1. **Subagent A — dbt test suite:** write the schema.yml generic tests and singular test SQL from the spec above. Bounded, verifiable (dbt build passes/fails), needs no architecture context.
2. **Subagent B — model documentation:** schema.yml descriptions for every model/column, from the profile doc + this plan's decision table. Bounded; I review for decision-fidelity.

Structure design and the seed encoding of series-break/denominator decisions stay in the primary session. When I reach the delegation point I will name these two tasks again and wait for your go-ahead before spawning anything.

## Step 0 (applied 2026-07-09, commit 950d992): ROADMAP.md governance edits

Three edits so the locked-decisions text is unambiguous before the seed encodes it:

**(a) Resolve the geothermal contradiction.** The current "Storage / geothermal / other" bullet says geothermal is "excluded from renewable and fossil numerators" and, in the same bullet, "treat as renewable when present." The gate decision was the latter. Replace that bullet with two:

> - **Mix denominator:** gross generation excluding storage charge/discharge. All storage categories (`battery_storage`, `pumped_storage`, `*_energy_storage`) are excluded from the denominator and from every named bucket. `other` and `unknown` stay in the denominator but belong to no named bucket.
> - **Geothermal:** counts in the renewable and carbon-free numerators when present, and in the denominator. CISO-only, first data 2025-12-16, so negligible in the core window. This amends the PRD §6.2 renewable definition per the Phase 1 gate decision.

And in the "Metric definitions" bullet, change "renewable = wind/solar/hydro" to "renewable = wind/solar/hydro, plus geothermal when present (Phase 1 gate amendment; negligible in-window)".

**(b) Lock the generation basis.** Add to the locked-decisions list:

> - **Generation basis:** `net_generation_adjusted_mwh` (EIA's cleaned series), never raw reported. Evidence from the landed data: adjusted never drops a reported value, fills 168–1,552 gaps per BA, differs from reported in only 0–476 rows per BA. No PUDL-imputed series exists for generation. Carry `is_imputed_eia` (EIA-imputed hours) so imputation status stays surfaced (integrity rule 3), and keep `net_generation_reported_mwh` for transparency. (Locked at Phase 2 plan approval, 2026-07-09.)

**(c) Add a change policy for static test bounds.** Append to the Phase 2 tests paragraph:

> Accepted-range bounds are derived from the landed data envelope and documented with their basis (PUDL release, observed min/max, date). Policy: a failing range test is a stop-and-investigate event first, never a prompt to widen bounds. Bounds change only when a new landing changes the envelope, and the change must cite the re-run profile output (`make profile`) in the commit that adjusts them.

Seed consequence of (a): `fuel_category_mapping.csv` sets `is_renewable=true` and `is_carbon_free=true` for geothermal (carbon-free = renewable + nuclear).

## Execution order

0. Apply the three ROADMAP.md edits above. Commit ("lock generation basis, resolve geothermal classification, add test-bounds change policy").
1. Materialize this plan as `docs/plans/phase2.md`. Add dbt deps (`uv add dbt-core dbt-duckdb`), scaffold `transform/`, Makefile targets. Commit.
2. Seeds + staging + intermediate + marts, built incrementally with `dbt build` at each step (primary session). Commit at first full green build.
3. Delegation checkpoint (pause for go-ahead) → test suite + docs via subagents; I review, integrate, re-run `dbt build`. Commit.
4. Anchor verification + `docs/verification_anchors.md`. Commit.
5. Stop for phase-gate review: marts + test results + anchor.

## Verification (phase done conditions)

- `make build` runs dbt build (run + all tests) green from a clean checkout on top of the Phase 1 DuckDB.
- Every locked decision traceable to one documented model/seed (table above).
- Spot-check: mart-summed CISO 2023 demand equals the landing-computed 218.19 TWh; ERCOT 2023 remains 446.79 TWh through the mart path.
- Second anchor recorded in `docs/verification_anchors.md`.
- Human review of marts + test results before Phase 3.
