# GridQuery evaluation report

Run `2026-07-16T17:55:10Z`, commit `ccc0e96`, model `claude-haiku-4-5`, batch `msgbatch_01V4JfrDuneRDGsuUTFcFTZ5`.

Inputs (sha256, first 12 chars): golden set `bd4d7c43eea4`, pinned results `b557c72e8a4c`, system prompt `dac40d42e596`.

## Composition

50 questions: 35 query, 10 refuse, 5 clarify.

## Accuracy

| Check | Accuracy |
|---|---|
| Overall | 86.0% |
| Metric selection | 82.9% |
| Result | 88.6% |
| Refusal | 100.0% |
| Clarify | 80.0% |

A query question passes overall only when all three checks pass: outcome kind, metric selection (including parameters and period), and result match against the pinned rows. Refuse and clarify questions score on outcome kind alone; there is no LLM-as-judge in v1, so the wording of a refusal or clarification is not graded.

## Failure modes

| Failure mode | Count |
|---|---|
| wrong_metric | 2 |
| wrong_parameter | 0 |
| wrong_period | 0 |
| refusal_should_have_answered | 4 |
| answered_should_have_refused | 0 |
| clarified_should_have_answered | 0 |
| answered_should_have_clarified | 1 |

## Failed questions

### q02_total_demand_erco_2022

Question: What was ERCOT total demand in 2022?

- Expected: kind `query`, metric `total_demand`
- Actual: kind `refusal`, metric `n/a`
- Failure mode: `refusal_should_have_answered`
- Detail: Not answerable through the governed metrics: The question requests data from 2022, but the governed data window begins 2019-01-01 and the earliest complete data available is from 2019 onward. The data landing ended 2026-05-03. 2022 is outside the data window available through the GridQuery semantic layer.

### q12_yoy_growth_pjm_2024

Question: What was PJM demand year-over-year growth for 2024?

- Expected: kind `query`, metric `demand_yoy_growth`
- Actual: kind `refusal`, metric `n/a`
- Failure mode: `refusal_should_have_answered`
- Detail: Not answerable through the governed metrics: the proposed query left the governed surface (order member 'demand_growth.year' is not selected in the plan)

### q13_yoy_growth_partial_2026_erco

Question: What is ERCOT demand year-over-year growth for 2026?

- Expected: kind `query`, metric `demand_yoy_growth`
- Actual: kind `refusal`, metric `n/a`
- Failure mode: `refusal_should_have_answered`
- Detail: Not answerable through the governed metrics: 2026 is a partial year (data ends 2026-05-03) and demand_growth metrics require complete calendar years by design. Year-over-year growth for 2026 returns null and cannot be computed from five months of data.

### q22_mix_share_solar_ciso_2025

Question: What was solar share of generation in CISO in 2025?

- Expected: kind `query`, metric `generation_mix_share`
- Actual: kind `answer`, metric `renewable_share`
- Failure mode: `wrong_metric`
- Detail: (none)

### q23_mix_share_hydro_ciso_2024

Question: What was hydro share of generation in CISO in 2024?

- Expected: kind `query`, metric `generation_mix_share`
- Actual: kind `answer`, metric `renewable_share`
- Failure mode: `wrong_metric`
- Detail: (none)

### q32_carbon_free_pjm_2021

Question: What was PJM carbon-free share in 2021?

- Expected: kind `query`, metric `carbon_free_share`
- Actual: kind `refusal`, metric `n/a`
- Failure mode: `refusal_should_have_answered`
- Detail: Not answerable through the governed metrics: Carbon-intensity proxy and emissions data are not governed. The catalog explicitly defers carbon intensity to future work. While the semantic layer does expose carbon_free_share as a generation_mix metric, your question conflates two different concepts: carbon-free generation (which is answerable as renewable + nuclear share) and carbon intensity (which is not). If you are asking for the share of PJM generation from carbon-free sources (renewable + nuclear) in 2021, that is answerable. Please clarify whether you want the carbon-free generation share, or whether you need something else such as emissions or carbon intensity per unit of demand.

### c01_ambiguous_region

Question: Which region had the highest demand in 2023?

- Expected: kind `clarify`, metric `n/a`
- Actual: kind `answer`, metric `total_demand`
- Failure mode: `answered_should_have_clarified`
- Detail: expected clarification, got answer

## Cost and usage

| Counter | Total |
|---|---|
| Input tokens | 955 |
| Output tokens | 5,493 |
| Cache read input tokens | 140,040 |
| Cache creation input tokens | 248,960 |

Estimated cost: $0.1768 USD.

Pricing basis: claude-haiku-4-5 Batches API, 2026-07: $0.50/$2.50 per MTok in/out, cache read $0.05, cache write (5m) $0.625

## How this was measured

- The golden set (`eval/golden_set.yaml`) is hand-authored and contains no numbers.
- Expected rows are pinned by executing the hand-authored golden plans against the tested Cube layer (`make eval-pin`); `eval/golden_results.json` is the only home of expected numbers.
- Planner calls are sent through the Message Batches API with the same request body the live path uses (`nl.planner.build_request_params`).
- Everything after the LLM call is the shipped pipeline: batch responses are resolved through `nl.interface.resolve_outcome` (validator, executor, renderer), not a reimplementation.
- Scoring is deterministic. There is no LLM-as-judge in v1.
- Regenerate this report with `make eval`; re-score a saved batch without API cost with `make eval-score`.
