# Adversarial offline validator tests: hostile, off-surface, and near-miss
# plans that must be rejected in every plan slot; operator and boundary
# edges; and multi-violation reporting. Complements test_validator.py.
# No Cube, no API key.

import pytest

from nl.schema import Filter, Order, QueryPlan, TimeDimension
from nl.validator import validate_plan


def plan(**overrides):
    """A known-good baseline demand plan; override fields per test."""
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


def growth_plan(filters):
    """A known-good demand_growth plan with the given filters."""
    return QueryPlan(
        view="demand_growth",
        measures=["demand_growth.demand_yoy_growth"],
        dimensions=["demand_growth.ba_code", "demand_growth.year"],
        filters=filters,
    )


# --- 1. off-surface members must be rejected in every slot ---

# Each slot builder injects one member string into a different part of an
# otherwise-valid plan.
SLOTS = {
    "measure": lambda m: plan(measures=[m], order=[]),
    "dimension": lambda m: plan(dimensions=[m]),
    "filter": lambda m: plan(
        filters=[Filter(member=m, operator="equals", values=["x"])]
    ),
    "time_dimension": lambda m: plan(
        time_dimension=TimeDimension(dimension=m, date_range=["2023-01-01", "2023-12-31"])
    ),
    "order": lambda m: plan(order=[Order(member=m, direction="desc")]),
}

BAD_MEMBERS = [
    # SQL-ish injection string
    "demand.total_demand_mwh; DROP TABLE x",
    # private (non-public) cube members, one per hidden cube
    "hourly_demand.total_demand_mwh",
    "hourly_demand.datetime_utc",
    "hourly_generation.generation_mwh",
    "annual_demand.demand_yoy_growth",
    # wrong view prefix: real members of OTHER governed views
    "generation_mix.renewable_share",
    "demand_growth.year",
    # near-misses: missing suffix, wrong suffix, typo
    "demand.total_demand",
    "demand.total_demand_mw",
    "demand.totall_demand_mwh",
    # case sensitivity: member names are lowercase in meta
    "demand.BA_CODE",
    "demand.Total_Demand_MWH",
]


@pytest.mark.parametrize("member", BAD_MEMBERS)
@pytest.mark.parametrize("slot", sorted(SLOTS))
def test_off_surface_member_rejected_in_every_slot(slot, member, views):
    assert validate_plan(SLOTS[slot](member), views), (
        f"member '{member}' in slot '{slot}' must be rejected"
    )


def test_missing_governed_view_is_a_single_hard_violation(views):
    # If the view disappears from meta, validation stops at the view check.
    reduced = {k: v for k, v in views.items() if k != "demand"}
    violations = validate_plan(plan(), reduced)
    assert violations == ["view 'demand' is not a governed view"]


# --- 2. filter/operator edges: every operator once valid, once invalid ---

VALID_FILTER_PLANS = {
    "equals": plan(
        filters=[Filter(member="demand.ba_code", operator="equals", values=["PJM"])]
    ),
    "notEquals": plan(
        filters=[Filter(member="demand.ba_code", operator="notEquals", values=["ERCO"])]
    ),
    "gt": growth_plan([Filter(member="demand_growth.year", operator="gt", values=["2019"])]),
    "gte": growth_plan([Filter(member="demand_growth.year", operator="gte", values=["2019"])]),
    "lt": growth_plan([Filter(member="demand_growth.year", operator="lt", values=["2024"])]),
    "lte": growth_plan([Filter(member="demand_growth.year", operator="lte", values=["2023"])]),
    "set": plan(
        filters=[Filter(member="demand.is_imputed", operator="set", values=[])]
    ),
    "notSet": plan(
        filters=[Filter(member="demand.imputation_code", operator="notSet", values=[])]
    ),
}


@pytest.mark.parametrize("op", sorted(VALID_FILTER_PLANS))
def test_every_operator_has_a_valid_use(op, views):
    assert validate_plan(VALID_FILTER_PLANS[op], views) == []


INVALID_FILTER_PLANS = {
    "equals-no-values": plan(
        filters=[Filter(member="demand.ba_code", operator="equals", values=[])]
    ),
    "notEquals-no-values": plan(
        filters=[Filter(member="demand.ba_code", operator="notEquals", values=[])]
    ),
    "gt-no-values": growth_plan(
        [Filter(member="demand_growth.year", operator="gt", values=[])]
    ),
    "gte-no-values": growth_plan(
        [Filter(member="demand_growth.year", operator="gte", values=[])]
    ),
    "lt-no-values": growth_plan(
        [Filter(member="demand_growth.year", operator="lt", values=[])]
    ),
    "lte-no-values": growth_plan(
        [Filter(member="demand_growth.year", operator="lte", values=[])]
    ),
    "set-with-values": plan(
        filters=[Filter(member="demand.is_imputed", operator="set", values=["true"])]
    ),
    "notSet-with-values": plan(
        filters=[Filter(member="demand.imputation_code", operator="notSet", values=["ML"])]
    ),
    "year-two-digit": growth_plan(
        [Filter(member="demand_growth.year", operator="equals", values=["23"])]
    ),
    "year-five-digit": growth_plan(
        [Filter(member="demand_growth.year", operator="equals", values=["20233"])]
    ),
    "year-spelled-out": growth_plan(
        [Filter(member="demand_growth.year", operator="equals", values=["two-thousand"])]
    ),
}


@pytest.mark.parametrize("case", sorted(INVALID_FILTER_PLANS))
def test_invalid_filter_edges_rejected(case, views):
    assert validate_plan(INVALID_FILTER_PLANS[case], views)


def test_ba_code_mixed_valid_and_invalid_values_rejected(views):
    p = plan(
        filters=[
            Filter(member="demand.ba_code", operator="equals", values=["PJM", "MISO"])
        ]
    )
    violations = validate_plan(p, views)
    # Only the invalid value is flagged as bad; the message may still echo
    # the governed set (which contains PJM) for context.
    assert any("['MISO']" in v for v in violations)


# --- 3. order/limit abuse ---


@pytest.mark.parametrize(
    "limit,ok",
    [(0, False), (-1, False), (1, True), (5000, True), (5001, False)],
)
def test_limit_boundaries(limit, ok, views):
    violations = validate_plan(plan(limit=limit), views)
    assert (violations == []) == ok, f"limit={limit}: {violations}"


def test_order_by_filter_only_member_rejected(views):
    # A member used only in a filter is not selected; ordering by it must fail.
    p = plan(
        filters=[Filter(member="demand.is_imputed", operator="equals", values=["false"])],
        order=[Order(member="demand.is_imputed", direction="asc")],
    )
    violations = validate_plan(p, views)
    assert any("order member" in v for v in violations)


def test_order_by_selected_time_dimension_passes(views):
    p = plan(order=[Order(member="demand.datetime_utc", direction="asc")])
    assert validate_plan(p, views) == []


# --- 4. multi-violation plans: ALL violations reported, not just the first ---


def test_bad_measure_and_bad_ba_code_both_reported(views):
    p = plan(
        measures=["demand.carbon_intensity"],
        filters=[Filter(member="demand.ba_code", operator="equals", values=["MISO"])],
        order=[],
    )
    violations = validate_plan(p, views)
    assert len(violations) >= 2
    assert any("carbon_intensity" in v for v in violations)
    assert any("MISO" in v for v in violations)


# --- 5. governed data window bounds (2019-01-01..2026-05-03) ---
# Out-of-window requests must be refused by the validator, not just by the
# prompt's refusal policy. Refuse, never clip: clipping is silent repair.

OUT_OF_WINDOW_RANGES = {
    "fully-before": ["2016-01-01", "2018-12-31"],
    "fully-after": ["2027-01-01", "2027-12-31"],
    "straddles-start": ["2018-06-01", "2019-06-30"],
    # The rule-7 calendar-year shape for 2026 exceeds the window end; the
    # prompt tells the model to cap at 2026-05-03 instead.
    "straddles-end": ["2026-01-01", "2026-12-31"],
}


@pytest.mark.parametrize("case", sorted(OUT_OF_WINDOW_RANGES))
def test_out_of_window_date_range_rejected(case, views):
    p = plan(
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc", date_range=OUT_OF_WINDOW_RANGES[case]
        )
    )
    violations = validate_plan(p, views)
    assert any("window" in v for v in violations), f"{case}: {violations}"


def test_exact_window_date_range_valid(views):
    p = plan(
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc", date_range=["2019-01-01", "2026-05-03"]
        )
    )
    assert validate_plan(p, views) == []


# Year filters are bounded by the interval each operator implies: only
# operators that request out-of-window data are flagged (gt 2018 implies
# years >= 2019, so it is valid; notEquals excludes rather than requests).
YEAR_WINDOW_CASES = [
    ("equals", "2018", False),
    ("equals", "2019", True),
    ("equals", "2026", True),
    ("equals", "2027", False),
    ("gt", "2017", False),
    ("gt", "2018", True),
    ("gte", "2018", False),
    ("gte", "2019", True),
    ("lt", "2027", True),
    ("lt", "2028", False),
    ("lte", "2026", True),
    ("lte", "2027", False),
    ("notEquals", "2018", True),
]


@pytest.mark.parametrize("op,value,ok", YEAR_WINDOW_CASES)
def test_year_filter_window_bounds(op, value, ok, views):
    p = growth_plan([Filter(member="demand_growth.year", operator=op, values=[value])])
    violations = validate_plan(p, views)
    assert (violations == []) == ok, f"{op} {value}: {violations}"


def test_four_independent_violations_all_reported(views):
    p = QueryPlan(
        view="demand",
        measures=["demand.carbon_intensity"],
        dimensions=["demand.weather_zone"],
        filters=[Filter(member="demand.ba_code", operator="equals", values=["MISO"])],
        limit=0,
    )
    violations = validate_plan(p, views)
    assert len(violations) >= 4
    assert any("carbon_intensity" in v for v in violations)
    assert any("weather_zone" in v for v in violations)
    assert any("MISO" in v for v in violations)
    assert any("limit" in v for v in violations)
