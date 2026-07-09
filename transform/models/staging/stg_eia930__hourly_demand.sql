-- Demand staging. Encodes two locked decisions (docs/ROADMAP.md):
--   demand basis = PUDL-imputed series (raw reported contains sentinel
--   garbage, e.g. PJM 2021-10-19 ~2.1e9 MWh), imputation code carried
--   so imputed hours stay identifiable (integrity rule 3);
--   BA set = PJM / ERCO / CISO.
-- datetime_utc is cast from TIMESTAMPTZ (dlt landing artifact) to a naive
-- UTC timestamp so downstream grouping is immune to session timezone.

select
    balancing_authority_code_eia as ba_code,
    timezone('UTC', datetime_utc) as datetime_utc,
    demand_imputed_pudl_mwh as demand_mwh,
    demand_reported_mwh,
    demand_imputed_pudl_mwh_imputation_code as imputation_code,
    demand_imputed_pudl_mwh_imputation_code is not null as is_imputed
from {{ source('landing', 'out_eia930__hourly_operations') }}
where balancing_authority_code_eia in ('PJM', 'ERCO', 'CISO')
