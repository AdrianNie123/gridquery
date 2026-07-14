# Live smoke tests: the full stack (Haiku planner -> validator -> Cube ->
# renderer) on a handful of questions. Skipped entirely when
# ANTHROPIC_API_KEY is unset; needs Cube running (make cube-up).
# The ~50-question golden set with failure-mode breakdown is Phase 5.

import os

import pytest

anthropic = pytest.importorskip("anthropic")

pytestmark = pytest.mark.skipif(
    not os.environ.get("ANTHROPIC_API_KEY"),
    reason="ANTHROPIC_API_KEY not set; live NL smoke tests skipped",
)

from nl.catalog import build_system_prompt  # noqa: E402
from nl.interface import ask  # noqa: E402
from nl.planner import MODEL  # noqa: E402

ERCO_2023_TOTAL_MWH = 446_793_938  # verified anchor, docs/verification_anchors.md


@pytest.fixture(scope="module")
def live_views():
    from nl.catalog import fetch_meta, governed_views

    return governed_views(fetch_meta())


def test_system_prompt_exceeds_cacheable_minimum(live_views):
    # Haiku 4.5 silently skips caching below 4096 tokens; verify for real.
    client = anthropic.Anthropic()
    count = client.messages.count_tokens(
        model=MODEL,
        system=build_system_prompt(live_views),
        messages=[{"role": "user", "content": "x"}],
    )
    assert count.input_tokens >= 4096, (
        f"system prompt is {count.input_tokens} tokens, under the 4096 "
        "cacheable minimum; caching would silently no-op"
    )


def test_ranking_question_reproduces_anchor(live_views):
    ans = ask("Which balancing authority had the highest total demand in 2023?", views=live_views)
    assert ans.kind == "answer", ans.text
    assert ans.metric == "total_demand"
    erco = [r for r in (ans.rows or []) if r.get(f"{ans.plan.view}.ba_code") == "ERCO"]
    assert erco, f"ERCO missing from ranking rows: {ans.rows}"
    value = float(erco[0][f"{ans.plan.view}.total_demand_mwh"])
    assert value == pytest.approx(ERCO_2023_TOTAL_MWH, rel=1e-6)
    assert "PJM" in ans.text


def test_share_question_uses_named_share_measure(live_views):
    ans = ask("What share of ERCOT's generation came from wind in 2023?", views=live_views)
    assert ans.kind == "answer", ans.text
    assert "generation_mix.wind_share" in ans.plan.measures
    assert not any(
        f.member.endswith("unified_fuel_category") for f in ans.plan.filters
    ), "share must come from the named measure, not a fuel-category filter"


def test_growth_question_uses_growth_view(live_views):
    ans = ask("How fast did demand grow in Texas in 2023?", views=live_views)
    assert ans.kind == "answer", ans.text
    assert ans.plan.view == "demand_growth"


def test_carbon_intensity_refuses(live_views):
    ans = ask("What is the carbon intensity of PJM's grid?", views=live_views)
    assert ans.kind == "refusal", f"expected refusal, got {ans.kind}: {ans.text}"


def test_out_of_scope_ba_refuses(live_views):
    ans = ask("What was total demand in MISO last year?", views=live_views)
    assert ans.kind in ("refusal", "clarification"), ans.text
    assert "MISO" not in str((ans.plan and ans.plan.filters) or "")


def test_ambiguous_question_clarifies(live_views):
    ans = ask("How much power was used?", views=live_views)
    assert ans.kind == "clarification", f"expected clarification, got {ans.kind}: {ans.text}"


def test_second_call_reads_prompt_cache(live_views):
    first = ask("What was CISO's peak demand in 2023?", views=live_views)
    second = ask("What was PJM's peak demand in 2022?", views=live_views)
    assert first.kind == "answer" and second.kind == "answer"
    assert (second.usage.get("cache_read_input_tokens") or 0) > 0, (
        f"no cache read on the second call: {second.usage}. "
        "A byte-unstable prefix silently disables caching."
    )
