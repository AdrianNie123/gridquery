# Offline tests for plan-to-Cube-query translation and deterministic
# answer rendering. No Cube, no API key.

from nl.answer import render_answer, render_clarification, render_refusal
from nl.executor import to_cube_query
from nl.schema import Filter, Order, QueryPlan, TimeDimension


def ranking_plan():
    return QueryPlan(
        view="demand",
        measures=["demand.total_demand_mwh"],
        dimensions=["demand.ba_code"],
        time_dimension=TimeDimension(
            dimension="demand.datetime_utc", date_range=["2023-01-01", "2023-12-31"]
        ),
        order=[Order(member="demand.total_demand_mwh", direction="desc")],
    )


def test_to_cube_query_shape():
    q = to_cube_query(ranking_plan())
    assert q == {
        "measures": ["demand.total_demand_mwh"],
        "dimensions": ["demand.ba_code"],
        "timeDimensions": [
            {
                "dimension": "demand.datetime_utc",
                "dateRange": ["2023-01-01", "2023-12-31"],
            }
        ],
        "order": {"demand.total_demand_mwh": "desc"},
    }


def test_to_cube_query_filters_and_limit():
    p = QueryPlan(
        view="demand_growth",
        measures=["demand_growth.demand_yoy_growth"],
        filters=[
            Filter(member="demand_growth.year", operator="equals", values=["2023"]),
            Filter(member="demand_growth.is_complete_year", operator="set", values=[]),
        ],
        limit=10,
    )
    q = to_cube_query(p)
    assert q["filters"] == [
        {"member": "demand_growth.year", "operator": "equals", "values": ["2023"]},
        {"member": "demand_growth.is_complete_year", "operator": "set"},
    ]
    assert q["limit"] == 10


def test_render_answer_shows_metric_params_and_numbers():
    rows = [
        {"demand.ba_code": "PJM", "demand.total_demand_mwh": "812345678.9"},
        {"demand.ba_code": "ERCO", "demand.total_demand_mwh": "446791234.5"},
    ]
    ans = render_answer("total_demand", ranking_plan(), rows, usage={})
    assert ans.kind == "answer"
    assert "metric: total_demand" in ans.text
    assert "period 2023-01-01..2023-12-31" in ans.text
    assert "812,345,679" in ans.text  # thousands-formatted, from the rows, not the LLM
    assert "PJM" in ans.text
    # Demand slices without an is_imputed filter carry the imputation caveat.
    assert "imputed" in ans.text


def test_render_percentages_and_nulls():
    p = QueryPlan(
        view="generation_mix",
        measures=["generation_mix.oil_share"],
        dimensions=["generation_mix.ba_code"],
    )
    rows = [
        {"generation_mix.ba_code": "PJM", "generation_mix.oil_share": "0.0023"},
        {"generation_mix.ba_code": "ERCO", "generation_mix.oil_share": None},
    ]
    ans = render_answer("generation_mix_share", p, rows, usage={})
    assert "0.23%" in ans.text
    assert "null" in ans.text
    assert "petroleum" in ans.text  # ERCO absence caveat triggered by the null


def test_growth_answer_carries_partial_year_note():
    p = QueryPlan(
        view="demand_growth",
        measures=["demand_growth.demand_yoy_growth"],
        dimensions=["demand_growth.ba_code", "demand_growth.year"],
    )
    rows = [
        {
            "demand_growth.ba_code": "ERCO",
            "demand_growth.year": "2023",
            "demand_growth.demand_yoy_growth": "0.021",
        }
    ]
    ans = render_answer("demand_yoy_growth", p, rows, usage={})
    assert "2.10%" in ans.text
    assert "complete calendar years" in ans.text


def test_refusal_and_clarification_render():
    r = render_refusal("carbon intensity is deferred future work")
    assert r.kind == "refusal" and "carbon intensity" in r.text
    c = render_clarification("Which region do you mean?")
    assert c.kind == "clarification" and "Which region" in c.text
