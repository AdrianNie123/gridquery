# Offline validator tests: the deterministic guardrail must accept every
# governed metric expressed as a valid plan, and reject anything off the
# governed surface. No Cube, no API key.

import pytest

from nl.schema import Filter, Order, QueryPlan, TimeDimension
from nl.validator import validate_plan


def plan(**overrides):
    """A known-good baseline plan; override fields per test."""
    base = dict(
        view="demand",
        measures=["demand.total_demand_mwh"],
        dimensions=["demand.ba_code"],
        filters=[],
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc",
            granularity=None,
            date_range=["2023-01-01", "2023-12-31"],
        ),
        order=[Order(member="demand.total_demand_mwh", direction="desc")],
        limit=None,
    )
    base.update(overrides)
    return QueryPlan(**base)


# --- acceptance: every named governed metric is expressible and valid ---

GOVERNED_METRIC_PLANS = {
    "total_demand": plan(),
    "peak_demand": plan(measures=["demand.peak_demand_mwh"], order=[]),
    "average_demand": plan(measures=["demand.average_demand_mwh"], order=[]),
    "imputed_demand_share": plan(measures=["demand.imputed_demand_share"], order=[]),
    "demand_yoy_growth": QueryPlan(
        view="demand_growth",
        measures=["demand_growth.demand_yoy_growth"],
        dimensions=["demand_growth.ba_code", "demand_growth.year"],
        filters=[Filter(member="demand_growth.year", operator="equals", values=["2023"])],
    ),
    "demand_cagr": QueryPlan(
        view="demand_growth",
        measures=["demand_growth.demand_cagr"],
        dimensions=["demand_growth.ba_code"],
        filters=[
            Filter(member="demand_growth.year", operator="gte", values=["2019"]),
            Filter(member="demand_growth.year", operator="lte", values=["2023"]),
        ],
    ),
    "generation_by_fuel": QueryPlan(
        view="generation_mix",
        measures=["generation_mix.generation_mwh"],
        dimensions=["generation_mix.unified_fuel_category"],
        filters=[Filter(member="generation_mix.ba_code", operator="equals", values=["CISO"])],
        time_dimension=TimeDimension(
            dimension="generation_mix.datetime_utc",
            date_range=["2023-01-01", "2023-12-31"],
        ),
    ),
    "generation_mix_share": QueryPlan(
        view="generation_mix",
        measures=["generation_mix.gas_share"],
        dimensions=["generation_mix.ba_code"],
    ),
    "renewable_share": QueryPlan(
        view="generation_mix",
        measures=["generation_mix.renewable_share"],
        dimensions=["generation_mix.ba_code"],
    ),
    "fossil_share": QueryPlan(
        view="generation_mix",
        measures=["generation_mix.fossil_share"],
        dimensions=["generation_mix.ba_code"],
    ),
    "carbon_free_share": QueryPlan(
        view="generation_mix",
        measures=["generation_mix.carbon_free_share"],
        dimensions=["generation_mix.ba_code"],
    ),
}


@pytest.mark.parametrize("metric", sorted(GOVERNED_METRIC_PLANS))
def test_every_governed_metric_has_a_valid_plan(metric, views):
    assert validate_plan(GOVERNED_METRIC_PLANS[metric], views) == []


# --- rejection: anything off the governed surface ---

def test_rejects_private_cube_members(views):
    p = plan(measures=["hourly_demand.total_demand_mwh"])
    violations = validate_plan(p, views)
    assert violations, "private cube member must be rejected"


def test_rejects_unknown_measure(views):
    p = plan(measures=["demand.carbon_intensity"])
    assert validate_plan(p, views)


def test_rejects_measure_from_other_view(views):
    p = plan(measures=["generation_mix.renewable_share"])
    assert validate_plan(p, views)


def test_rejects_unknown_dimension(views):
    p = plan(dimensions=["demand.weather_zone"])
    assert validate_plan(p, views)


def test_rejects_bad_ba_code(views):
    p = plan(filters=[Filter(member="demand.ba_code", operator="equals", values=["MISO"])])
    violations = validate_plan(p, views)
    assert any("MISO" in v for v in violations)


def test_rejects_filter_on_ungoverned_member(views):
    p = plan(filters=[Filter(member="demand.raw_demand", operator="equals", values=["1"])])
    assert validate_plan(p, views)


def test_rejects_empty_measures(views):
    p = plan(measures=[])
    assert validate_plan(p, views)


def test_rejects_non_time_dimension_as_time(views):
    p = plan(
        time_dimension=TimeDimension(dimension="demand.ba_code", date_range=["2023-01-01", "2023-12-31"])
    )
    assert validate_plan(p, views)


def test_rejects_malformed_date_range(views):
    p = plan(
        time_dimension=TimeDimension(dimension="demand.datetime_utc", date_range=["2023", "2024"])
    )
    assert validate_plan(p, views)


def test_rejects_inverted_date_range(views):
    p = plan(
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc", date_range=["2024-01-01", "2023-01-01"]
        )
    )
    assert validate_plan(p, views)


def test_rejects_order_on_unselected_member(views):
    p = plan(order=[Order(member="demand.peak_demand_mwh", direction="desc")])
    assert validate_plan(p, views)


def test_rejects_valueless_equals_filter(views):
    p = plan(filters=[Filter(member="demand.ba_code", operator="equals", values=[])])
    assert validate_plan(p, views)


def test_rejects_absurd_limit(views):
    p = plan(limit=1_000_000)
    assert validate_plan(p, views)


def test_rejects_non_year_growth_filter(views):
    p = QueryPlan(
        view="demand_growth",
        measures=["demand_growth.demand_yoy_growth"],
        filters=[Filter(member="demand_growth.year", operator="equals", values=["latest"])],
    )
    assert validate_plan(p, views)
