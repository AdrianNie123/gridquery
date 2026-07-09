-- The fuel series-break and denominator decisions, encoded once.
--
-- EIA-930 recategorized fuels on 2024-07-01: legacy hydro/solar/wind labels
-- end there and are replaced by hydro_excluding_pumped_storage and the
-- *_wo_integrated_battery_storage labels. The seed fuel_category_mapping
-- unifies each pair into one unified_fuel_category; source_regime (from the
-- source label itself, no date arithmetic) is the break signal every row
-- carries. Quantification of the discontinuity: docs/phase1_data_profile.md
-- s10 - no detectable level break for wind/solar/PJM hydro, immaterial for
-- ERCO hydro (0.12% of its generation), ambiguous for CISO hydro (10.5%,
-- hydrology vs definitional narrowing). Any metric spanning 2024-07-01 is
-- affected and must say so (enforced downstream in the metric catalog).
--
-- in_mix_denominator encodes the denominator decision: gross generation
-- excluding storage charge/discharge. Storage categories carry false;
-- other/unknown stay true but belong to no named bucket.
--
-- Left join by design: a source label missing from the seed produces null
-- unified_fuel_category, which downstream not_null / accepted_values tests
-- turn into a loud failure instead of silently dropped rows.

select
    g.ba_code,
    g.datetime_utc,
    m.unified_fuel_category,
    m.source_regime,
    g.source_label,
    g.net_generation_mwh,
    g.net_generation_reported_mwh,
    g.is_imputed_eia,
    m.is_storage,
    m.in_mix_denominator,
    m.is_renewable,
    m.is_fossil,
    m.is_carbon_free
from {{ ref('stg_eia930__hourly_generation') }} g
left join {{ ref('fuel_category_mapping') }} m
    on g.source_label = m.source_label
