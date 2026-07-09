# plan.md — Phase 1: Data Landing & Verification

**Read `CLAUDE.md` and `PRD.md` before acting on this plan.**

This is the first build phase. It is primarily a **verification phase, not a coding phase.** The goal is to land the target data and then confirm the real schema against the actual data before any modeling. Do not proceed to dbt models (Phase 2) until the verification deliverable in §5 exists and the human has reviewed it. Baking an assumed schema or fuel mapping into downstream models is the failure mode this phase exists to prevent.

## 1. Objective
Pull the bounded EIA-930 subset from PUDL into DuckDB, profile it, and produce a written record of the actual schema, categories, coverage, and data-quality facts that downstream phases depend on. Assume nothing about column names, fuel labels, or BA codes from memory — confirm everything against the landed data.

## 2. Scope for this phase
- **Datasets:** EIA-930 hourly data via PUDL (analysis-ready Parquet). Demand, net generation by fuel, by balancing authority.
- **Balancing authorities:** PJM, ERCOT, CISO (California). Optionally one contrast/baseline region if easy. Confirm the exact BA codes PUDL/EIA-930 uses; do not assume.
- **Time window:** target calendar years ~2019–2024. Confirm the usable start year by inspecting data quality, not by assumption.
- **Out of scope this phase:** any dbt models, any metrics, any Cube setup, any LLM wiring, any front end. Landing and profiling only.

## 3. Tasks (use plan mode; propose before building)
1. **Set up the environment:** DuckDB, dlt, and profiling tooling (a notebook or a Python script). No dbt or Cube yet.
2. **Land the data:** use dlt to pull the EIA-930 subset from PUDL's documented Parquet distribution into local Parquet, then load into a DuckDB database. If a direct Parquet load is simpler than a full dlt source for static files, propose that tradeoff rather than over-engineering — but keep the refresh reproducible.
3. **Profile the landed data** and record findings (see §4).
4. **Write the verification note** (see §5).

## 4. Verification checklist (the real point of this phase)
Confirm and record each of these against the actual landed data:
- [ ] **Exact balancing-authority codes** for PJM, ERCOT, CISO as they appear in the data. Note any surprises (sub-regions, renamed codes, aggregation).
- [ ] **Exact fuel-category labels** used in EIA-930 net-generation-by-fuel. This directly determines the renewable / carbon-free / fossil buckets defined in `PRD.md` §6.2. List every fuel category present.
- [ ] **Mapping check:** confirm that wind, solar, hydro, nuclear, coal, natural gas, and petroleum each map cleanly to a category present in the data. Flag any that are ambiguous, missing, or bundled (e.g., "other," "unknown," combined categories). If hydro or nuclear are not clean, flag for the human — `PRD.md` §4 anticipates adjusting.
- [ ] **Imputation flags:** identify which columns indicate imputed vs. reported values. Record how imputation is signaled. This is required for integrity rule 3.
- [ ] **Coverage / gaps:** for each BA, check completeness by year. Identify the earliest year where data quality is acceptable. Record any large gaps.
- [ ] **Grain confirmation:** confirm the data is hourly and confirm the timestamp/timezone handling (UTC vs. local). Note anything that will affect period aggregation.
- [ ] **Row counts and basic sanity:** record row counts per BA per year and eyeball demand ranges for obvious anomalies (negatives, impossible spikes).

## 5. Deliverable
A short **`docs/phase1_data_profile.md`** (plus the profiling script/notebook) that records every item in §4 with the actual values found. This is a factual record, not analysis. It must contain no invented numbers — everything comes from the landed data. This document unblocks the final confirmation of the fuel-category definitions and the BA/time-window scope.

## 6. Done conditions
- Data for the target BAs and window is landed in DuckDB and reloadable via a single documented command.
- `docs/phase1_data_profile.md` exists and covers every §4 item.
- The human has reviewed it and confirmed: final BA set, final fuel-category mapping, and final start year.
- Only then does Phase 2 (dbt staging + marts + tests) begin.

## 7. Explicit stop-and-ask triggers
Stop and ask the human if:
- The PUDL EIA-930 distribution's structure differs materially from what `PRD.md` assumes.
- A core fuel category (especially hydro or nuclear) is ambiguous or bundled in a way that affects the renewable/carbon-free definitions.
- Data quality for a target BA is poor enough that the BA or the start year should change.
- The imputation signal cannot be clearly identified (this blocks integrity rule 3).
