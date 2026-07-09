-- One row per unified fuel category, with the governed classification flags
-- and the source labels that feed it. Flags are uniform within a category by
-- construction of the seed; a singular test asserts that stays true.

select
    unified_fuel_category,
    bool_or(is_storage) as is_storage,
    bool_or(in_mix_denominator) as in_mix_denominator,
    bool_or(is_renewable) as is_renewable,
    bool_or(is_fossil) as is_fossil,
    bool_or(is_carbon_free) as is_carbon_free,
    string_agg(source_label, ', ' order by source_label) as source_labels
from {{ ref('fuel_category_mapping') }}
group by unified_fuel_category
