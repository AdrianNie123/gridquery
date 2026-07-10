-- Enforces mapping completeness: every distinct source_label observed in staging generation must exist in seed fuel_category_mapping.

select distinct
    s.source_label
from {{ ref('stg_eia930__hourly_generation') }} s
left join {{ ref('fuel_category_mapping') }} m
    on s.source_label = m.source_label
where m.source_label is null
