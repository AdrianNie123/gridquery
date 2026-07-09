-- Hourly generation fact. Grain: ba_code x datetime_utc x unified_fuel_category.
-- Window >= 2019-01-01 UTC (locked start year). Rows exist only where the
-- adjusted generation value is non-null: the landing spine carries every
-- label for every hour, but a label outside its reporting regime (or absent
-- for a BA, e.g. oil for ERCO) has no value and no row here.
-- source_regime is the 2024-07-01 series-break signal; flags come from the
-- governed seed via int_generation__fuel_mapped.

select
    ba_code,
    datetime_utc,
    unified_fuel_category,
    net_generation_mwh,
    source_regime,
    is_storage,
    in_mix_denominator,
    is_renewable,
    is_fossil,
    is_carbon_free,
    is_imputed_eia
from {{ ref('int_generation__fuel_mapped') }}
where datetime_utc >= timestamp '2019-01-01'
  and net_generation_mwh is not null
