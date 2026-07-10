-- Enforces that source_regime in int_generation__fuel_mapped matches the governed regime in seed fuel_category_mapping for each source label.

select
    i.ba_code,
    i.datetime_utc,
    i.source_label,
    i.source_regime as model_source_regime,
    m.source_regime as seed_source_regime
from {{ ref('int_generation__fuel_mapped') }} i
join {{ ref('fuel_category_mapping') }} m
    on i.source_label = m.source_label
where i.source_regime is distinct from m.source_regime
