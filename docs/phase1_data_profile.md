# Phase 1 Data Profile — EIA-930 subset (PUDL) landed in DuckDB

Factual record of the landed data, per the verification checklist in
`docs/plans/phase1.md` §4. Every number in this document was produced by
`scripts/profile_phase1.py` (run with `make profile`) against the landed
database; nothing is estimated or assumed. Where a fact raises a decision,
it is flagged in §8 rather than decided here.

## 0. Provenance and reload

- **Source:** PUDL stable release **v2026.6.1**, public S3 bucket
  `s3://pudl.catalyst.coop` (anonymous HTTPS access, no credentials).
- **Landed tables** (schema `landing` in `data/gridquery.duckdb`):

| Table | Rows |
|---|---|
| `core_eia930__hourly_operations` | 285,048 |
| `core_eia930__hourly_net_generation_by_energy_source` | 5,415,912 |
| `out_eia930__hourly_operations` | 285,048 |

- **Filter applied at load:** `balancing_authority_code_eia IN ('PJM','ERCO','CISO')`, full available history.
- **Reload command:** `make land` (runs `ingest/eia930_pipeline.py`; full replace, no incremental state).

## 1. Balancing-authority codes (checklist item 1)

Confirmed codes as they appear in the data: **`PJM`**, **`ERCO`** (ERCOT), **`CISO`** (California ISO).
Each has exactly 95,016 rows in both operations tables (an identical, complete hourly spine).
No surprises: no sub-region rows appear in these tables (PUDL keeps sub-region demand in a
separate `*_subregion_demand` table, which was not landed).

## 2. Fuel-category labels (checklist item 2)

`generation_energy_source` in the net-generation table contains **19 distinct labels**.
Every label has a row for every BA-hour; availability below means hours with a
**non-null reported value** for at least one of our three BAs.

**The single most important finding of this phase:** EIA-930 switched its fuel
categorization on **2024-07-01**. Legacy labels stop and new labels start at that
boundary. This is a series break, not an overlap.

| Label | Data present | Notes |
|---|---|---|
| `coal` | 2018-07-01 → present | all 3 BAs |
| `gas` | 2018-07-01 → present | all 3 BAs |
| `nuclear` | 2018-07-01 → present | all 3 BAs |
| `oil` | 2018-07-01 → present | **PJM and CISO only; ERCO reports no `oil`** |
| `other` | 2018-07-01 → present | all 3 BAs |
| `hydro` | 2018-07-01 → **2024-07-01** | legacy label, ends at the break |
| `solar` | 2018-07-01 → **2024-07-01** | legacy label, ends at the break |
| `wind` | 2018-07-01 → **2024-07-01** | legacy label, ends at the break |
| `hydro_excluding_pumped_storage` | **2024-07-01** → present | replacement for `hydro` |
| `solar_wo_integrated_battery_storage` | **2024-07-01** → present | replacement for `solar` |
| `wind_wo_integrated_battery_storage` | **2024-07-01** → present | replacement for `wind` |
| `battery_storage` | 2024-10-23 → present | ERCO only |
| `unknown_energy_storage` | 2024-10-23 → 2025-12-15 | ERCO only; net negative total (charging) |
| `geothermal` | 2025-12-16 → present | CISO only |
| `pumped_storage` | no non-null values | empty for these 3 BAs |
| `solar_w_integrated_battery_storage` | no non-null values | empty for these 3 BAs |
| `wind_w_integrated_battery_storage` | no non-null values | empty for these 3 BAs |
| `other_energy_storage` | no non-null values | empty for these 3 BAs |
| `unknown` | no non-null values | empty for these 3 BAs |

Also note: **fuel-mix data begins 2018-07-01** for all categories. There is no
generation-by-fuel data for 2015-07 through 2018-06, even though demand exists there.

## 3. Mapping check for the seven core fuels (checklist item 3)

| PRD fuel | Data label(s) | Status |
|---|---|---|
| wind | `wind` (to 2024-07) + `wind_wo_integrated_battery_storage` (from 2024-07) | present, **split across the series break** |
| solar | `solar` (to 2024-07) + `solar_wo_integrated_battery_storage` (from 2024-07) | present, **split across the series break** |
| hydro | `hydro` (to 2024-07) + `hydro_excluding_pumped_storage` (from 2024-07) | present, **split across the series break**; see pumped-storage note below |
| nuclear | `nuclear` | clean, continuous |
| coal | `coal` | clean, continuous |
| natural gas | `gas` | clean, continuous |
| petroleum | `oil` | continuous, but **absent for ERCO** (ERCOT reports no oil category) |

Continuity evidence at the break (PJM annual sums, reported MWh): `hydro` 2023 =
15,445,864; `hydro_excluding_pumped_storage` 2025 = 15,467,921 — same order of
magnitude, consistent with a relabel rather than a redefinition of scope.

**Pumped-storage ambiguity (flagged, §8):** whether legacy `hydro` netted pumped-storage
pumping cannot be fully resolved from this data. Evidence recorded: PJM legacy `hydro`
has **zero negative hours** (min 18 MWh) despite PJM containing large pumped-storage
plants, so pumping load was not netted there; CISO shows small negatives in both the
legacy label (141 hours, min -425 MWh) and the new excluding-PS label (55 hours,
min -463 MWh). The new-regime `pumped_storage` label is entirely null for these BAs.

## 4. Imputation signal (checklist item 4)

The distinction is carried in **parallel value columns**, not a boolean flag:

- Every measure comes in three variants: `*_reported_mwh` (as reported),
  `*_adjusted_mwh` (EIA's cleaned series), `*_imputed_eia_mwh` (EIA's imputation,
  populated **only** for hours EIA imputed — 94,639–94,800 of 95,016 hours are null).
- `out_eia930__hourly_operations` additionally carries **PUDL's imputed demand**:
  `demand_imputed_pudl_mwh` (complete: **zero nulls** for all 3 BAs) plus
  `demand_imputed_pudl_mwh_imputation_code` (varchar), which is **non-null exactly
  where PUDL replaced the value** and states why:

| Code | Rows (of 285,048) |
|---|---|
| (null = not imputed) | 283,853 |
| `missing_value` | 1,004 |
| `anomalous_region` | 124 |
| `double_delta` | 25 |
| `local_outlier_low` | 25 |
| `local_outlier_high` | 10 |
| `single_delta` | 3 |
| `global_outlier` | 3 |
| `identical_run` | 1 |

Integrity rule 3 is satisfiable: the imputation-code column identifies imputed demand
hours exactly. Overall imputed share is 0.42% of hours (1,195 of 285,048); worst
BA-year is CISO 2016 at 2.64%. Note there is **no PUDL-imputed series for
net generation by fuel** — only EIA's reported/adjusted/imputed-EIA variants exist there.

## 5. Coverage and gaps (checklist item 5)

- Window landed: **2015-07-01 through 2026-05-02/03 UTC** (start and end hours differ
  by BA by a few hours; EIA-930 begins 2015-07-01 in each BA's local time).
- The hourly spine is **continuous for all three BAs**: 95,016 rows each, zero
  duplicate (BA, hour) pairs, and every consecutive gap is exactly 1 hour.
- Full calendar years available: **2016–2025**. 2015 and 2026 are partial.
- Missing values live *inside* the spine as nulls. Per BA-year
  (hours / reported-demand nulls / PUDL-imputed hours / imputed %):

| BA | Year | Hours | Reported null | Imputed hours | Imputed % |
|---|---|---|---|---|---|
| CISO | 2015 | 4,408 | 6 | 6 | 0.14 |
| CISO | 2016 | 8,784 | 170 | 232 | 2.64 |
| CISO | 2017 | 8,760 | 36 | 36 | 0.41 |
| CISO | 2018 | 8,760 | 42 | 42 | 0.48 |
| CISO | 2019 | 8,760 | 9 | 89 | 1.02 |
| CISO | 2020 | 8,784 | 3 | 4 | 0.05 |
| CISO | 2021 | 8,760 | 5 | 5 | 0.06 |
| CISO | 2022 | 8,760 | 3 | 3 | 0.03 |
| CISO | 2023 | 8,760 | 2 | 2 | 0.02 |
| CISO | 2024 | 8,784 | 48 | 48 | 0.55 |
| CISO | 2025 | 8,760 | 48 | 50 | 0.57 |
| CISO | 2026 | 2,936 | 54 | 54 | 1.84 |
| ERCO | 2015 | 4,410 | 0 | 0 | 0.00 |
| ERCO | 2016 | 8,784 | 72 | 72 | 0.82 |
| ERCO | 2017 | 8,760 | 72 | 72 | 0.82 |
| ERCO | 2018 | 8,760 | 96 | 96 | 1.10 |
| ERCO | 2019 | 8,760 | 0 | 0 | 0.00 |
| ERCO | 2020 | 8,784 | 0 | 0 | 0.00 |
| ERCO | 2021 | 8,760 | 0 | 9 | 0.10 |
| ERCO | 2022 | 8,760 | 0 | 0 | 0.00 |
| ERCO | 2023 | 8,760 | 0 | 0 | 0.00 |
| ERCO | 2024 | 8,784 | 0 | 0 | 0.00 |
| ERCO | 2025 | 8,760 | 48 | 48 | 0.55 |
| ERCO | 2026 | 2,934 | 24 | 24 | 0.82 |
| PJM | 2015 | 4,411 | 1 | 1 | 0.02 |
| PJM | 2016 | 8,784 | 26 | 48 | 0.55 |
| PJM | 2017 | 8,760 | 25 | 25 | 0.29 |
| PJM | 2018 | 8,760 | 1 | 1 | 0.01 |
| PJM | 2019 | 8,760 | 1 | 4 | 0.05 |
| PJM | 2020 | 8,784 | 46 | 54 | 0.61 |
| PJM | 2021 | 8,760 | 0 | 3 | 0.03 |
| PJM | 2022 | 8,760 | 23 | 23 | 0.26 |
| PJM | 2023 | 8,760 | 25 | 25 | 0.29 |
| PJM | 2024 | 8,784 | 47 | 48 | 0.55 |
| PJM | 2025 | 8,760 | 25 | 25 | 0.29 |
| PJM | 2026 | 2,933 | 46 | 46 | 1.57 |

- **Earliest usable start year:** demand quality is acceptable from 2016 onward
  (worst year 2.64% imputed). But since **fuel-mix data only begins 2018-07-01**,
  the earliest full calendar year for generation-mix metrics is **2019** — which
  matches the PRD's target window. Decision flagged in §8.

## 6. Grain and timestamp handling (checklist item 6)

- Grain confirmed **hourly**: all 95,015 consecutive gaps are exactly 1:00:00 for
  every BA; zero duplicate (BA, hour) pairs.
- Source parquet stores `datetime_utc` as a naive UTC timestamp. **The dlt load
  converted it to `TIMESTAMP WITH TIME ZONE`** in DuckDB. The instants are correct,
  but any session that groups by `year(datetime_utc)` will use the session timezone —
  queries must `SET TimeZone='UTC'` (the profiling script does). This must be handled
  deliberately in the dbt layer (Phase 2 consideration).
- All aggregation in this profile is on **UTC calendar boundaries**. Whether
  "calendar year" for metrics means UTC or BA-local time is a Phase 2 definition
  choice; the difference is a few boundary hours per year.

## 7. Row counts and sanity (checklist item 7)

Reported demand (`demand_reported_mwh`), full landed window:

| BA | Min | Median | p99.9 | Max | Negative hours | Zero hours |
|---|---|---|---|---|---|---|
| CISO | 14 | 24,656 | 45,473 | 51,104 | 0 | 0 |
| ERCO | 24,763 | 44,289 | 83,397 | 85,544 | 0 | 0 |
| PJM | 56,260 | 89,088 | 148,538 | **2,147,480,000** | 0 | 0 |

Anomalies found (present in reported data, already handled by the cleaned series):

- **PJM sentinel garbage:** 3 consecutive hours on 2021-10-19 (03:00–05:00 UTC) with
  reported demand of 1,527,760,000 / 2,147,480,000 (≈ INT32_MAX) / 431,044,000 MWh.
  PUDL codes all three `global_outlier`; the adjusted (73,530 / 70,134 / 67,665) and
  PUDL-imputed (77,023 / 73,806 / 70,877) values are plausible. Raw `*_reported_*`
  columns must never be aggregated without outlier policy — use the imputed/adjusted
  series or filter by imputation code.
- **CISO low outlier:** reported minimum of 14 MWh (vs a PUDL-imputed minimum of
  14,372 MWh) — coded `local_outlier_low`.
- PUDL-imputed demand has no negatives, no nulls, and sane maxima
  (CISO 51,104 / ERCO 85,544 / PJM 160,560 MWh).

Annual demand anchors for hand-checking (sum of `demand_imputed_pudl_mwh`, TWh):
ERCO 2023 = **446.79**, ERCO 2024 = 463.60, CISO 2023 = 218.19, PJM 2023 = 784.81,
PJM 2025 = 843.06. (ERCOT's publicly reported 2023 energy use is ~445–446 TWh;
same ballpark — this is a plausibility anchor, not a validation.)

## 8. Open questions for reviewer (blocking Phase 2)

1. **Final BA set:** PJM, ERCO, CISO landed and healthy. Confirm three BAs, or add a
   contrast region (re-run of `make land` required).
2. **Fuel-category mapping across the 2024-07-01 series break.** Proposed handling,
   pending your approval: a mapping table with validity windows that unifies
   `hydro` + `hydro_excluding_pumped_storage` → hydro, `solar` + `solar_wo_…` → solar,
   `wind` + `wind_wo_…` → wind, giving continuous series; the break date and the
   pumped-storage caveat (§3) documented in the metric catalog. Alternatives: keep
   the two regimes separate (breaks YoY growth spanning 2024) or truncate mix metrics
   to post-break (loses most of the window).
3. **`oil` absent for ERCO:** fossil share for ERCO would be coal + gas only.
   Confirm that is acceptable (it reflects the source data, not a bug).
4. **Storage and residual categories:** `battery_storage`, `unknown_energy_storage`
   (ERCO, can be negative = net charging), `geothermal` (CISO, from 2025-12), `other`.
   Proposed: exclude storage from fuel-mix denominators; include `other` in the
   denominator but in no named bucket; geothermal needs a call — PRD's renewable
   definition (wind/solar/hydro) currently excludes it.
5. **Start year:** propose **2019** (first full calendar year with fuel-mix data;
   demand-only metrics could extend back to 2016 if wanted).
6. **Demand basis for metrics:** propose `demand_imputed_pudl_mwh` as the primary
   demand series (complete, outliers fixed, imputation-code column preserved for
   surfacing imputed shares), with `demand_reported_mwh` retained for transparency.
   The raw reported series contains sentinel garbage (§7) and must not be the
   metric basis.

Phase 2 (dbt models) does not begin until these are confirmed.
