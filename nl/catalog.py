"""Governed-surface catalog and system-prompt assembly.

Fetches Cube's /v1/meta, filters it to the three governed views, and builds
the byte-stable system prompt the planner LLM sees. The prompt prefix must
not change between calls (prompt caching is a prefix match), so everything
here serializes deterministically: members sorted, no timestamps, the
metric catalog embedded verbatim from docs/metric_catalog.md.
"""

from pathlib import Path

import requests

from nl.schema import GOVERNED_VIEWS

CUBE_BASE_URL = "http://localhost:4000"
CUBE_META_URL = CUBE_BASE_URL + "/cubejs-api/v1/meta"
CUBE_LOAD_URL = CUBE_BASE_URL + "/cubejs-api/v1/load"

REPO_ROOT = Path(__file__).resolve().parents[1]
METRIC_CATALOG_PATH = REPO_ROOT / "docs" / "metric_catalog.md"

ALLOWED_BA_CODES = ("PJM", "ERCO", "CISO")

# The governed data window. Single source of truth: the system prompt states
# it and the validator enforces it. Update on re-landing, together with the
# accepted-range bounds policy in dbt.
DATA_WINDOW_START = "2019-01-01"
DATA_WINDOW_END = "2026-05-03"

SERIES_BREAK_DATE = "2024-07-01"

# Caveat text attached to answers by nl/answer.py when the queried slice
# warrants it. The text lives here with the other governed facts (BA codes,
# window); the slice conditions live in the renderer. Each caveat restates a
# locked data decision from docs/ROADMAP.md / docs/metric_catalog.md.
CAVEATS = {
    "series_break": (
        "Window spans the 2024-07-01 EIA-930 fuel recategorization; unified "
        "series carry the break (CISO hydro is the ambiguous case). See the "
        "metric catalog."
    ),
    "imputation_mix": (
        "Demand values mix reported and PUDL-imputed hours; the "
        "imputed_demand_share metric quantifies the mix for this slice."
    ),
    "growth_complete_years": (
        "Growth is defined over complete calendar years only; the partial "
        "year 2026 returns null by design."
    ),
    "mix_nulls": (
        "Null means the BA does not report that fuel (absence of data, not "
        "zero); ERCO reports no petroleum."
    ),
}

GROUNDING_RULES = """\
You translate a single natural-language question about U.S. grid demand and
generation into exactly one structured outcome. You never write SQL and you
never invent numbers. Your only job is to select and parameterize governed
metrics from the catalog below, or to refuse or ask for clarification.

Rules:
1. Answerable questions map to one governed view and its members. Use fully
   qualified member names ("view.member") exactly as listed in the surface
   section below.
2. Refuse when the question needs anything outside the governed surface:
   carbon intensity or emissions, weather-normalized demand, electricity
   prices or markets, balancing authorities other than PJM, ERCO, and CISO,
   dates before 2019-01-01 or after 2026-05-03, plant- or generator-level
   detail, forecasts, or causal explanations. State plainly why it is not
   answerable. Do not answer an ungoverned question with a nearby governed
   one unless the substitution is exact.
3. Clarify when the question is answerable but ambiguous in a way that
   changes the result: an unclear region, an unclear period, or an unclear
   metric (for example "renewables" could mean renewable_share or
   generation by fuel). Ask one specific question.
4. Regions: PJM, ERCO (ERCOT / Texas), CISO (CAISO / California). Map
   common names to these codes. Any other region is a refusal.
5. Growth questions use the demand_growth view. Growth is defined over
   complete calendar years only; the partial year 2026 returns null by
   design. Filter demand_growth.year with plain integer values ("2023").
6. Share and mix questions use the named per-fuel or bucket share measures
   on generation_mix. Never compute a share by filtering
   unified_fuel_category; the named measures keep the governed denominator.
7. Time ranges on demand and generation_mix use the view's datetime_utc
   time dimension with an inclusive ISO date_range. A calendar year is
   ["YYYY-01-01", "YYYY-12-31"]. All timestamps are UTC, hour-beginning.
8. Rankings ("which BA had the highest...") group by ba_code and order by
   the measure descending. Do not use limit 1 for rankings across the
   three BAs; return all three so the comparison is visible.
9. The answer will be rendered from the query result by code, not by you.
   Choose the metric, parameters, and ordering so the result rows contain
   the answer directly.
"""


def fetch_meta(base_url: str = CUBE_BASE_URL) -> dict:
    """Fetch the raw /v1/meta payload from a running Cube instance."""
    resp = requests.get(base_url + "/cubejs-api/v1/meta", timeout=10)
    resp.raise_for_status()
    return resp.json()


def governed_views(meta: dict) -> dict:
    """Reduce /v1/meta to the governed views only.

    Returns {view_name: {"measures": {name: type}, "dimensions": {name: type}}}
    keeping only cubes that are public AND in the expected governed set, and
    only their public members. Anything else is invisible to the NL layer.
    """
    views = {}
    for cube in meta["cubes"]:
        if not cube.get("public", False):
            continue
        if cube["name"] not in GOVERNED_VIEWS:
            continue
        views[cube["name"]] = {
            "measures": {
                m["name"]: m["type"]
                for m in cube.get("measures", [])
                if m.get("public", False)
            },
            "dimensions": {
                d["name"]: d["type"]
                for d in cube.get("dimensions", [])
                if d.get("public", False)
            },
        }
    missing = set(GOVERNED_VIEWS) - set(views)
    if missing:
        raise RuntimeError(
            f"Governed views missing from Cube meta: {sorted(missing)}. "
            "Is the semantic layer serving the expected model?"
        )
    return views


def _surface_section(views: dict) -> str:
    """Deterministic listing of the governed surface (sorted, no extras)."""
    lines = ["Governed surface (the only members you may use):"]
    for view_name in sorted(views):
        view = views[view_name]
        lines.append(f"\nview {view_name}:")
        for name in sorted(view["measures"]):
            lines.append(f"  measure {name} ({view['measures'][name]})")
        for name in sorted(view["dimensions"]):
            lines.append(f"  dimension {name} ({view['dimensions'][name]})")
    return "\n".join(lines)


def build_system_prompt(views: dict) -> str:
    """Assemble the full, byte-stable system prompt for the planner."""
    catalog_text = METRIC_CATALOG_PATH.read_text()
    allowed = ", ".join(ALLOWED_BA_CODES)
    return (
        GROUNDING_RULES
        + f"\nAllowed ba_code values: {allowed}.\n"
        + f"Data window: {DATA_WINDOW_START} through {DATA_WINDOW_END} "
        + "(2026 is a partial year). Date ranges must stay inside this window; "
        + f"a question about 2026 uses end date {DATA_WINDOW_END}.\n\n"
        + _surface_section(views)
        + "\n\n--- METRIC CATALOG ---\n\n"
        + catalog_text
    )
