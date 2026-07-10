-- Enforces the locked decision that petroleum (oil) is absent from ERCOT reporting: if ERCO ever reports oil, fail loudly so the decision is revisited.

select
    ba_code,
    datetime_utc,
    unified_fuel_category,
    net_generation_mwh
from {{ ref('fct_hourly_generation') }}
where ba_code = 'ERCO'
  and unified_fuel_category = 'oil'
