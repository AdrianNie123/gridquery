-- Generation staging. Encodes the locked generation basis (docs/ROADMAP.md):
--   value = EIA-adjusted series (never drops a reported value, fills gaps);
--   is_imputed_eia marks hours where EIA imputed (integrity rule 3);
--   reported kept for transparency.
-- Same naive-UTC timestamp normalization as demand staging.

select
    balancing_authority_code_eia as ba_code,
    timezone('UTC', datetime_utc) as datetime_utc,
    generation_energy_source as source_label,
    net_generation_adjusted_mwh as net_generation_mwh,
    net_generation_reported_mwh,
    net_generation_imputed_eia_mwh is not null as is_imputed_eia
from {{ source('landing', 'core_eia930__hourly_net_generation_by_energy_source') }}
where balancing_authority_code_eia in ('PJM', 'ERCO', 'CISO')
