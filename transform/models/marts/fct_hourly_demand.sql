-- Hourly demand fact. Grain: ba_code x datetime_utc (naive UTC hour).
-- Window >= 2019-01-01 UTC: locked start year (docs/ROADMAP.md); earlier
-- demand exists in landing but is outside the governed window.
-- demand_mwh is the PUDL-imputed series (locked basis); is_imputed and
-- imputation_code surface exactly which hours were imputed and why.

select
    ba_code,
    datetime_utc,
    demand_mwh,
    is_imputed,
    imputation_code,
    demand_reported_mwh
from {{ ref('stg_eia930__hourly_demand') }}
where datetime_utc >= timestamp '2019-01-01'
