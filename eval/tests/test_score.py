# Offline tests for the deterministic scorer (eval/score.py): period
# canonicalization, parameter/metric checks, row comparison semantics,
# and end-to-end classification of one outcome per failure mode in the
# PRD 8.3 taxonomy. No Cube, no API key.

import copy

import pytest

from eval.golden import Checks, GoldenEntry, PeriodSpec
from eval.score import (
    canonical_period,
    check_metric,
    check_params,
    compare_rows,
    expected_period,
    score_question,
)
from nl.answer import Answer
from nl.catalog import DATA_WINDOW_END, DATA_WINDOW_START
from nl.schema import Filter, QueryPlan, TimeDimension

FULL_WINDOW = ("interval", DATA_WINDOW_START, DATA_WINDOW_END)


def demand_plan(**overrides):
    """A known-good baseline plan; override fields per test."""
    base = dict(
        view="demand",
        measures=["demand.total_demand_mwh"],
        dimensions=["demand.ba_code"],
        filters=[],
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc",
            date_range=["2023-01-01", "2023-12-31"],
        ),
    )
    base.update(overrides)
    return QueryPlan(**base)


def year_filter(operator, *values):
    return Filter(
        member="demand_growth.year", operator=operator, values=[str(v) for v in values]
    )


def growth_plan(*filters):
    return QueryPlan(
        view="demand_growth",
        measures=["demand_growth.demand_yoy_growth"],
        dimensions=["demand_growth.ba_code", "demand_growth.year"],
        filters=list(filters),
    )


def query_entry(**overrides):
    base = dict(
        id="q_total_demand_2023",
        question="Which balancing authority had the highest total demand in 2023?",
        kind="query",
        expected_metric="total_demand",
        golden_plan=demand_plan(),
        checks=Checks(ba_filter=[], group_by=["ba_code"], period=PeriodSpec(years=[2023])),
    )
    base.update(overrides)
    return GoldenEntry(**base)


def pinned_rows():
    return [
        {"demand.ba_code": "ERCO", "demand.total_demand_mwh": 446793938.1},
        {"demand.ba_code": "PJM", "demand.total_demand_mwh": 812000000.0},
        {"demand.ba_code": "CISO", "demand.total_demand_mwh": 230000000.0},
    ]


def answer_for(entry, rows, metric=None, plan=None):
    return Answer(
        kind="answer",
        text="rendered elsewhere",
        metric=metric or entry.expected_metric,
        plan=plan or entry.golden_plan,
        rows=rows,
    )


# --- period canonicalization ---


def test_year_equals_filter_matches_covering_date_range():
    by_filter = growth_plan(year_filter("equals", 2023))
    by_range = demand_plan()
    assert canonical_period(by_filter) == ("interval", "2023-01-01", "2023-12-31")
    assert canonical_period(by_filter) == canonical_period(by_range)
    assert canonical_period(by_range) == expected_period(PeriodSpec(years=[2023]))


def test_multi_year_contiguous_equals_matches_year_spec():
    plan = growth_plan(year_filter("equals", 2019, 2020, 2021))
    assert canonical_period(plan) == ("interval", "2019-01-01", "2021-12-31")
    assert canonical_period(plan) == expected_period(PeriodSpec(years=[2019, 2020, 2021]))


def test_off_by_one_year_mismatches():
    plan = growth_plan(year_filter("equals", 2022))
    assert canonical_period(plan) != expected_period(PeriodSpec(years=[2023]))


@pytest.mark.parametrize(
    "operator, value, expected",
    [
        ("gte", 2019, ("interval", "2019-01-01", DATA_WINDOW_END)),
        ("gt", 2018, ("interval", "2019-01-01", DATA_WINDOW_END)),
        ("lte", 2023, ("interval", DATA_WINDOW_START, "2023-12-31")),
        ("lt", 2024, ("interval", DATA_WINDOW_START, "2023-12-31")),
    ],
)
def test_year_range_operators(operator, value, expected):
    assert canonical_period(growth_plan(year_filter(operator, value))) == expected


def test_gt_is_equivalent_to_gte_of_next_year():
    assert canonical_period(growth_plan(year_filter("gt", 2018))) == canonical_period(
        growth_plan(year_filter("gte", 2019))
    )


def test_not_equals_year_filter_is_unbounded():
    # notEquals excludes rather than requests: it constrains nothing.
    plan = growth_plan(year_filter("notEquals", 2020))
    assert canonical_period(plan) == FULL_WINDOW


def test_year_2026_clamps_to_window_end():
    plan = growth_plan(year_filter("equals", 2026))
    assert canonical_period(plan) == ("interval", "2026-01-01", DATA_WINDOW_END)
    assert canonical_period(plan) == expected_period(PeriodSpec(years=[2026]))


def test_full_window_spec_and_none_both_give_full_window():
    assert expected_period(PeriodSpec(full_window=True)) == FULL_WINDOW
    assert expected_period(None) == FULL_WINDOW
    # An unconstrained plan matches both.
    plan = demand_plan(time_dimension=None)
    assert canonical_period(plan) == FULL_WINDOW


def test_non_contiguous_years_compare_as_a_set():
    plan = growth_plan(year_filter("equals", 2019, 2021))
    assert canonical_period(plan) == ("years", frozenset({2019, 2021}))
    assert canonical_period(plan) == expected_period(PeriodSpec(years=[2019, 2021]))
    assert canonical_period(plan) != expected_period(PeriodSpec(years=[2019, 2022]))
    assert canonical_period(plan) != expected_period(PeriodSpec(years=[2019, 2020, 2021]))


def test_date_range_intersects_with_year_filter():
    plan = QueryPlan(
        view="demand_growth",
        measures=["demand_growth.demand_yoy_growth"],
        filters=[year_filter("equals", 2023)],
        time_dimension=TimeDimension(
            dimension="demand_growth.year",
            date_range=["2023-06-01", "2024-12-31"],
        ),
    )
    assert canonical_period(plan) == ("interval", "2023-06-01", "2023-12-31")


# --- check_params ---


def test_ba_filter_set_match():
    entry = query_entry(
        checks=Checks(ba_filter=["ERCO"], group_by=["ba_code"], period=PeriodSpec(years=[2023]))
    )
    plan = demand_plan(
        filters=[Filter(member="demand.ba_code", operator="equals", values=["ERCO"])]
    )
    params_ok, period_ok, detail = check_params(entry, plan)
    assert params_ok and period_ok
    assert detail == ""


def test_equals_filter_on_all_three_bas_equivalent_to_no_filter():
    entry = query_entry()  # checks.ba_filter == []
    plan = demand_plan(
        filters=[
            Filter(
                member="demand.ba_code",
                operator="equals",
                values=["PJM", "ERCO", "CISO"],
            )
        ]
    )
    params_ok, _, detail = check_params(entry, plan)
    assert params_ok, detail


def test_non_equals_operator_on_ba_code_fails():
    entry = query_entry(
        checks=Checks(ba_filter=["ERCO"], group_by=["ba_code"], period=PeriodSpec(years=[2023]))
    )
    plan = demand_plan(
        filters=[Filter(member="demand.ba_code", operator="notEquals", values=["PJM"])]
    )
    params_ok, _, detail = check_params(entry, plan)
    assert not params_ok
    assert "non-equals operator on ba_code" in detail


def test_grouping_set_match_with_fully_qualified_dimensions():
    entry = query_entry()  # checks.group_by == ["ba_code"]
    ok_plan = demand_plan(dimensions=["demand.ba_code"])
    params_ok, _, detail = check_params(entry, ok_plan)
    assert params_ok, detail

    ungrouped = demand_plan(dimensions=[])
    params_ok, _, detail = check_params(entry, ungrouped)
    assert not params_ok
    assert "grouping" in detail


def test_missing_expected_measure_fails():
    plan = demand_plan(measures=["demand.peak_demand_mwh"])
    params_ok, _, detail = check_params(query_entry(), plan)
    assert not params_ok
    assert "missing measures" in detail


def test_extra_measures_pass():
    plan = demand_plan(measures=["demand.total_demand_mwh", "demand.hours"])
    params_ok, _, detail = check_params(query_entry(), plan)
    assert params_ok, detail


def test_wrong_view_fails():
    plan = QueryPlan(
        view="generation_mix",
        measures=["demand.total_demand_mwh"],
        dimensions=["demand.ba_code"],
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc", date_range=["2023-01-01", "2023-12-31"]
        ),
    )
    params_ok, _, detail = check_params(query_entry(), plan)
    assert not params_ok
    assert "view generation_mix != demand" in detail


# --- check_metric ---


@pytest.mark.parametrize(
    "actual, expected_ok",
    [
        ("total_demand", True),
        ("TOTAL_DEMAND", True),
        ("  Total_Demand  ", True),
        ("peak_demand", False),
        (None, False),
    ],
)
def test_check_metric(actual, expected_ok):
    assert check_metric(query_entry(), actual) is expected_ok


def test_check_metric_accepts_aliases():
    entry = query_entry(
        checks=Checks(group_by=["ba_code"], period=PeriodSpec(years=[2023]), metric_aliases=["demand_total"])
    )
    assert check_metric(entry, "demand_total") is True
    assert check_metric(entry, "DEMAND_TOTAL") is True
    assert check_metric(entry, "something_else") is False


# --- compare_rows ---


def test_identical_rows_pass():
    golden = demand_plan()
    ok, detail = compare_rows(pinned_rows(), copy.deepcopy(pinned_rows()), golden, ordered=False)
    assert ok, detail


def test_string_typed_numerics_compare_as_floats():
    golden = demand_plan()
    pinned = [{"demand.ba_code": "ERCO", "demand.total_demand_mwh": 446793938.1}]
    actual = [{"demand.ba_code": "ERCO", "demand.total_demand_mwh": "446793938.1"}]
    ok, detail = compare_rows(pinned, actual, golden, ordered=False)
    assert ok, detail


def test_tolerance_passes_float_noise_but_fails_real_difference():
    golden = demand_plan()
    pinned = [{"demand.ba_code": "ERCO", "demand.total_demand_mwh": 446793938.1}]
    noisy = [
        {"demand.ba_code": "ERCO", "demand.total_demand_mwh": 446793938.1 * (1 + 1e-9)}
    ]
    ok, detail = compare_rows(pinned, noisy, golden, ordered=False)
    assert ok, detail

    off_by_tenth_percent = [
        {"demand.ba_code": "ERCO", "demand.total_demand_mwh": 446793938.1 * 1.001}
    ]
    ok, detail = compare_rows(pinned, off_by_tenth_percent, golden, ordered=False)
    assert not ok
    assert "measures differ" in detail


def test_null_matches_only_null():
    # Absence of data is not zero (the ERCO petroleum decision).
    golden = demand_plan()
    pinned = [{"demand.ba_code": "ERCO", "demand.total_demand_mwh": None}]
    ok, _ = compare_rows(
        pinned,
        [{"demand.ba_code": "ERCO", "demand.total_demand_mwh": 0}],
        golden,
        ordered=False,
    )
    assert not ok
    ok, detail = compare_rows(
        pinned,
        [{"demand.ba_code": "ERCO", "demand.total_demand_mwh": None}],
        golden,
        ordered=False,
    )
    assert ok, detail


def test_missing_golden_column_fails_and_names_the_column():
    golden = demand_plan()
    actual = [{"demand.ba_code": "ERCO"}]  # no measure column
    pinned = [{"demand.ba_code": "ERCO", "demand.total_demand_mwh": 1.0}]
    ok, detail = compare_rows(pinned, actual, golden, ordered=False)
    assert not ok
    assert "missing column demand.total_demand_mwh" in detail


def test_extra_columns_in_actual_rows_are_ignored():
    golden = demand_plan()
    actual = copy.deepcopy(pinned_rows())
    for row in actual:
        row["demand.hours"] = 8760
    ok, detail = compare_rows(pinned_rows(), actual, golden, ordered=False)
    assert ok, detail


def test_row_count_mismatch_fails():
    golden = demand_plan()
    ok, detail = compare_rows(pinned_rows(), pinned_rows()[:2], golden, ordered=False)
    assert not ok
    assert "row count 2 != 3" in detail


def test_ordered_comparison_requires_same_sequence():
    golden = demand_plan()
    swapped = [pinned_rows()[1], pinned_rows()[0], pinned_rows()[2]]
    ok, detail = compare_rows(pinned_rows(), swapped, golden, ordered=True)
    assert not ok
    assert "row 0 key" in detail
    # The same rows pass as a multiset when order is not pinned.
    ok, detail = compare_rows(pinned_rows(), swapped, golden, ordered=False)
    assert ok, detail


def test_duplicate_dimension_keys_fail_as_grain_mismatch():
    golden = demand_plan()
    pinned = pinned_rows()[:2]
    actual = [
        {"demand.ba_code": "ERCO", "demand.total_demand_mwh": 200000000.0},
        {"demand.ba_code": "ERCO", "demand.total_demand_mwh": 246793938.1},
    ]
    ok, detail = compare_rows(pinned, actual, golden, ordered=False)
    assert not ok
    assert "duplicate dimension keys" in detail


def test_time_dimension_column_resolves_via_granularity_fallback():
    golden = demand_plan(
        dimensions=[],
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc",
            granularity="year",
            date_range=["2019-01-01", "2020-12-31"],
        ),
    )
    # Cube may key the column as member.granularity; pinned and actual rows
    # using either key must resolve to the same dimension tuple.
    pinned = [
        {"demand.datetime_utc.year": "2019-01-01T00:00:00.000", "demand.total_demand_mwh": 1.5},
        {"demand.datetime_utc.year": "2020-01-01T00:00:00.000", "demand.total_demand_mwh": 2.5},
    ]
    actual = [
        {"demand.datetime_utc": "2019-01-01T00:00:00.000", "demand.total_demand_mwh": 1.5},
        {"demand.datetime_utc": "2020-01-01T00:00:00.000", "demand.total_demand_mwh": 2.5},
    ]
    ok, detail = compare_rows(pinned, actual, golden, ordered=False)
    assert ok, detail


# --- score_question: end-to-end classification ---


def test_all_checks_pass():
    entry = query_entry()
    answer = answer_for(entry, rows=pinned_rows())
    result = score_question(entry, answer, pinned_rows())
    assert result.passed is True
    assert result.failure_mode is None
    assert result.checks == {
        "kind": True,
        "metric": True,
        "params": True,
        "period": True,
        "result": True,
    }


def test_wrong_metric():
    entry = query_entry()
    answer = answer_for(entry, rows=pinned_rows(), metric="peak_demand")
    result = score_question(entry, answer, pinned_rows())
    assert result.passed is False
    assert result.failure_mode == "wrong_metric"
    assert result.checks["metric"] is False


def test_wrong_period():
    entry = query_entry()
    off_by_one = demand_plan(
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc", date_range=["2022-01-01", "2022-12-31"]
        )
    )
    answer = answer_for(entry, rows=pinned_rows(), plan=off_by_one)
    result = score_question(entry, answer, pinned_rows())
    assert result.passed is False
    assert result.failure_mode == "wrong_period"
    assert result.checks["period"] is False
    assert result.checks["params"] is True  # only the period is wrong


def test_wrong_parameter_when_params_look_right_but_rows_differ():
    # An extra is_imputed filter is invisible to the parameter predicates
    # but changes the rows; the result check catches it as wrong_parameter.
    entry = query_entry()
    filtered_plan = demand_plan(
        filters=[
            Filter(member="demand.is_imputed", operator="equals", values=["false"])
        ]
    )
    changed = copy.deepcopy(pinned_rows())
    changed[0]["demand.total_demand_mwh"] = 440000000.0
    answer = answer_for(entry, rows=changed, plan=filtered_plan)
    result = score_question(entry, answer, pinned_rows())
    assert result.passed is False
    assert result.failure_mode == "wrong_parameter"
    assert result.checks["metric"] is True
    assert result.checks["params"] is True
    assert result.checks["period"] is True
    assert result.checks["result"] is False


def test_refusal_on_query_entry_is_refusal_should_have_answered():
    entry = query_entry()
    answer = Answer(kind="refusal", text="Not answerable through the governed metrics: x")
    result = score_question(entry, answer, pinned_rows())
    assert result.passed is False
    assert result.failure_mode == "refusal_should_have_answered"
    assert result.detail == answer.text


def test_clarification_on_query_entry_is_clarified_should_have_answered():
    entry = query_entry()
    answer = Answer(kind="clarification", text="Clarification needed: which region?")
    result = score_question(entry, answer, pinned_rows())
    assert result.passed is False
    assert result.failure_mode == "clarified_should_have_answered"


def test_answer_on_refuse_entry_is_answered_should_have_refused():
    entry = GoldenEntry(id="r_prices", question="Average LMP in PJM?", kind="refuse")
    answer = answer_for(query_entry(), rows=pinned_rows())
    result = score_question(entry, answer, None)
    assert result.passed is False
    assert result.failure_mode == "answered_should_have_refused"


def test_answer_on_clarify_entry_is_answered_should_have_clarified():
    entry = GoldenEntry(id="c_region", question="Demand in the West?", kind="clarify")
    answer = answer_for(query_entry(), rows=pinned_rows())
    result = score_question(entry, answer, None)
    assert result.passed is False
    assert result.failure_mode == "answered_should_have_clarified"


def test_refusal_on_refuse_entry_passes():
    entry = GoldenEntry(id="r_prices", question="Average LMP in PJM?", kind="refuse")
    answer = Answer(kind="refusal", text="Not answerable through the governed metrics: prices")
    result = score_question(entry, answer, None)
    assert result.passed is True
    assert result.failure_mode is None
    assert result.checks == {"kind": True}


def test_clarification_on_clarify_entry_passes():
    entry = GoldenEntry(id="c_region", question="Demand in the West?", kind="clarify")
    answer = Answer(kind="clarification", text="Clarification needed: which BA?")
    result = score_question(entry, answer, None)
    assert result.passed is True
    assert result.failure_mode is None
