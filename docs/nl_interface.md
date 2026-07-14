# NL interface contract - GridQuery Phase 4

This document is the contract for the natural-language query layer: what the LLM sees, what it may return, what code enforces, and where the layer's honesty limits are. It is the source for the README's NL section. The behavior described here is implemented in the `nl/` package; every claim below is traceable to a file.

## What this layer is

The LLM is a thin translation layer. It converts one natural-language question into exactly one structured outcome: a parameterized query against the governed Cube views, a refusal, or a clarification request. It never writes SQL, never touches source tables, and never produces a number. Trust in the layer does not come from the model; it comes from three things stacked in order: a grounding contract that limits what the model can see, deterministic code that enforces what it can do, and an evaluation harness (Phase 5) that measures how often it is right.

The pipeline is `ask()` in `nl/interface.py`:

```
question -> planner (LLM, cached prefix) -> validator (deterministic)
         -> executor (Cube REST) -> answer renderer
```

Refuse and clarify outcomes exit before anything executes. `ask()` is the single entry point; the Phase 5 eval harness and the Phase 6 front end both call it, and it accepts a pre-fetched governed-surface snapshot so the harness can reuse one `/v1/meta` fetch across its whole question set.

## The grounding contract

The model's entire view of the data is assembled deterministically in `nl/catalog.py`:

- Cube's `/v1/meta` is fetched and reduced to the three governed views (`demand`, `demand_growth`, `generation_mix`). Only cubes marked public and in the expected governed set survive, and only their public members. If a governed view is missing from meta, the layer refuses to start rather than run against a wrong model.
- The system prompt is the concatenation of: the grounding rules (`GROUNDING_RULES`), the allowed `ba_code` values (PJM, ERCO, CISO), the data window (2019-01-01 through 2026-05-03, with 2026 a partial year), a sorted listing of every governed member with its type, and `docs/metric_catalog.md` embedded verbatim. The metric definitions live in that catalog and are referenced here, not duplicated.
- All members are fully qualified (`view.member`), matching Cube's REST format, so the plan the model returns uses the same names the validator checks and the executor sends.
- The prompt is byte-stable: members sorted, no timestamps, deterministic serialization. This matters for prompt caching (below), which is a prefix match.

Nothing else reaches the model. No table schemas, no raw column lists, no SQL dialect. The grounding mechanism follows PRD section 7.2: constrained selection and parameterization, not open-ended authorship.

## The outcome taxonomy

The model must return one of three typed outcomes, defined as a discriminated union in `nl/schema.py` and enforced through the API's structured-output parsing (`nl/planner.py`):

- **query**: a `QueryPlan` (view, measures, dimensions, filters, time dimension with granularity and inclusive ISO date range, order, limit) plus the name of the governed metric the plan answers with. The metric name is part of the contract: it is what the answer displays for auditability and what the Phase 5 harness scores for metric-selection correctness.
- **refuse**: a reason why the question maps to no governed metric.
- **clarify**: one specific question back to the user, when the question is answerable but ambiguous in a way that changes the result (unclear region, period, or metric).

The schema is the shared contract between the planner (Phase 4), the eval harness (Phase 5), and the front end (Phase 6). A question type the schema structurally cannot express is a stop-and-ask event, not a quiet extension, because a schema change is a contract change with the harness.

The refusal policy is stated in the grounding rules (`nl/catalog.py`) and names the non-answerable territory explicitly: carbon intensity or emissions, weather-normalized demand, electricity prices or markets, balancing authorities other than PJM, ERCO, and CISO, dates before 2019-01-01 or after 2026-05-03, plant- or generator-level detail, forecasts, and causal explanations. The model is also instructed not to answer an ungoverned question with a nearby governed one unless the substitution is exact.

Refusal is a feature, not a failure (PRD section 7.3). The design position, recorded in the metric catalog: an ungoverned answer is a fabricated one. A question that does not map to a governed metric is not answerable, by design.

## Deterministic enforcement

The model is not trusted to stay on the governed surface; `nl/validator.py` guarantees it. Before anything executes, every part of a `QueryPlan` is checked against the `/v1/meta`-derived surface:

- The view must be governed; every measure, dimension, and filter member must exist on that view.
- Filter values are checked against allowed sets: `ba_code` values must be in PJM/ERCO/CISO, year filters must be plain four-digit years, date ranges must be ordered ISO dates, order members must be selected in the plan, and the row limit is capped.
- The governed data window (2019-01-01 through 2026-05-03, defined once in `nl/catalog.py`) is enforced, not just stated in the prompt: date ranges must lie inside it, and year filters may not request data outside it. The year check follows the interval each operator implies, so `gt 2018` (years 2019 and later) is valid while `gte 2018` is not, and `notEquals` is unbounded because it excludes rather than requests. Out-of-window plans are refused, never clipped: clipping is silent repair.
- Any violation converts the plan to a refusal listing what went wrong (`nl/interface.py`). Invalid plans are never silently repaired: a repair would substitute the code's guess for the model's, which is the same integrity problem one layer down.

The executor (`nl/executor.py`) touches exactly one Cube endpoint, `/cubejs-api/v1/load`, and only with plans that passed the validator. It translates the `QueryPlan` into Cube's REST query format, waits through Cube's "Continue wait" long-query handshake, and surfaces Cube errors as errors rather than swallowing them. There is no SQL anywhere in `nl/`; the LLM cannot emit it and the code never constructs it.

Between them, the two Cube endpoints (`/v1/meta` read at startup, `/v1/load` for validated plans) are the entire surface this layer touches. Everything under the views (the private cubes, the dbt marts, the DuckDB file) is unreachable from here.

## Deterministic answers

Every number shown to the user comes straight from Cube result rows, formatted by code in `nl/answer.py`. The LLM never produces or restates a figure (integrity rule 1 in `CLAUDE.md`); its output ends at the plan.

Every answer displays the governed metric and the exact parameters used (filters, period, granularity, grouping), so the answer is auditable back to a named, version-controlled metric definition (PRD section 9). The renderer also attaches caveat lines when the queried slice warrants them. The caveat text is defined in `nl/catalog.py` alongside the other governed facts (BA codes, data window); the renderer holds only the slice conditions:

- Demand answers that do not filter on imputation status note that the values mix reported and PUDL-imputed hours, and point to `imputed_demand_share` for the same slice.
- Generation-mix answers whose window spans 2024-07-01 (or has no date bound) note the EIA-930 fuel recategorization break, with CISO hydro flagged as the ambiguous case.
- Growth answers note that growth is defined over complete calendar years only, so the partial year 2026 returns null by design.
- Generation-mix answers containing nulls note that null means the BA does not report that fuel: absence of data, not zero. ERCO reports no petroleum.

These caveats implement integrity rule 3 (surface imputation status) and the locked data decisions in `docs/ROADMAP.md` at the point where a user actually sees a number.

## Cost design

The model is `claude-haiku-4-5` (`nl/planner.py`). The task is constrained metric selection over a small governed catalog, not open-ended generation; misinterpretation rate is measured by the Phase 5 eval, and the model choice is revisited only with that data (locked decision, `docs/ROADMAP.md`).

The system prompt (grounding rules + governed surface + metric catalog) is the static prefix and carries a `cache_control: {type: ephemeral}` breakpoint; the question is the only volatile content and comes after it. Because the prefix is byte-stable, every question after the first reads the prefix from cache instead of paying for it as fresh input. Measured on 2026-07-14 from the pipeline's own usage telemetry:

- The cached prefix measures 7,780 tokens by the API's cache-write/cache-read counters, comfortably above Haiku 4.5's 4,096-token minimum cacheable prefix. Of that, the system prompt alone counts 5,812 tokens by the Anthropic `count_tokens` endpoint; the remainder is the structured-output schema, which sits in the prefix and is cached with it.
- A cached question showed usage of 19 uncached input tokens, 7,780 cache-read tokens, and 121 output tokens.

So the per-question marginal cost is dominated by cache reads and a few dozen fresh tokens, not the full catalog. The CLI prints the usage counters after every answer so cache behavior stays observable. The Phase 5 eval harness will run its ~50-question golden set through the Message Batches API (locked decision, `docs/ROADMAP.md`); the harness is being designed for it from the start.

Accuracy is not reported here. It is measured by the Phase 5 harness and unreported until then.

## Failure modes and limitations

- **The LLM can still pick a wrong metric or parameter.** A fluent question about demand can produce a surface-valid plan against the wrong measure, region, or period. This is exactly what the Phase 5 eval harness measures (PRD sections 7.3 and 8), with failures categorized: wrong metric, wrong parameter, wrong period, refusal that should have answered, answer that should have refused.
- **The validator checks surface validity, not intent.** A plan can use only governed members, pass every check, and still answer a different question than the one asked. No deterministic check can catch that class of error, which is why the eval harness exists as a separate layer rather than a nice-to-have.
- **Single-shot only.** Each question yields exactly one typed outcome. Clarifications are returned to the caller, not conversed: there is no multi-turn dialogue in Phase 4. The Phase 6 front end can loop a clarification by re-asking.
- **Local only.** Cube runs on localhost, the API key lives in a local `.env`, and nothing is deployed. This is a deliberate scope bound, not an accident.

One structural property is worth stating plainly: this architecture is its own fallback. Under the project's scope-control rule (PRD section 12), if the free-form NL interface has to be cut, the `QueryPlan` schema, validator, executor, and renderer are exactly the parameterized-query interface that survives; only `nl/planner.py` would be replaced by a fixed question-to-plan mapping. The LLM is the one swappable component, which is what "thin translation layer" means in practice.

## How to run it

1. Start the semantic layer: `make cube-up` (Docker, pinned Cube image).
2. Put `ANTHROPIC_API_KEY` in `.env` at the repo root (`.env.example` shows the shape). The file is gitignored and the key carries a spend cap set in the Anthropic console; nothing key-related is committed.
3. Ask a question: `make ask Q="Which balancing authority had the highest total demand in 2023?"`. The answer prints the governed metric, the parameters used, the result table, applicable caveats, and the token-usage counters.
4. Run the tests: `make nl-test`. Offline tests (validator, catalog assembly, executor and renderer against fixtures) always run and need no API key. Live smoke tests skip when `ANTHROPIC_API_KEY` is unset; with a key and a running Cube they exercise the full stack, including a required refusal, a required clarification, an anchor check, and a cache-hit assertion.
