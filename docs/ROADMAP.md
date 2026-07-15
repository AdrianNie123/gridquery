# ROADMAP.md — GridQuery

The full phase map for the project. Individual phase plans live in `docs/plans/`. This file is the durable overview; check it to see where the project stands and what comes next. Read `CLAUDE.md` and `PRD.md` for standing rules and full spec.

## Phase overview

| Phase | Name | Status | Weight/risk |
|---|---|---|---|
| 1 | Data landing & verification | ✅ Complete (gate passed) | Light, but foundation-critical |
| 2 | dbt staging & marts + tests | ✅ Complete (gate passed 2026-07-13) | Medium (mechanical) |
| 3 | Cube semantic layer | ✅ Complete (gate passed 2026-07-14) | **Heavy — core of project** |
| 4 | Natural-language interface | ✅ Complete (gate passed 2026-07-15) | Medium-heavy |
| 5 | Evaluation harness | In progress (plan approved 2026-07-15, `docs/plans/phase5.md`) | **Heavy — the differentiator** |
| 6 | Streamlit front end | In progress (delegated build, `docs/plans/phase6.md`) | Light-medium |
| 7 (stretch) | Dagster orchestration | Optional, week 3 | Polish, not load-bearing |

The phases are not equal. Phases 3 and 5 carry most of the intellectual work and most of the timeline risk. The scope-control rule in `PRD.md` §12 watches those two: if semantic layer + eval harness exceed ~40% of total time by end of week 2, cut the free-form NL interface to parameterized queries and keep everything else. Phases can be split at a gate if they prove harder than expected; the count is not sacred, the gates are.

## Locked decisions (confirmed at Phase 1 gate)
- **BA set:** PJM, ERCO, CISO (locked; do not add a fourth).
- **Start year:** 2019 for anything using fuel mix (fuel data begins 2018-07-01); demand-only usable back to 2016. Core window 2019–2025.
- **Demand basis:** PUDL-imputed demand series, never raw reported. Raw contains sentinel garbage (PJM Oct 2021 ~2.1B MWh). Carry the imputation-code column through so imputed hours are surfaced (integrity rule 3).
- **Fuel series break (2024-07-01):** EIA-930 recategorized fuels mid-2024 (legacy `hydro`/`solar`/`wind` → `hydro_excluding_pumped_storage`, `solar_wo_integrated_battery_storage`, etc.). Approved approach: validity-windowed mapping table unifying each pair into one series, **conditional on first quantifying the discontinuity at the boundary.** If pre/post values are not level-continuous, define the unified series AND carry a break flag; document that any metric spanning 2024-07-01 is affected. Do not paper over a real jump as continuity.
- **ERCOT fossil share:** coal + natural gas. Petroleum is **absent from ERCOT reporting**, not zero — document the absence explicitly per BA; do not silently drop it.
- **Mix denominator:** gross generation excluding storage charge/discharge. All storage categories (`battery_storage`, `pumped_storage`, `*_energy_storage`) are excluded from the denominator and from every named bucket. `other` and `unknown` stay in the denominator but belong to no named bucket.
- **Geothermal:** counts in the renewable and carbon-free numerators when present, and in the denominator. CISO-only, first data 2025-12-16, so negligible in the core window. This amends the PRD §6.2 renewable definition per the Phase 1 gate decision.
- **Generation basis:** `net_generation_adjusted_mwh` (EIA's cleaned series), never raw reported. Evidence from the landed data: adjusted never drops a reported value, fills 168–1,552 gaps per BA, differs from reported in only 0–476 rows per BA. No PUDL-imputed series exists for generation. Carry `is_imputed_eia` (EIA-imputed hours) so imputation status stays surfaced (integrity rule 3), and keep `net_generation_reported_mwh` for transparency. (Locked at Phase 2 plan approval, 2026-07-09.)
- **Metric definitions (from `PRD.md`):** growth = total-annual YoY + window CAGR; renewable = wind/solar/hydro, plus geothermal when present (Phase 1 gate amendment; negligible in-window); carbon-free = renewable + nuclear (separate metric); fossil = coal/gas/petroleum. Weather-normalization is out of scope for v1, named as future work.
- **Carbon-intensity proxy: deferred to future work.** PRD §11 open decision 5 resolved at Phase 3 planning (2026-07-13). Not built in v1; named in the README limitations/future-work section. Can be added later as one more governed metric with cited emission factors.
- **Cube runtime: Docker, pinned image.** `cubejs/cube` at a pinned stable tag via docker-compose in `semantic/`. Chosen over Node/npx for reproducibility from a clean checkout. (Locked at Phase 3 planning, 2026-07-13.)

## Locked decisions (Phase 4 planning, 2026-07-14)
- **NL model: `claude-haiku-4-5`** via the Anthropic API. The task is constrained metric selection over a governed catalog, not open-ended generation. Misinterpretation rate is measured honestly by the Phase 5 eval harness; the model choice is revisited only with that data.
- **Prompt caching from v1.** The static prefix (grounding rules + metric catalog + `/v1/meta` snapshot) carries a `cache_control` breakpoint; the volatile question comes after it. The prefix is byte-stable (deterministic serialization, no timestamps) and its size is verified against Haiku 4.5's 4096-token cacheable minimum via `count_tokens`.
- **Phase 5 eval harness uses the Message Batches API** (50% price, results keyed by `custom_id`). Recorded now so the harness is designed for it from the start.
- **Key handling: `.env`, local-only.** `ANTHROPIC_API_KEY` lives in a gitignored `.env` with a spend cap set in the Anthropic console. Nothing key-related is committed; the app runs locally only.
- **Deterministic answer rendering.** Code formats answers from Cube result rows; the LLM selects and parameterizes governed metrics but never produces or restates numbers (integrity rule 1). Every answer displays the metric and parameters used (PRD §9 auditability).
- **Single-shot interaction.** Each question yields exactly one typed outcome: query, refuse, or clarify. No multi-turn dialogue in Phase 4; the Phase 6 front end can loop clarifications by re-asking.

## Locked decisions (Phase 5/6 planning, 2026-07-15)
- **Phase 4 gate closed 2026-07-15:** 179 nl tests green (offline + live smoke incl. refusal, clarification, ERCOT anchor, cache-hit assertion), 24 Cube tests green.
- **Execution structure:** Phase 5 is built in the primary session with bounded subagent tasks (scorer test suite, report generator, question-phrasing drafts). Phase 6 is delegated to a parallel worktree agent working from the frozen `ask()` contract (`docs/plans/phase6.md` is self-contained). Each phase gets its own human gate review.
- **Golden set integrity split:** the hand-authored `eval/golden_set.yaml` contains questions and expected plans but no numbers; every expected numeric value lives in `eval/golden_results.json`, produced only by executing the hand-authored golden plans against the tested Cube layer (`make eval-pin`). Integrity rule 1 enforced structurally. Regeneration policy: a pin diff without a corresponding data change is a stop-and-investigate event.
- **Scoring semantics:** exact plan match rejected (equivalent plans exist). Three deterministic checks per query question: outcome kind, metric selection with period canonicalization, result match through the real validator + executor. Numeric tolerance `rel_tol=1e-6` (same engine, same data); never loosened without investigation. Refuse/clarify score on outcome kind only; no LLM-as-judge in v1.
- **Composition:** 35 query (all 11 metrics covered) / 10 refuse / 5 clarify.
- **Eval artifact contract:** `eval/results/latest.json` (committed at the gate) is the single artifact consumed by `docs/eval_report.md` and the Streamlit eval page; it records actual batch token usage and cost, never assumed rates.
- **Front end:** Streamlit app in `app/` with NL page, demand-growth leaderboard, generation-mix breakdown (all numbers through the governed layer), plus an eval-results page rendering `latest.json` with graceful degradation. New deps approved: `pyyaml`, `streamlit`.

## Outstanding verification task (carry into Phase 2)
- **Second plausibility anchor: DONE** — recorded in `docs/verification_anchors.md`. CISO 2023 peak demand: mart 44,007 MWh hourly vs CAISO-published 44,534 MW instantaneous (-1.18%, documented hourly-vs-instantaneous definitional difference; peak-demand form substituted because CAISO publishes no annual energy total). ERCOT annual anchor restated there; PJM ~800,000 GWh forecast baseline noted as weak corroboration.

---

## Phase 2: dbt staging & marts + tests

**Objective:** turn the landed, verified EIA-930 data in DuckDB into clean, tested, well-modeled analytical tables (marts) that the Phase 3 semantic layer will sit on. No metrics logic beyond what belongs in marts; no Cube yet.

**Structure (standard dbt layering):**
- **Staging models:** one-to-one with source tables, light cleaning only — rename columns to consistent names, cast types, apply the demand-basis decision (select PUDL-imputed demand, carry imputation-code), filter to the locked BA set and window. No business logic here.
- **Intermediate models (as needed):** apply the fuel series-break mapping table (validity-windowed), and the storage/geothermal/other denominator handling. This is where the Phase 1 decisions get encoded, once, in a documented place.
- **Marts:** the analysis-ready tables the semantic layer queries — e.g., hourly demand by BA, generation by fuel by BA (with unified fuel categories + break flag), and whatever daily/annual grains the metrics need. Keep marts clean and well-named; the metric math itself lives in Cube (Phase 3), not baked into marts, so marts stay reusable.

**Tests (non-negotiable — integrity core, never cut):**
- Not-null and accepted-range tests on demand (guard against the sentinel garbage class of error).
- Uniqueness on the grain (BA + hour) — Phase 1 confirmed zero duplicates; a test enforces it stays true.
- Accepted-values test on fuel categories after the break mapping, so an unmapped/surprise category fails loudly.
- Relationship/consistency tests where marts join.
- A test or documented check that the fuel series-break flag is set correctly around 2024-07-01.

Accepted-range bounds are derived from the landed data envelope and documented with their basis (PUDL release, observed min/max, date). Policy: a failing range test is a stop-and-investigate event first, never a prompt to widen bounds. Bounds change only when a new landing changes the envelope, and the change must cite the re-run profile output (`make profile`) in the commit that adjusts them.

**Delegation (Phase 2 has real bounded parallel work):**
- Good subagent task: **writing the dbt test suite** once the model structure is agreed — bounded, verifiable, doesn't need whole-architecture context.
- Good subagent task: **generating model documentation / schema.yml descriptions** from the agreed models.
- Keep in primary session: the staging→intermediate→mart structure design and the encoding of the series-break and denominator decisions, since those require holding the Phase 1 findings in mind.

**Done conditions:**
- Marts build from a single command on top of the Phase 1 DuckDB.
- All dbt tests pass.
- The series-break mapping and denominator decisions are encoded once, in documented intermediate models.
- The second plausibility anchor is reproduced and recorded.
- Human has reviewed marts + test results before Phase 3 begins.

**Stop-and-ask triggers:**
- The fuel series-break discontinuity turns out large enough that unifying into one series is misleading (then escalate the bridging decision before encoding it).
- Any test reveals a data-quality issue not caught in Phase 1.
- The second plausibility anchor is materially off from the public figure.
