# PRD: GridQuery — A Governed Semantic Layer with an Evaluated Natural-Language Interface over U.S. Grid Demand Data

**Author:** Adrian
**Status:** Draft v0.1 (for review)
**Last updated:** 2026-07-09
**Target ship window:** 2–3 weeks (AI-assisted build in Cursor + Claude Code, Fable 5)

---

## 0. How to read this document

This is a working PRD, not a marketing artifact. It states explicitly which datasets are used, which tables are pulled, which methods are applied, and where each component's limitations lie. Where a metric requires a formula that is standard, it is named. Where a formula must be decided during the build, it is marked **[DEFINE DURING BUILD]** rather than invented here, to avoid committing a wrong definition on paper. Nothing in this document should be treated as a validated result; results are produced by the pipeline and evaluated by the harness described in Section 8.

---

## 1. Problem statement and motivation

### 1.1 The business problem
Electricity demand in the United States is growing unevenly across regions, and the growth is increasingly driven by large loads such as data centers. Analysts at utilities, grid operators, regulators, and the infrastructure/energy teams of large technology companies repeatedly need to answer questions of the form: *which regions are seeing the fastest demand growth, how is the generation mix serving that growth, and how is the fuel/carbon composition of supply changing over time?*

Answering these today requires an analyst who knows where the data lives, how to clean it, how to define the metric correctly, and how to write the SQL. That is slow, and it does not scale to non-technical stakeholders.

### 1.2 What this project builds
A small but complete data product that lets a user ask those questions in natural language and receive answers that are **grounded in governed metric definitions** rather than generated ad hoc by a language model. The language model is deliberately a thin translation layer; the trustworthiness comes from the semantic layer beneath it and the evaluation harness that holds it accountable.

### 1.3 Why this is the right project (honest framing)
This is explicitly a **small-scale, learning-oriented reconstruction of the architecture that Snowflake Cortex Analyst and Databricks Genie implement at enterprise scale**, applied to a bounded, domain-specific dataset. It is not those products and does not claim to be. Its value as a portfolio piece is that it demonstrates understanding of the *architecture* — ingestion, transformation, governance, grounding, and evaluation — as one connected system, and that it makes the hard parts (metric governance and answer verification) actually present rather than hand-waved.

The intended signal to a hiring manager: this candidate can architect a data product, can articulate why LLM-generated SQL is untrustworthy without a governed semantic layer, and can prove trustworthiness with an evaluation suite. The domain (energy demand economics) is chosen because it is timely, because the data is exceptionally clean, and because it plays to an econometrics/economics background.

### 1.4 What this project is NOT
- It is not a machine-learning research project. There is no novel model. Any forecasting, if included at all, is a stretch goal and uses standard, named methods.
- It is not an enterprise system. Scope is bounded to a subset of balancing authorities, a fixed set of metrics, and a fixed evaluation set.
- It does not claim production reliability. It documents its own error bounds.

---

## 2. Goals, non-goals, and success criteria

### 2.1 Goals
1. Ingest clean hourly grid data and produce a small, well-modeled analytical warehouse.
2. Define a **governed semantic layer** of ~10–15 metrics with explicit, documented economic definitions.
3. Expose a **natural-language query interface** that translates questions into queries against the semantic layer only (never against raw tables).
4. Build an **evaluation harness** of ~50 questions with expected results, run on every change, that measures answer correctness.
5. Present results through a clean front end and document the entire architecture, including its limitations, in a strong README.

### 2.2 Non-goals
- Covering all of PUDL, all balancing authorities, or all fuel types.
- Real-time / streaming ingestion. Batch is sufficient and correct for this data.
- Sub-second query latency or multi-user concurrency.
- A general-purpose text-to-SQL system over arbitrary schemas.

### 2.3 Success criteria (measurable)
- **Data:** the warehouse builds reproducibly from a single command, and dbt tests pass on every model.
- **Semantic layer:** every metric has a written definition, a SQL implementation, and at least one test.
- **NL interface:** achieves a documented accuracy on the ~50-question evaluation set. The *number itself is not a pass/fail target* — the requirement is that the number is honestly measured and reported, with failures analyzed. (Setting an arbitrary accuracy bar on paper would be the kind of invented target this document avoids.)
- **Evaluation:** the harness runs automatically and produces a per-question pass/fail plus an aggregate score.
- **Documentation:** a reader can understand the architecture, reproduce the build, and see the honest limitations.

---

## 3. Users and key questions

### 3.1 Primary user persona
A **regional demand analyst** (or a hiring manager evaluating the project) who wants fast, trustworthy answers to grid-demand questions without writing SQL.

### 3.2 Representative questions the system must handle
These drive both the semantic-layer metric list and the evaluation set. Examples (final set defined in build):
- Which balancing authorities had the highest total electricity demand last year?
- Which region grew fastest in demand over the last three years?
- What share of generation came from natural gas vs. renewables in a given region and period?
- How did peak demand change year over year in a given region?
- Which regions have the highest share of fossil generation?

Each such question maps to one or more **governed metrics**. Questions that cannot be answered by a governed metric must be refused or flagged, not answered by improvised SQL — this refusal behavior is itself a tested feature.

---

## 4. Data sources (explicit)

All data is public and accessed through documented channels. No scraping of undocumented endpoints.

### 4.1 Primary source: PUDL (Catalyst Cooperative)
- **What:** Analysis-ready, cleaned, integrated U.S. energy data distributed as Apache Parquet and SQLite. Maintained by Catalyst Cooperative, released on a regular schedule (confirmed active through 2026), with a documented data dictionary.
- **Access method:** PUDL distributes processed outputs as Parquet files (via AWS Open Data Registry / their documented Data Access page) and a Data Viewer with CSV export. Access is via standard Parquet/SQL tooling; no bespoke API client required.
- **Why PUDL and not raw EIA:** PUDL has already standardized units, cleaned the raw semi-structured government formats, and — critically for this project's data-integrity thesis — runs a **validation pipeline on its EIA-930 hourly demand imputation** that computes percent error against held-out ground-truth values and checks it on every nightly build. This means the primary dataset's quality is instrumented, not merely asserted.

### 4.2 Primary dataset within PUDL: EIA-930 (hourly grid operations)
- **What:** Hourly electricity demand, day-ahead demand forecast, net generation by fuel type, and interchange, reported by the balancing authorities operating the Lower-48 grid.
- **Coverage used:** A **bounded subset of balancing authorities** (final list chosen in build — likely a set that includes high-growth and data-center-heavy regions plus a few contrasting ones), over a multi-year window sufficient to compute year-over-year growth.
- **Known limitation:** EIA-930 contains reported values that require imputation for gaps. PUDL imputes these and measures the error. The project must **surface imputation status** where relevant rather than silently treating imputed values as reported. **[DEFINE DURING BUILD: exactly which imputation-flag columns are carried through to the marts.]**

### 4.3 Supporting dataset (optional, scope-permitting): EIA-860 / generator metadata
- **What:** Generator- and plant-level metadata (fuel type, capacity, location, balancing authority) used to enrich generation-mix analysis.
- **Use:** Only if generation-mix-by-fuel from EIA-930 needs enrichment. Treated as a stretch, not a core dependency.

### 4.4 Explicitly deferred sources
- **FERC Form 1 (financial/rate data):** deferred. Rich but messy (XBRL/DBF), and FERC↔EIA record linkage is a known hard problem that would consume disproportionate time. Named here as related prior domain experience, not built.
- **Wholesale LMP prices (gridstatus):** deferred. Clean but rate-limited and a different (markets) story. Possible future extension.
- **Carbon-intensity feeds (WattTime / Electricity Maps):** deferred. A carbon **proxy** may be derived from EIA-930 generation mix instead (see Section 6), which avoids an external dependency. Marginal-vs-average carbon signal work is explicitly out of scope for v1.

---

## 5. Architecture

### 5.1 High-level flow
```
PUDL Parquet (EIA-930 subset)
        │
        ▼
   [dlt ingestion]  ──►  local landing (Parquet)
        │
        ▼
      [DuckDB]  ◄── analytical engine (local, zero-infra)
        │
        ▼
   [dbt models]  staging → intermediate → marts   (+ dbt tests)
        │
        ▼
 [Semantic layer]  governed metric definitions
        │
        ▼
 [NL interface] ── LLM translates question → semantic-layer query only
        │                     │
        ▼                     ▼
  [Front end]          [Evaluation harness]  ~50 Q&A, run on every change
```

### 5.2 Component choices and rationale

| Layer | Choice | Rationale | Honest note |
|---|---|---|---|
| Ingestion | **dlt** (data load tool) | Python-native, schema inference, modern | For static Parquet, a plain load script is acceptable; dlt is used to demonstrate the modern pattern and to make refresh reproducible |
| Storage/compute | **DuckDB** (local, Parquet) | Fast, zero-infrastructure, reads Parquet natively | Local-only is a deliberate scope choice, not a limitation to hide |
| Transformation | **dbt Core** (with dbt tests) | Largest ecosystem, most hireable, staging→marts discipline | dbt Fusion engine / SQLMesh referenced in README as frontier awareness; not required to build |
| Semantic layer | **[DECISION — see 5.3]** | Governance is the heart of the project | Choice affects how the LLM is grounded |
| NL interface | LLM (via API) constrained to semantic layer | Thin, replaceable, evaluated | The model is NOT the differentiator; the grounding + eval is |
| Orchestration | **Dagster** (stretch) or a simple task runner | Asset-based, best dbt integration | For a 3-week solo build, a Makefile/dbt-run sequence may suffice; Dagster is a stretch that strengthens the "assets + lineage" story |
| Front end | **Streamlit** (familiar) or Evidence.dev | Fast to build, familiar to author | Streamlit chosen for speed unless Evidence's BI-as-code story is worth the extra time |
| Data quality | dbt tests (+ Elementary, stretch) | Tests on every model | Elementary adds observability if time allows |

### 5.3 Key open decision: semantic-layer technology
This is the one architectural decision that should be settled before building, because it determines how the LLM is grounded. Options:

- **Cube** (recommended in research): API-first, fully open-source *including the serving layer*, self-hostable, has a native metadata API well-suited to an agent/LLM discovering available metrics. No dbt Cloud dependency.
- **dbt Semantic Layer / MetricFlow:** metrics co-located with dbt models; MetricFlow is open-source, but the production Semantic Layer *API* historically required dbt Cloud. Must verify current free-tier terms before committing.
- **Hand-rolled metric registry:** a YAML file of metric definitions plus a small resolver that maps metric names to vetted SQL. Lowest external dependency, most transparent, easiest to evaluate — but you build the governance layer yourself.

**Recommendation for this scope:** either **Cube** (if the setup cost is low) or a **hand-rolled metric registry** (if we want maximum transparency and zero external service). Both make the grounding story explicit and testable. **[DECIDE IN PLANNING — this is the first thing to resolve in Section 11.]**

---

## 6. The semantic layer (the heart of the project)

### 6.1 Principle
Every question the system answers is answered through a **named, defined, version-controlled metric**. The LLM does not write arbitrary SQL against raw tables. It selects and parameterizes governed metrics. This is what makes the answers trustworthy and is the single most important design decision in the project.

### 6.2 Candidate metrics (~10–15; final list in build)
Each metric will have: a plain-language definition, an explicit SQL/semantic implementation, the grain it operates at, and at least one test. Formulas that are standard are named; those needing a decision are flagged.

- **Total demand** (sum of hourly demand over a period, by balancing authority). Standard aggregation.
- **Peak demand** (max hourly demand in a period, by BA). Standard.
- **Average demand.** Standard.
- **Demand growth rate** (period-over-period). **[DEFINE DURING BUILD: exact basis — calendar-year totals vs. trailing 12 months vs. peak-to-peak. This choice is an economic decision and must be documented, not defaulted silently.]**
- **Generation by fuel type** (sum of net generation by fuel, by BA, period). Standard aggregation over EIA-930 fuel categories.
- **Generation mix share** (fuel's share of total generation). Standard ratio.
- **Renewable share** (share of generation from renewable fuel categories). **[DEFINE DURING BUILD: exact set of fuel categories counted as "renewable" — this is a definitional choice and must be stated explicitly.]**
- **Fossil share.** Same definitional-choice note.
- **Carbon-intensity proxy** (stretch). **[DEFINE DURING BUILD if included: a proxy derived from generation mix using published, cited emission factors per fuel. Must be clearly labeled a proxy, with the factor source cited. NOT a marginal-emissions signal.]**
- **Interchange / net imports** (stretch, if data supports cleanly).

### 6.3 Data-integrity rules for metrics
- Imputed vs. reported values must not be silently mixed where the distinction matters. **[DEFINE DURING BUILD: policy per metric.]**
- Any metric that divides must guard against divide-by-zero and document behavior on missing periods.
- No metric formula is committed to this document as final unless it is a standard named aggregation; anything requiring a modeling choice is deferred to the build and documented there.

---

## 7. The natural-language interface

### 7.1 Design
The interface accepts a natural-language question and must produce either (a) a query expressed against the governed semantic layer, or (b) a refusal/clarification if the question cannot be mapped to a governed metric. It never emits free-form SQL against raw tables.

### 7.2 Grounding mechanism
The LLM is given the catalog of available metrics, their definitions, and the allowed parameters (regions, time ranges, fuel types). Its task is constrained selection and parameterization, not open-ended SQL authorship. This is the mechanism that converts a plausible-but-possibly-wrong generator into a trustworthy one.

### 7.3 Honest limitations
- The LLM can still misinterpret a question (e.g., pick the wrong metric or wrong region). This is exactly what the evaluation harness exists to measure.
- Ambiguous questions should trigger clarification, not a guess. Refusal/clarification behavior is a tested feature, not a failure.

---

## 8. Evaluation harness ("evals are the new unit tests")

### 8.1 Why this is the differentiator
Most portfolio projects wire up an LLM and stop. This project treats the LLM feature the way a serious team does: with a test suite that runs on every change and measures whether answers are correct. This is the single most defensible thing in the project and the clearest signal of engineering maturity.

### 8.2 Design
- A **golden set of ~50 questions**, each paired with an expected result (or expected metric+parameters, or expected refusal).
- Two check types:
  1. **Execution/result correctness:** does the system's answer match the expected result within tolerance? (For numeric answers, exact or tolerance-based; tolerance **[DEFINE DURING BUILD]**.)
  2. **Metric-selection correctness:** did the system choose the correct governed metric and parameters?
- Optionally, **LLM-as-judge** for questions where the "answer" is a short explanation rather than a number — used cautiously and documented as a secondary check, since LLM-as-judge has known reliability caveats.
- The harness runs via a single command and (stretch) in CI on every commit.

### 8.3 Honest reporting
- The aggregate accuracy is reported as-measured. Failures are categorized (wrong metric, wrong parameter, wrong period, refusal-that-should-have-answered, answer-that-should-have-refused).
- The README presents this honestly, including the failure modes. A project that reports 82% with a failure analysis is more credible than one claiming 100%.

---

## 9. Front end

A clean interface with: a natural-language query box, the returned answer, **the governed metric and parameters that were used** (so the answer is auditable), and a few pre-built views (e.g., demand-growth leaderboard, generation-mix breakdown). Streamlit for speed; Evidence.dev if the BI-as-code presentation is worth the extra time. The auditability element — always showing *which governed metric produced the answer* — is a deliberate trust feature and should not be cut.

---

## 10. Documentation requirements (per your writing guidelines)

- **README** foregrounds the architecture and the grounding + evaluation story, states the datasets and their access methods explicitly, and includes an honest limitations section.
- **Metric catalog** documents every metric's definition, implementation, grain, and tests.
- **Data lineage** from PUDL source through marts to metrics is documented (Dagster provides this automatically if used).
- **Reproducibility:** a documented, single-command build from a clean checkout.
- **No invented results:** every number shown is produced by the pipeline; no illustrative-but-fake figures in the docs.

---

## 11. Open decisions to resolve before building (in order)
1. **Semantic-layer technology:** Cube vs. hand-rolled metric registry vs. MetricFlow (verify dbt Cloud dependency). *Blocks Section 6.*
2. **Balancing-authority subset and time window.** *Blocks ingestion.*
3. **Demand-growth-rate basis** (calendar-year vs. trailing-12-month vs. peak-to-peak). *Economic decision; blocks the flagship metric.*
4. **Renewable/fossil fuel-category definitions.** *Definitional; blocks mix metrics.*
5. **Whether the carbon-intensity proxy is in v1 or deferred.**
6. **Orchestration: Dagster now, or task-runner now + Dagster as stretch.**
7. **Front end: Streamlit vs. Evidence.dev.**

---

## 12. Scope-control and fallback plan (given the 2–3 week ceiling)
- **If the semantic layer + eval harness is consuming more than ~40% of total time by end of week 2:** cut the NL interface to a fixed set of parameterized queries (drop free-form NL), keep the semantic layer, marts, eval-on-metrics, and dashboard. This still demonstrates architecture and governance.
- **If ingestion/cleaning overruns:** narrow the BA subset and the time window rather than skipping tests.
- **Never cut:** dbt tests, the metric-definition documentation, and the honest limitations section. These are the integrity core.

---

## 13. Explicit risks and limitations (summary)
- **Data:** EIA-930 requires imputation; the project surfaces rather than hides this. Coverage is a deliberate subset, not the whole grid.
- **LLM:** can misinterpret questions; measured, not assumed away.
- **Scope:** a solo 2–3 week build; Dagster, Evidence, Elementary, and the carbon proxy are stretches, not commitments.
- **Vendor-claim awareness:** the architecture is inspired by Cortex Analyst / Genie; performance figures cited from vendor blogs in prior research are vendor claims, not independent benchmarks, and are not reproduced as fact in project documentation.
