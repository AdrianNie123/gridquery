# plan.md - Phase 4: Natural-language interface

## Context

Phases 1-3 are complete: landed EIA-930 data, tested dbt marts (47/47), and the Cube semantic layer with 11 governed metrics across three views (`demand`, `demand_growth`, `generation_mix`), a 24-test suite, and `docs/metric_catalog.md`. Phase 4 (PRD section 7) adds the natural-language layer: an LLM that translates a question into a query against the governed Cube views only, or refuses/clarifies. The LLM is a thin translation layer; trustworthiness comes from the grounding contract (Cube `/v1/meta` for the three views is the entire surface the LLM sees) and a deterministic validator that enforces it in code. Phase 5's eval harness and Phase 6's Streamlit front end both consume the module built here.

## Decisions locked at Phase 4 planning (2026-07-14, recorded in `docs/ROADMAP.md`)

- **NL model: `claude-haiku-4-5`** via the Anthropic API. Constrained metric selection, not open-ended generation. Misinterpretation is measured by the Phase 5 eval; the model choice is revisited only with that data.
- **Prompt caching from v1.** The static prefix (grounding rules + metric catalog + `/v1/meta` snapshot) carries `cache_control: {type: ephemeral}`; the volatile question comes after. Haiku 4.5's minimum cacheable prefix is 4096 tokens, so the build verifies the assembled prefix with `count_tokens` and confirms `cache_read_input_tokens > 0` on a second call. Prefix is byte-stable: deterministic serialization, no timestamps.
- **Phase 5 eval harness uses the Message Batches API** (50% price, results keyed by `custom_id`). Recorded now so the harness is designed for it from the start.
- **Key handling: `.env`, local-only.** `ANTHROPIC_API_KEY` in a gitignored `.env`, spend cap set in the Anthropic console. Nothing key-related is committed.
- **Deterministic answer rendering.** Code formats the answer from Cube's result rows; the LLM selects and parameterizes metrics but never touches numbers (integrity rule 1). Every answer displays the governed metric and parameters used (PRD section 9 auditability).
- **Single-shot interaction.** Each question produces exactly one typed outcome: query, refuse, or clarify. No multi-turn dialogue in Phase 4; Phase 6 can loop clarifications by re-asking.

## New dependencies (approved with this plan, per CLAUDE.md)

- `anthropic` (Python SDK) - runtime dep.
- `pydantic` - declared explicitly since `nl/schema.py` imports it directly (it ships as a dependency of the anthropic SDK).
- `python-dotenv` - loads `.env`.
- No other new tools. Streamlit stays in Phase 6.

## Structure

New top-level `nl/` package:

- `nl/catalog.py` - fetches `/v1/meta` from the running Cube, filters to the three governed views, and assembles the stable system prompt: grounding rules, the metric catalog (`docs/metric_catalog.md` embedded), member list with types, allowed dimension values (`ba_code` in PJM/ERCO/CISO, year bounds, complete-year rule), and the refusal policy (carbon intensity, weather normalization, prices, out-of-scope BAs and dates are named non-answerable).
- `nl/schema.py` - Pydantic models for the structured outcome: `QueryPlan` (view, measures, dimensions, filters, time dimension + granularity + date range, order, limit) | `Refusal(reason)` | `Clarification(question)`.
- `nl/planner.py` - the one LLM call: `claude-haiku-4-5`, structured outputs (`client.messages.parse` with the outcome schema), `cache_control` on the last system block. No agentic loop, no tools.
- `nl/validator.py` - deterministic guardrail, the code-level enforcement of integrity rule 4: every member in a `QueryPlan` must exist in the governed `/v1/meta` views; filter values checked against allowed sets; anything unknown converts the plan to a `Refusal`, never silently repaired.
- `nl/executor.py` - POSTs the validated plan to `/cubejs-api/v1/load`; surfaces Cube errors as errors.
- `nl/answer.py` - deterministic rendering: numbers straight from Cube rows, plus the metric name and parameters used, plus caveat lines pulled from the catalog where the slice warrants them (imputation share, 2024-07-01 series break, ERCO petroleum absence, partial-2026 nulls).
- `nl/__main__.py` - CLI: `uv run python -m nl "question"`. Makefile target `make ask Q="..."`.
- `nl/tests/` - pytest, mirroring `semantic/tests/` conventions.
- `.env.example` committed; `.env` gitignored.

Data flow: question -> planner (LLM, cached prefix) -> validator (deterministic) -> executor (Cube REST) -> answer renderer. Refuse/clarify outcomes exit after the planner or validator.

**Scope-control alignment (PRD section 12):** the `QueryPlan` schema + validator + executor + renderer are exactly the parameterized-query fallback. If the free-form NL interface must be cut at the end of week 2, only `planner.py` is replaced by a fixed question-to-plan mapping; everything else survives.

## Tests

- **Offline (no API key needed):** validator accepts every metric in the catalog expressed as a valid plan; rejects non-governed members, private cube references, bad BA codes, malformed filters. Planner outcome parsing tested against mocked API responses.
- **Live smoke (skipped when `ANTHROPIC_API_KEY` unset):** 4-6 questions through the full stack against running Cube: one per view, one that must refuse (carbon intensity), one that must clarify (ambiguous region), one anchor check (ERCOT 2023 total = 446.79 TWh through the NL path). Asserts `cache_read_input_tokens > 0` on the second call.
- The ~50-question golden set is Phase 5, not built here.

## Execution order

0. Close the Phase 3 gate: re-run cube tests, commit the `annual_demand.yml` complete-year fix, update ROADMAP. (Done: commit 4ccee3f.)
1. Materialize this plan as `docs/plans/phase4.md`. Scaffold `nl/`, add deps via uv, `.env.example`, `.gitignore` entry. Commit.
2. Build `catalog.py`, `schema.py`, `validator.py` with offline tests green. Verify prefix >= 4096 tokens via `count_tokens`. Commit.
3. Build `planner.py`, `executor.py`, `answer.py`, CLI + Makefile target. Manual spot checks against running Cube, confirm cache hit. Commit.
4. Delegation checkpoint (pause for go-ahead): subagent task - expand the offline validator/refusal test suite from the spec; subagent task - docs write-up of the NL interface contract (grounding, refusal taxonomy, cost design: Haiku + caching + Batch API) for the README later.
5. Full verification pass. Commit. Stop for phase-gate review.

## Verification (phase done conditions)

- `make ask Q="Which balancing authority had the highest total demand in 2023?"` returns the pipeline-produced number with the governed metric and parameters displayed.
- A carbon-intensity question refuses, citing that the metric is not governed; an ambiguous question returns a clarification.
- Both anchors reproduce through the NL path.
- Offline tests green with no API key; live smoke green with one; second identical call shows `cache_read_input_tokens > 0`.
- The only Cube surface touched is `/v1/meta` and `/v1/load` on the three governed views; no SQL anywhere in `nl/`.
- ROADMAP updated; `.env` never committed.

## Stop-and-ask triggers

- A question type the QueryPlan schema structurally cannot express (schema change is a contract change with Phase 5).
- Haiku smoke-check misinterpretation so severe the phase gate would be meaningless (bring data, propose model escalation).
- The assembled prefix cannot reach 4096 tokens without artificial padding (decide: accept no caching vs restructure prompt).
- Anything forcing the LLM toward raw SQL or an ungoverned surface.
