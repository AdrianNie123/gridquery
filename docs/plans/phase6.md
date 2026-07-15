# plan.md - Phase 6: Streamlit front end (delegable spec)

## Context

GridQuery answers grid-demand questions through governed Cube metrics. This phase builds the Streamlit front end (PRD section 9) against a **frozen contract**: the builder may not modify anything under `nl/`, `eval/`, `semantic/`, or `transform/`. Read `CLAUDE.md`, `PRD.md` sections 7 and 9, `docs/nl_interface.md`, and `docs/metric_catalog.md` before building.

Non-negotiables that bind the UI:
- Every number shown comes from Cube result rows or the eval artifact (integrity rule 1). No placeholder or illustrative numbers anywhere, including empty states.
- Every answer displays the governed metric and parameters used (PRD section 9 auditability - never cut).
- Refusal and clarification are features to render respectfully, not errors.

## The frozen contract

- `nl.interface.ask(question: str, views: dict | None = None, client=None) -> Answer`. `Answer` fields: `kind` (`"answer" | "refusal" | "clarification"`), `text` (fully rendered incl. metric, parameters, caveats), `metric`, `plan` (`nl.schema.QueryPlan`), `rows` (list of dicts keyed by fully qualified member, e.g. `"demand.ba_code"`), `usage` (token/cache counters).
- `nl.catalog.fetch_meta()` / `nl.catalog.governed_views(meta)` for the meta snapshot; pass the snapshot into `ask(question, views=...)` to reuse it across questions.
- `nl.validator.validate_plan(plan, views) -> list[str]` (empty = valid); `nl.executor.execute_plan(plan) -> rows`.
- Eval artifact: `eval/results/latest.json`, produced by the Phase 5 harness. Schema: top-level `run_id`, `git_commit`, `model`, `batch_id`, content hashes, `counts` (total/query/refuse/clarify), `aggregate` (overall_accuracy, metric_selection_accuracy, result_accuracy, refusal_accuracy, clarify_accuracy), `failure_modes` (wrong_metric, wrong_parameter, wrong_period, refusal_should_have_answered, answered_should_have_refused, clarified_should_have_answered, answered_should_have_clarified), `usage` (token counters + estimated_cost_usd + pricing_basis), and `questions` (per-question: id, question, expected_kind, expected_metric, actual_kind, actual_metric, actual_plan, checks booleans, pass, failure_mode, usage). The artifact may not exist while building - the eval page must degrade gracefully.

## Files to build

```
app/                    # not streamlit/ - that would shadow the package import
  Home.py               # NL query page
  governed.py           # hardcoded governed QueryPlans for pre-built views + shared cache helpers
  pages/
    1_Demand_Growth_Leaderboard.py
    2_Generation_Mix.py
    3_Eval_Results.py
```

Plus: `streamlit` added via `uv add streamlit` (approved dependency); Makefile target `app: uv run streamlit run app/Home.py`; a short `docs/frontend.md`. Keep Makefile and pyproject edits additive and isolated (Phase 5 edits both files in parallel).

## Home.py (NL query page)

Text input -> `ask(question, views=cached_views, client=cached_client)`. Cache the Anthropic client with `@st.cache_resource` and the meta snapshot with `@st.cache_data(ttl=3600)` (one `/v1/meta` fetch per session, with a manual "refresh governed surface" button). Render by `Answer.kind`:

- `answer`: metric name prominently, the parameters line, `st.dataframe(rows)` with humanized column names, caveat notes, and an expander with the exact `QueryPlan` JSON and usage counters. Display formatting only; never re-derive values.
- `refusal`: the reason, framed as by-design ("refusal is a feature"), with a pointer to what is governed (`docs/metric_catalog.md` surface).
- `clarification`: show the clarifying question and keep the input populated via `st.session_state` so the user re-asks with more detail. This is the single-shot loop the Phase 4 contract anticipated; do not build multi-turn dialogue.
- Cube down / missing key: catch and show actionable setup instructions (`make cube-up`, `.env` with `ANTHROPIC_API_KEY`), never a stack trace, never fake data.

## governed.py + pre-built views

Hardcoded `QueryPlan` objects built from `nl.schema`, each passed through `nl.validator.validate_plan` at page load (fail loudly on violations - this proves the pre-built views sit on the governed surface) and executed via `nl.executor.execute_plan`. No SQL, no DuckDB import, no `duckdb` anywhere in `app/`.

- **Demand-growth leaderboard:** `demand_growth` view - `demand_growth.demand_yoy_growth` by `demand_growth.ba_code` with a year selector restricted to complete years (2020-2025; 2026 is partial and returns null by design - show the null and say why, do not hide it), plus `demand_growth.demand_cagr` per BA over the complete-year window. State the complete-years caveat on the page.
- **Generation mix:** `generation_mix` view - the named share measures (`renewable_share`, `fossil_share`, `carbon_free_share`, per-fuel shares) by BA and selected year. Never compute a share by filtering `unified_fuel_category`. Surface the standing caveats where the slice warrants: the 2024-07-01 series break for spanning windows; null means the BA does not report that fuel (absence, not zero - ERCO reports no petroleum). Charts: Streamlit built-ins (`st.bar_chart` / `st.dataframe`); clarity over decoration.

## Eval results page

Load `eval/results/latest.json`. If absent or unparsable: one calm sentence ("No eval run artifact found - run `make eval` (Phase 5).") and nothing else - no placeholder metrics. If present: run metadata (run_id, git commit, model), overall + per-check-type accuracies, failure-mode breakdown as a table or bar chart, per-question detail in an expandable dataframe (question, expected vs actual, failure mode), and the usage/cost block. Render exactly what the artifact says.

## Verification (phase done conditions)

- `make cube-up && make app` works from a clean checkout with `.env`.
- The anchor question ("Which balancing authority had the highest total demand in 2023?") through the UI shows the pipeline number with metric + parameters visible.
- A carbon-intensity question shows a refusal; an ambiguous question shows a clarification and the re-ask loop works.
- Both pre-built pages show only Cube-produced numbers and their plans pass the validator at load.
- The eval page degrades gracefully with no artifact and renders a fixture artifact matching the schema above.
- `rg -n "duckdb|SELECT " app/` comes back empty.
- Existing `make nl-test` untouched and green.

## Stop-and-ask triggers

- Anything requiring a change to `ask()`, `Answer`, `QueryPlan`, or the artifact schema (contract change).
- Any need to query DuckDB or Cube endpoints other than `/v1/meta` and `/v1/load`.
- Any UI element that would display a number not produced by the pipeline.
- A Makefile or pyproject conflict with mainline that cannot be kept additive.

## Merge plan

Built in a worktree touching only `app/`, one Makefile target, the `streamlit` dep, and `docs/frontend.md`. Launched after Phase 5's artifact-schema commit lands so the eval page codes against the real schema. Merged after its own human gate review.
