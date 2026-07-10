-- Enforces that classification flags in seed fuel_category_mapping are uniform across all source labels within each unified_fuel_category.

select
    unified_fuel_category
from {{ ref('fuel_category_mapping') }}
group by unified_fuel_category
having count(distinct is_storage) > 1
    or count(distinct in_mix_denominator) > 1
    or count(distinct is_renewable) > 1
    or count(distinct is_fossil) > 1
    or count(distinct is_carbon_free) > 1
