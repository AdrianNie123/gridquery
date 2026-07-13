# Metric catalog - GridQuery governed metrics

This catalog documents every governed metric served by the GridQuery semantic layer. Audience: an analyst deciding which metric answers a question, and the Phase 4 natural-language layer, which grounds itself in this surface and nothing else.

**What "governed" means here.** Every answer the product gives comes from a named, version-controlled metric defined in the Cube semantic layer (`semantic/model/`). Three Cube views, `demand`, `demand_growth`, and `generation_mix`, are the entire public surface; the underlying cubes are private. The LLM never writes raw SQL against source tables. It selects and parameterizes these governed metrics, or it refuses or asks for clarification. A question that does not map to a metric in this catalog is not answerable, by design.

**Data bases (locked decisions, `docs/ROADMAP.md`):**

- Demand: PUDL-imputed demand series (`demand_mwh`), never raw reported. Imputation status is carried through and queryable.
- Generation: EIA adjusted series (`net_generation_adjusted_mwh`), never raw reported. EIA imputation status is carried through.
- Window: 2019-01-01 onward. The landed data ends 2026-05-03, so 2026 is a partial year.
- Balancing authorities: PJM, ERCO, CISO only.
- All timestamps are UTC, hour-beginning. Calendar-year aggregations use UTC hours.

**The eleven governed metrics:**

| Metric | View | Member(s) |
|---|---|---|
| total_demand | demand | total_demand_mwh |
| peak_demand | demand | peak_demand_mwh |
| average_demand | demand | average_demand_mwh |
| demand_yoy_growth | demand_growth | demand_yoy_growth |
| demand_cagr | demand_growth | demand_cagr |
| generation_by_fuel | generation_mix | generation_mwh (grouped by unified_fuel_category) |
| generation_mix_share | generation_mix | coal_share, gas_share, oil_share, nuclear_share, hydro_share, solar_share, wind_share, geothermal_share, other_share, unknown_share |
| renewable_share | generation_mix | renewable_share |
| fossil_share | generation_mix | fossil_share |
| carbon_free_share | generation_mix | carbon_free_share |
| imputed_demand_share | demand | imputed_demand_share |

The views also expose supporting members that back these metrics (`hours`, `imputed_hours`, `annual_total_demand_mwh`, `denominator_generation_mwh`, `renewable_generation_mwh`, `fossil_generation_mwh`, `carbon_free_generation_mwh`, `imputed_generation_rows_share`). They are queryable and governed by the same definitions, but the eleven metrics above are the named answer surface.

**Fuel classification (locked, from PRD and Phase 1 gate amendment):** renewable = wind, solar, hydro, geothermal; fossil = coal, gas, oil (petroleum); carbon-free = renewable plus nuclear. Classification flags live in the `fuel_category_mapping` seed and flow through the mart; the semantic layer references the flags, it does not redefine them.

---

## total_demand

| | |
|---|---|
| View | demand |
| Member | total_demand_mwh |
| Grain | any aggregation of BA x UTC hour |
| Dimensions | ba_code, datetime_utc (any time granularity), is_imputed, imputation_code |

Total electricity demand in MWh over the selected period, on the PUDL-imputed basis.

Formula: `SUM(demand_mwh)` over the selected BA-hours.

Caveats:

- The sum mixes reported and imputed hours. Filter or group by `is_imputed`, or check `imputed_demand_share` for the same slice, when the distinction matters.

## peak_demand

| | |
|---|---|
| View | demand |
| Member | peak_demand_mwh |
| Grain | any aggregation of BA x UTC hour |
| Dimensions | ba_code, datetime_utc, is_imputed, imputation_code |

Maximum hourly demand in MWh within the selected period.

Formula: `MAX(demand_mwh)` over the selected BA-hours.

Caveats:

- This is the maximum of hourly averages, not an instantaneous peak. Operator-published peaks are minute-level and will be at or above this value. The verification anchor (`docs/verification_anchors.md`, anchor 2) documents this for CISO 2023: the pipeline hourly peak came in about 1.2% below the CAISO-published instantaneous peak, consistent with the definitional difference.
- A multi-BA selection without `ba_code` grouping returns the max over all BAs' hours, not a coincident system peak. Group by `ba_code` for per-BA peaks.

## average_demand

| | |
|---|---|
| View | demand |
| Member | average_demand_mwh |
| Grain | any aggregation of BA x UTC hour |
| Dimensions | ba_code, datetime_utc, is_imputed, imputation_code |

Mean hourly demand in MWh over the selected period.

Formula: `AVG(demand_mwh)` over the selected BA-hours.

## demand_yoy_growth

| | |
|---|---|
| View | demand_growth |
| Member | demand_yoy_growth |
| Grain | BA x calendar year (UTC) |
| Dimensions | ba_code, year, is_complete_year |

Year-over-year demand growth: this year's total annual demand over last year's total, minus 1. This is the locked growth basis (total-annual YoY, from PRD via ROADMAP).

Formula, per BA-year, where both the year and the prior year are complete:

```
demand_yoy_growth = total_demand_mwh(year) / total_demand_mwh(year - 1) - 1
```

As implemented, the measure sums the qualifying current-year totals and the qualifying prior-year totals across the selection and divides, so aggregating several years returns the growth of the summed totals, not an average of per-year growth rates.

Caveats:

- Defined over complete calendar years only. A year qualifies when every expected hour is present (`is_complete_year`). The landed data ends 2026-05-03, so 2026 is partial and any request for 2026 growth returns null. This is the partial-year guard: computing growth from five months of data would be a fabricated number.
- Group or filter by `ba_code`. A multi-BA selection sums demand across BAs before dividing.

## demand_cagr

| | |
|---|---|
| View | demand_growth |
| Member | demand_cagr |
| Grain | BA x calendar year (UTC), evaluated over the selected year range |
| Dimensions | ba_code, year, is_complete_year |

Compound annual growth rate of total annual demand between the first and last complete calendar years in the selection.

Formula, over the complete years in the selection:

```
demand_cagr = (total_last / total_first) ^ (1 / (year_last - year_first)) - 1
```

where `total_first` and `total_last` are the annual demand totals of the earliest and latest complete years selected.

Caveats:

- Valid per balancing authority: group or filter by `ba_code`. A multi-BA selection without `ba_code` grouping is not meaningful.
- Complete years only; partial 2026 never enters the endpoints. Null when the selection spans fewer than two complete years.

## generation_by_fuel

| | |
|---|---|
| View | generation_mix |
| Member | generation_mwh, grouped by unified_fuel_category |
| Grain | any aggregation of BA x UTC hour x unified fuel category |
| Dimensions | ba_code, datetime_utc, unified_fuel_category, source_regime, in_mix_denominator, is_imputed_eia |

Total net generation in MWh by unified fuel category, on the EIA adjusted basis (`net_generation_adjusted_mwh`).

Formula: `SUM(net_generation_mwh)` over the selected rows, typically grouped by `unified_fuel_category`.

Caveats:

- `unified_fuel_category` unifies each fuel across the 2024-07-01 EIA-930 recategorization (legacy labels and post-break labels map to one series per fuel). Categories: coal, gas, oil, nuclear, hydro, solar, wind, geothermal, other, unknown, plus storage categories.
- Storage categories are included in this metric when selected. Only the mix-share denominator excludes them.
- Storage reporting is sparse in EIA-930 as landed (PUDL v2026.6.1): only ERCO carries storage values, from 2024-10-22 onward, and its net storage generation sums negative (charging exceeds discharge). CISO and PJM storage labels exist but hold no reported or adjusted values, despite CISO's real-world battery fleet. Absence of data, not zero.
- Any result whose window spans 2024-07-01 crosses the series break. `source_regime` (legacy, post_2024_break) is exposed so the break can be inspected. Phase 1 quantification (`docs/phase1_data_profile.md` section 10) found no evidence of a level break for wind or solar and none material for hydro at PJM or ERCO; CISO hydro is the one genuinely ambiguous case, where a definitional narrowing cannot be ruled out against an expected hydrological decline.
- A fuel a BA does not report is absent from the data, not zero. ERCO reports no petroleum.

## generation_mix_share

| | |
|---|---|
| View | generation_mix |
| Members | coal_share, gas_share, oil_share, nuclear_share, hydro_share, solar_share, wind_share, geothermal_share, other_share, unknown_share |
| Grain | any aggregation of BA x UTC hour |
| Dimensions | ba_code, datetime_utc, source_regime, is_imputed_eia |

One governed metric parameterized by fuel: the share of a single fuel in gross generation. Implemented as one measure per unified category so the denominator stays the full mix denominator regardless of query filters. Do not filter by `unified_fuel_category` to compute a share; use the named per-fuel measure.

Formula, per fuel f:

```
f_share = SUM(net_generation_mwh WHERE unified_fuel_category = f)
          / NULLIF(SUM(net_generation_mwh WHERE in_mix_denominator), 0)
```

Caveats:

- Denominator: gross generation excluding all storage charge/discharge categories (battery storage, pumped storage, and related energy-storage labels). `other` and `unknown` remain in the denominator but belong to no named bucket, so the ten shares sum to 1 for a slice where every fuel is reported.
- A null share means the BA does not report that fuel: absence of data, not zero. ERCO reports no petroleum, so `oil_share` is null for ERCO.
- `geothermal_share`: CISO only, first data 2025-12, null elsewhere and negligible in the core window.
- `hydro_share`, `solar_share`, `wind_share` are unified across the 2024-07-01 series break. For windows spanning that date, see the series-break caveat under generation_by_fuel; the CISO hydro ambiguity applies directly to `hydro_share` for CISO.
- The share is null when the denominator is zero for the selection.

## renewable_share

| | |
|---|---|
| View | generation_mix |
| Member | renewable_share |
| Grain | any aggregation of BA x UTC hour |
| Dimensions | ba_code, datetime_utc, source_regime, is_imputed_eia |

Share of generation from renewable categories: wind, solar, hydro, geothermal. The geothermal inclusion is a Phase 1 gate amendment to the PRD definition; geothermal is CISO-only with first data 2025-12, so it is negligible in the core window.

Formula:

```
renewable_share = SUM(net_generation_mwh WHERE is_renewable)
                  / NULLIF(SUM(net_generation_mwh WHERE in_mix_denominator), 0)
```

Caveats:

- Same denominator rules as generation_mix_share: storage excluded, other/unknown in the denominator but in no bucket.
- Windows spanning 2024-07-01 cross the series break. The numerator is mostly wind, solar, and hydro, exactly the recategorized families; the CISO hydro ambiguity (`docs/phase1_data_profile.md` section 10) therefore applies to CISO renewable_share across the break.
- Null when the denominator is zero for the selection.

## fossil_share

| | |
|---|---|
| View | generation_mix |
| Member | fossil_share |
| Grain | any aggregation of BA x UTC hour |
| Dimensions | ba_code, datetime_utc, source_regime, is_imputed_eia |

Share of generation from fossil categories: coal, gas, oil (petroleum).

Formula:

```
fossil_share = SUM(net_generation_mwh WHERE is_fossil)
               / NULLIF(SUM(net_generation_mwh WHERE in_mix_denominator), 0)
```

Caveats:

- ERCO reports no petroleum, so ERCO fossil generation is coal plus gas by construction. This is an absence in ERCOT's EIA-930 reporting, not a zero.
- Same denominator rules as the other shares. Null when the denominator is zero.

## carbon_free_share

| | |
|---|---|
| View | generation_mix |
| Member | carbon_free_share |
| Grain | any aggregation of BA x UTC hour |
| Dimensions | ba_code, datetime_utc, source_regime, is_imputed_eia |

Share of generation from carbon-free categories: the renewable set (wind, solar, hydro, geothermal) plus nuclear. Kept as a separate metric from renewable_share per the locked definitions; the two are never merged.

Formula:

```
carbon_free_share = SUM(net_generation_mwh WHERE is_carbon_free)
                    / NULLIF(SUM(net_generation_mwh WHERE in_mix_denominator), 0)
```

Caveats:

- Inherits the series-break caveat through its renewable components: windows spanning 2024-07-01 are affected, with the CISO hydro ambiguity applying to CISO.
- Same denominator rules as the other shares. Null when the denominator is zero.

## imputed_demand_share

| | |
|---|---|
| View | demand |
| Member | imputed_demand_share |
| Grain | any aggregation of BA x UTC hour |
| Dimensions | ba_code, datetime_utc, is_imputed, imputation_code |

Share of hours in the selection whose demand value was imputed by PUDL rather than reported. This metric exists to make imputation status itself queryable (integrity rule 3): before trusting a demand figure for a slice, this metric says how much of it rests on imputed values.

Formula:

```
imputed_demand_share = COUNT(hours WHERE is_imputed) / NULLIF(COUNT(hours), 0)
```

Caveats:

- Counts hours, not energy: it is the fraction of BA-hours flagged imputed, not the fraction of MWh.
- Demand-side only. Generation imputation is surfaced separately via the `is_imputed_eia` dimension and the supporting `imputed_generation_rows_share` measure on the generation_mix view.

---

## Cross-cutting caveats

**Imputation is surfaced, never hidden.** Demand rows carry `is_imputed` and `imputation_code` (PUDL); generation rows carry `is_imputed_eia` (EIA). Any metric can be filtered or split on these dimensions, and `imputed_demand_share` quantifies the demand-side mix directly.

**The 2024-07-01 series break.** EIA-930 recategorized fuel labels effective 2024-07-01. The unified fuel series are built from a validity-windowed mapping with zero label overlap, so no double counting is possible, and every row carries `source_regime`. Any generation or share metric evaluated over a window spanning 2024-07-01 crosses this break. Phase 1 quantified the boundary (`docs/phase1_data_profile.md` section 10): no evidence of a level break for wind or solar in any BA, no measurable step for PJM hydro, an immaterial shift for ERCO hydro, and one genuinely ambiguous case, CISO hydro, where a real definitional narrowing cannot be distinguished from an expected hydrological decline after an exceptionally wet 2023. Treat CISO hydro comparisons across the break with that ambiguity in mind.

**Peaks are hourly.** All demand data is hourly; every peak is a max of hourly averages and sits at or below operator-published instantaneous peaks (see `docs/verification_anchors.md`).

**Partial years return null growth.** The landed window ends 2026-05-03. Growth metrics require complete calendar years and return null where a year is incomplete.

---

## Not governed (by design)

Questions outside the metrics above are refused or clarified, not answered by guessing. Refusal is a feature: an ungoverned answer is a fabricated one.

Named exclusions:

- **Carbon-intensity proxy: deferred to future work.** Resolved at Phase 3 planning (2026-07-13). It can be added later as one more governed metric with cited emission factors; until then, questions about emissions or carbon intensity are not answerable.
- **Weather normalization: out of scope for v1.** Demand growth and comparisons are not weather-adjusted. Named as documented future work.
- **Anything requiring raw SQL over source tables**, prices/LMP data, FERC Form 1, BAs outside PJM/ERCO/CISO, or data before 2019-01-01 (the marts start there for demand and generation alike). Not exposed through the views, therefore not answerable.
