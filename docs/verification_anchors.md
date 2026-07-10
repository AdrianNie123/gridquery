# Verification anchors

Plausibility anchors comparing pipeline-produced numbers against operator-published
figures. Purpose: catch gross pipeline errors (unit mistakes, double counting,
wrong-column selection). These are plausibility checks against independently
published figures, not validations; EIA-930 BA demand and operator-published
figures are related but not definitionally identical concepts.

Review thresholds (set in `docs/plans/phase2.md` before checking): within ~1% =
pass; 1–5% = investigate and document the definitional difference; >5% or
unexplained = stop and ask.

## Anchor 1 — ERCOT 2023 annual demand (recorded at Phase 1)

- **Pipeline:** sum of `demand_mwh` (PUDL-imputed basis) for ERCO, calendar 2023
  (UTC) = **446.79 TWh**. Computed at Phase 1 from landing
  (`docs/phase1_data_profile.md` §7) and reproduced exactly through
  `marts.fct_hourly_demand` at the Phase 2 model build (commit 96c2cae).
- **Public figure:** ERCOT publicly reported 2023 energy use of approximately
  445–446 TWh (ERCOT public communications, as recorded at Phase 1).
- **Delta:** well under 1%. **Pass.**

## Anchor 2 — CISO 2023 peak demand (recorded at Phase 2)

- **Pipeline:** maximum hourly `demand_mwh` for CISO in calendar 2023 from
  `marts.fct_hourly_demand` = **44,007 MWh**, at hour timestamped
  2023-08-17 02:00 UTC. Surrounding evening hours (UTC): 00:00 = 41,603;
  01:00 = 43,016; 02:00 = 44,007; 03:00 = 43,515.
- **Public figure:** CAISO-published 2023 peak demand of **44,534 MW on
  August 16, 2023 at 5:59 p.m.** Pacific (= 00:59 UTC, August 17).
  Source: CAISO, "2023 Statistics" (caiso.com/documents/2023statistics.pdf),
  retrieved 2026-07-09.
- **Delta:** -527 MW = **-1.18%**, in the investigate-and-document band.
  Documented explanation: the published figure is an instantaneous
  (minute-level) system peak; the pipeline value is an hourly average, which
  is necessarily at or below the instantaneous peak. The pipeline peak falls
  in the same evening ramp as the published peak minute (the hourly series
  rises to its maximum in the hour or two around 5:59 p.m. Pacific, exact
  alignment depending on hour-beginning vs hour-ending labeling). Direction
  and size are consistent with that definitional difference. **Pass with
  documented definitional difference.**
- **Substitution note:** the plan called for a summed-annual-demand
  comparison, but CAISO's statistics publication reports no annual energy
  total, so the operator-published peak is the anchor instead. The annual
  side is covered by Anchor 1 (ERCOT) and the corroboration below.

## Tertiary corroboration — PJM annual energy (weak, labeled as such)

- **Pipeline:** PJM calendar-2023 summed `demand_mwh` = **784.81 TWh**
  (`docs/phase1_data_profile.md` §7; reproduced through the mart).
- **Public figure:** press coverage of PJM's 2024 Long-Term Load Forecast
  cites total annual energy use in the PJM footprint of roughly
  **800,000 GWh** as the current baseline (PJM Inside Lines, "PJM Publishes
  2024 Long-Term Load Forecast").
- **Caveat:** that is a round forecast baseline, not a reported actual, so
  this is corroboration (~2% apart), not an anchor.

## Conclusion

Two independent anchors of different types (annual energy, ERCOT; peak
demand, CISO) both land within their thresholds with documented
explanations. The marts are plausible against operator-published figures.
