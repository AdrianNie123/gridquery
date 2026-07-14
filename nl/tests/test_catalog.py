# Offline catalog tests: governed-surface filtering and system-prompt
# stability. The prompt is the cached prefix, so byte-stability across
# calls is a correctness property, not a nicety.

from nl.catalog import build_system_prompt, governed_views
from nl.schema import GOVERNED_VIEWS


def test_governed_views_are_exactly_the_three(views):
    assert set(views) == set(GOVERNED_VIEWS)


def test_private_cubes_are_excluded(meta):
    views = governed_views(meta)
    all_members = {
        name for view in views.values() for name in (*view["measures"], *view["dimensions"])
    }
    assert not any(m.startswith(("hourly_demand.", "hourly_generation.", "annual_demand.")) for m in all_members)


def test_governed_members_match_phase3_surface(views):
    assert set(views["demand"]["measures"]) == {
        "demand.total_demand_mwh",
        "demand.peak_demand_mwh",
        "demand.average_demand_mwh",
        "demand.hours",
        "demand.imputed_hours",
        "demand.imputed_demand_share",
    }
    assert set(views["demand_growth"]["measures"]) == {
        "demand_growth.annual_total_demand_mwh",
        "demand_growth.demand_yoy_growth",
        "demand_growth.demand_cagr",
    }
    assert "generation_mix.renewable_share" in views["generation_mix"]["measures"]
    assert views["demand"]["dimensions"]["demand.datetime_utc"] == "time"


def test_system_prompt_is_byte_stable(views):
    assert build_system_prompt(views) == build_system_prompt(views)


def test_system_prompt_contains_surface_and_catalog(views):
    prompt = build_system_prompt(views)
    assert "measure demand.total_demand_mwh" in prompt
    assert "METRIC CATALOG" in prompt
    assert "ERCO" in prompt
    # Refusal policy names the deferred metric explicitly.
    assert "carbon" in prompt.lower()


def test_system_prompt_is_large_enough_to_cache(views):
    # Haiku 4.5's minimum cacheable prefix is 4096 tokens. Exact count needs
    # the API (checked in live smoke); 4 chars/token is a conservative proxy.
    prompt = build_system_prompt(views)
    assert len(prompt) > 4096 * 4, (
        f"system prompt is {len(prompt)} chars; likely under the 4096-token "
        "cacheable minimum for claude-haiku-4-5"
    )
