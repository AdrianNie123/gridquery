# plan.md - Phase 5: Evaluation harness

## Context

Phases 1-4 are complete. Phase 4 delivered the NL layer with `ask(question, views=None, client=None) -> Answer` in `nl/interface.py` as the single entry point, the typed outcome contract in `nl/schema.py` (query / refuse / clarify), and working prompt caching (7,780-token cached prefix). Phase 5 builds the golden-set evaluation harness (PRD section 8): ~50 questions with expected outcomes, run through the Message Batches API, scored deterministically, with a failure-mode taxonomy and honest as-measured reporting. This is the differentiator phase (ROADMAP: heavy).

## Decisions locked at Phase 5 planning (2026-07-15, recorded in `docs/ROADMAP.md`)

- **Batches API** for the ~50-question run (50% price, results keyed by `custom_id`), per the decision recorded at Phase 4 planning.
- **Integrity split:** the hand-authored `eval/golden_set.yaml` contains no numbers; expected numeric rows live in `eval/golden_results.json`, produced only by `make eval-pin` executing the hand-authored golden plans against the tested Cube layer. Integrity rule 1 enforced structurally, not by discipline.
- **Scoring is deterministic.** No LLM-as-judge in v1 (PRD 8.2 names it optional; recorded as not-built in the report).
- **Numeric tolerance `rel_tol=1e-6`** (`math.isclose`): expected values come from the same engine over the same data, so agreement is near-exact; the tolerance absorbs float summation-order noise only. A legitimate equivalent plan failing 1e-6 is stop-and-investigate, never a prompt to loosen.
- **Composition: 35 query / 10 refuse / 5 clarify.**
- **Artifact contract:** `eval/results/latest.json` is the single output consumed by both `docs/eval_report.md` and the Phase 6 Streamlit eval page.

## Structure

New top-level `eval/` package:

- `eval/golden.py` - loads and structurally validates `eval/golden_set.yaml`: ids unique, kinds valid, every `golden_plan` parses as `nl.schema.QueryPlan` and passes `nl.validator.validate_plan` against the fixture meta (`nl/tests/fixtures/meta.json`), offline. A golden plan that is itself invalid is a build error caught before any API spend.
- `eval/pin.py` - executes the golden plans against live Cube and writes `eval/golden_results.json` with metadata (git commit, timestamp). The only writer of expected numbers.
- `eval/batch.py` - builds batch requests from `nl.planner.build_request_params` (the same builder the live path uses), submits, polls until ended, streams results keyed by `custom_id`, persists raw results to `eval/results/raw_<batch_id>.jsonl` so re-scoring is free (`--resume`).
- `eval/score.py` - deterministic scoring: outcome kind; metric selection (alias table + view/measures/BA-filter-set/grouping-set checks + period canonicalization so a year filter and a covering date_range are equivalent while off-by-one fails); result match by running the model's plan through the real `nl.validator.validate_plan` + `nl.executor.execute_plan` and comparing rows to pinned rows. Row semantics: columns projected onto the golden plan's columns; rows as a multiset keyed by dimension tuple, ordered sequence when the entry sets `ordered: true`; null matches only null (absence of data is not zero, per the ERCO petroleum decision).
- `eval/report.py` - renders `docs/eval_report.md` from the run artifact.
- `eval/__main__.py` - CLI: `uv run python -m eval {pin|run|score|report} [--resume BATCH_ID]`.
- `eval/golden_set.yaml` - hand-authored. `eval/golden_results.json` - pinned, committed, regenerated only by `make eval-pin`.
- `eval/results/` - run artifacts, gitignored except `latest.json`.
- `eval/tests/` - offline pytest, no API key needed, mirroring `nl/tests` conventions.

Failure taxonomy (PRD 8.3): `wrong_metric`, `wrong_parameter`, `wrong_period`, `refusal_should_have_answered`, `answered_should_have_refused`, plus `clarified_should_have_answered` / `answered_should_have_clarified` reported alongside. A query question passes iff kind, metric-selection, and result checks all pass; metric-selection accuracy and result accuracy are also reported separately as the two PRD 8.2 check types.

Makefile targets: `eval-pin`, `eval` (full batch run), `eval-score` (re-score a saved raw batch, no API cost), `eval-report`, `eval-test`.

## Prerequisite refactor (contract-preserving)

- `nl/planner.py`: extract `build_request_params(question, system_prompt) -> dict` producing the exact Messages API body (system block with `cache_control`, structured-output schema from `PlannerResponse`); the live path becomes `messages.create(**params)` + parse. Return shape of `plan_question` unchanged.
- `nl/interface.py`: extract `resolve_outcome(parsed, views, usage) -> Answer` (validator -> executor -> renderer, refusal on violations); `ask()` calls planner then `resolve_outcome`. The eval scorer feeds batch-parsed responses through the same `resolve_outcome`, so the eval measures the shipped system, not a reimplementation.
- An offline test asserts the live request body equals the batch params byte-for-byte for the same question. Existing live smoke (cache hit + anchor) must stay green after the refactor.

## Golden set composition

Query (35), covering all 11 governed metrics: total_demand x4 (incl. the ERCOT-2023 anchor ranking), peak_demand x3, average_demand x2, demand_yoy_growth x4 (incl. the partial-2026 null-by-design case), demand_cagr x3, generation_by_fuel x3 (incl. one window spanning the 2024-07-01 break), generation_mix_share x4, renewable_share x3, fossil_share x3 (incl. ERCO petroleum absence), carbon_free_share x3, imputed_demand_share x3.
Refuse (10): carbon intensity x2, prices, out-of-scope BAs x2, out-of-window dates x2, weather normalization, forecast, plant-level detail.
Clarify (5): ambiguous region, period, metric (x2), comparison basis - each genuinely answerable-but-ambiguous, not a disguised refusal.

Example entry (schema for every entry):

```yaml
- id: q07_total_demand_ranking_2023
  question: "Which balancing authority had the highest total demand in 2023?"
  kind: query
  expected_metric: total_demand
  golden_plan:
    view: demand
    measures: [demand.total_demand_mwh]
    dimensions: [demand.ba_code]
    time_dimension: {dimension: demand.datetime_utc, date_range: ["2023-01-01", "2023-12-31"]}
    order: [{member: demand.total_demand_mwh, direction: desc}]
  checks: {ba_filter: [], group_by: [ba_code], period: {years: [2023]}, ordered: true}
  notes: "Anchor: ERCO 2023 total = 446.79 TWh (docs/verification_anchors.md)."
```

## Run artifact

One JSON per run in `eval/results/`, copied to `eval/results/latest.json`: run metadata (run id, git commit, batch id, sha256 of golden set / pinned results / system prompt), aggregate accuracies (overall, metric-selection, result, refusal, clarify), failure-mode counts, per-question detail (expected vs actual, per-check booleans, failure mode, usage), and actual token usage + cost with a dated pricing basis. Estimated ~$0.04-0.22 per run at Haiku batch pricing; the artifact records what actually happened.

## Execution order

0. Close the Phase 4 gate (done: 179 nl tests + 24 Cube tests green 2026-07-15). Materialize this plan and `docs/plans/phase6.md`. Add `pyyaml`. Commit.
1. Planner split refactor + equivalence test. All existing tests green. Commit.
2. Harness scaffold: loader, scorer, artifact schema. Delegation checkpoint: subagent S1 writes the scorer test suite (every failure category, period-equivalence cases, row-comparison edges); subagent S2 writes `eval/report.py` from the frozen artifact schema. `make eval-test` green. Commit. Phase 6 worktree agent launches after this step.
3. Golden set: subagent S3 drafts question phrasings from the composition table; golden plans and check blocks are authored in the primary session (they encode metric semantics). `make eval-pin`; hand-check anchors in the pinned rows. Commit golden set + pinned results together.
4. Batch runner + first full `make eval` run end-to-end. Commit code, then artifact + `docs/eval_report.md`.
5. Failure analysis: read every failed question; a miscategorized failure is a harness bug - fix and re-score from the saved raw batch (free). Commit. Stop for phase-gate review.

## Verification (phase done conditions)

- `make eval-test` green offline with no API key.
- `make eval-pin` reproduces `eval/golden_results.json` against the current data, and the ERCOT/CISO anchors appear in the pinned rows.
- The equivalence test proves live and batch request bodies are identical; live smoke (incl. cache hit) still green after the refactor.
- One `make eval` run completes end-to-end; the artifact contains per-question outcomes, both PRD check-type accuracies, the failure-mode breakdown, and actual token usage + cost; `docs/eval_report.md` renders from it.
- Zero hand-typed numbers anywhere: `golden_set.yaml` contains no expected values; report numbers all trace to the artifact.
- Human has reviewed the failure analysis before the phase is called done.

## Stop-and-ask triggers

- A golden question the `QueryPlan` schema cannot express (schema change = contract change with Phases 4 and 6).
- Accuracy so low the harness itself is suspect (first suspect scoring/canonicalization bugs; bring per-question evidence before proposing model escalation, per the locked Phase 4 decision).
- An equivalent-correct plan failing the 1e-6 tolerance.
- A pin diff not explained by a data change.
- Batch results missing or erroring for some custom_ids beyond simple resubmission (partial-run scoring policy needs a human call).
- Anything tempting the harness to bypass `nl/validator` or `nl/executor` - the eval must measure the shipped system.
