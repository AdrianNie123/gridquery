-- Enforces seam coverage across the 2024-07-01 fuel-label break: every BA x hydro/solar/wind must have at least one generation row in the 48h before 2024-07-01 00:00 and in the 48h after 2024-07-02 00:00.

with expected as (

    select ba.ba_code, fc.unified_fuel_category, sd.side
    from (values ('PJM'), ('ERCO'), ('CISO')) as ba (ba_code)
    cross join (values ('hydro'), ('solar'), ('wind')) as fc (unified_fuel_category)
    cross join (values ('before_break'), ('after_break')) as sd (side)

),

observed as (

    select distinct
        ba_code,
        unified_fuel_category,
        case
            when datetime_utc >= timestamp '2024-06-29 00:00:00'
             and datetime_utc <  timestamp '2024-07-01 00:00:00'
                then 'before_break'
            else 'after_break'
        end as side
    from {{ ref('fct_hourly_generation') }}
    where ba_code in ('PJM', 'ERCO', 'CISO')
      and unified_fuel_category in ('hydro', 'solar', 'wind')
      and (
            (datetime_utc >= timestamp '2024-06-29 00:00:00' and datetime_utc < timestamp '2024-07-01 00:00:00')
         or (datetime_utc >= timestamp '2024-07-02 00:00:00' and datetime_utc < timestamp '2024-07-04 00:00:00')
      )

)

select
    e.ba_code,
    e.unified_fuel_category,
    e.side
from expected e
left join observed o
    on  e.ba_code = o.ba_code
    and e.unified_fuel_category = o.unified_fuel_category
    and e.side = o.side
where o.ba_code is null
