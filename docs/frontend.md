# Front end (Phase 6)

Streamlit app over the frozen Phase 4/5 contract. Launch with:

```
make cube-up   # Cube semantic layer (Docker)
make app       # streamlit run app/Home.py, needs ANTHROPIC_API_KEY in .env
```

## Pages

- **Home** - the NL query page. One question in, one `nl.interface.ask()`
  call out, rendered by outcome kind: answer (metric, parameters, result
  rows, caveats, plan JSON in an expander), refusal (by design, with a
  pointer to the governed surface in `docs/metric_catalog.md`), or
  clarification (the input stays populated so the user refines and
  re-asks; single-shot, no multi-turn dialogue).
- **Demand Growth Leaderboard** - year-over-year growth by BA for a
  selected year plus window CAGR per BA, from the `demand_growth` view.
  2026 is selectable but returns null by design (partial year); the page
  shows the null and says why.
- **Generation Mix** - the named share measures from the
  `generation_mix` view by BA and year. Shares are never computed in the
  app by filtering fuel categories. Series-break and null-means-absence
  caveats appear when the slice warrants them.
- **Eval Results** - renders `eval/results/latest.json` exactly as the
  Phase 5 harness wrote it. Without an artifact the page says so and
  shows nothing else.

## Ground rules the app is built under

- Every number shown comes from Cube result rows or the eval artifact.
  No placeholder or illustrative numbers anywhere, including empty states.
- Pre-built pages use hardcoded governed `QueryPlan`s that pass
  `nl.validator.validate_plan` at page load and run through
  `nl.executor.execute_plan`. No SQL and no DuckDB anywhere in `app/`.
- The app never modifies anything under `nl/`, `eval/`, `semantic/`, or
  `transform/` (frozen contract). It reuses the shipped renderer's
  formatting helpers so the UI matches the CLI path.
- Cube down or a missing API key produces setup instructions, never a
  stack trace and never fake data.

`make app` sets `PYTHONPATH=.` because the repo is not an installed
package; the pages import `nl/` from the repo root.
