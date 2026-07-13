# Phase 3 Explained Simply

This note explains what Phase 3 does in plain language.

Audience: someone with basic coding experience, about a year of Docker exposure, and new to semantic layers/Cube.

## Big picture

In Phase 2, you built clean data tables with dbt.

In Phase 3, you built a **semantic layer** with Cube on top of those tables.

Think of it like this:

- Phase 2 = clean ingredients in the fridge
- Phase 3 = a menu with fixed recipes

People (and later your LLM) can order from the menu, but cannot invent random recipes.

That is how you keep answers consistent and trustworthy.

## What a semantic layer is

A semantic layer is a controlled place where metric definitions live.

Instead of asking raw SQL questions like:
"sum some column maybe grouped by maybe this date thing..."

You ask named metrics like:

- `total_demand`
- `peak_demand`
- `demand_yoy_growth`
- `renewable_share`

Each metric has one official definition.

## What you built in Phase 3

You created a new `semantic/` area with:

- Cube config
- Cube model files (metrics and dimensions)
- API tests
- Docker compose setup

You exposed exactly 3 public views:

- `demand`
- `demand_growth`
- `generation_mix`

These views are the only allowed public surface.

Under them, you defined the governed metrics from your roadmap and metric catalog.

## Why this is important

Without this layer:

- Different queries can calculate "the same metric" differently
- LLM tools may generate inconsistent SQL
- Trust drops

With this layer:

- One metric name -> one formula
- Business rules are explicit and reusable
- You can test metric outputs through an API

This is the core "trust architecture" of your project.

## What Docker is doing here

You run Cube in a Docker container so it is reproducible and isolated.

- `make cube-up` starts Cube
- `make cube-test` runs tests against Cube API
- `make cube-down` stops Cube

Cube reads from your DuckDB warehouse in read-only mode.

Important idea:

- dbt is the writer (builds/updates tables)
- Cube is the reader (serves governed metrics)

So the semantic layer cannot accidentally mutate the warehouse.

## How the request flow works (simple)

1. A question comes in (later from app/LLM).
2. The app maps it to a governed metric in Cube.
3. Cube translates that metric to SQL over your marts.
4. DuckDB runs the query.
5. Cube returns a structured answer.
6. If the question is outside governed metrics, the system should refuse/clarify.

## What is governed vs not governed

Governed in Phase 3:

- Demand metrics (total/peak/average/imputed share)
- Demand growth metrics (YoY, CAGR, complete-year guarded)
- Generation and mix metrics (renewable/fossil/carbon-free and per-fuel shares)

Not governed by design (for now):

- Carbon-intensity proxy (deferred)
- Weather normalization (out of scope)
- Arbitrary raw-SQL requests

## How tests protect quality

You added semantic tests that:

- Compare Cube API outputs to direct DuckDB SQL
- Check anchors (known expected values)
- Check governance surface (`/meta`) to ensure only allowed views/members are public
- Check growth behavior on partial years

So this is not only modeled, it is verified.

## One-sentence summary

Phase 3 turned your clean tables into a tested, governed metric API that later LLM/app layers can safely use without writing free-form SQL.
