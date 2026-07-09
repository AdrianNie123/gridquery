-- Balancing-authority dimension: the locked BA set with reporting quirks
-- recorded as data (ERCO petroleum absence, CISO geothermal start).

select
    ba_code,
    ba_name,
    iana_timezone,
    notes
from {{ ref('balancing_authorities') }}
