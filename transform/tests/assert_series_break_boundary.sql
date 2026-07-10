-- Enforces the 2024-07-01 series break: legacy fuel labels carry no values after 2024-07-02, post-break labels carry none before 2024-06-30.

select
    ba_code,
    datetime_utc,
    source_label,
    source_regime,
    net_generation_mwh
from {{ ref('int_generation__fuel_mapped') }}
where source_regime = 'legacy'
  and net_generation_mwh is not null
  and datetime_utc > timestamp '2024-07-02'

union all

select
    ba_code,
    datetime_utc,
    source_label,
    source_regime,
    net_generation_mwh
from {{ ref('int_generation__fuel_mapped') }}
where source_regime = 'post_2024_break'
  and net_generation_mwh is not null
  and datetime_utc < timestamp '2024-06-30'
