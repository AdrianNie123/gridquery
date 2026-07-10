-- Enforces that every (ba_code, datetime_utc) pair in fct_hourly_generation has a matching hour in fct_hourly_demand.

select distinct
    g.ba_code,
    g.datetime_utc
from {{ ref('fct_hourly_generation') }} g
left join {{ ref('fct_hourly_demand') }} d
    on  g.ba_code = d.ba_code
    and g.datetime_utc = d.datetime_utc
where d.ba_code is null
