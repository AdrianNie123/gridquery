# Offline tests for golden-set loading and structural validation
# (eval/golden.py). The loader must reject a malformed golden set before
# any API spend; a golden plan that is itself off the governed surface is
# a build error. No Cube, no API key.

import copy

import pytest
import yaml
from pydantic import ValidationError

from eval.golden import Checks, GoldenEntry, load_golden_set, validate_golden_plans
from nl.schema import QueryPlan

VALID_QUERY = {
    "id": "q01_total_demand_ranking_2023",
    "question": "Which balancing authority had the highest total demand in 2023?",
    "kind": "query",
    "expected_metric": "total_demand",
    "golden_plan": {
        "view": "demand",
        "measures": ["demand.total_demand_mwh"],
        "dimensions": ["demand.ba_code"],
        "time_dimension": {
            "dimension": "demand.datetime_utc",
            "date_range": ["2023-01-01", "2023-12-31"],
        },
        "order": [{"member": "demand.total_demand_mwh", "direction": "desc"}],
    },
    "checks": {
        "ba_filter": [],
        "group_by": ["ba_code"],
        "period": {"years": [2023]},
        "ordered": True,
    },
}

VALID_REFUSE = {
    "id": "r01_prices",
    "question": "What was the average wholesale electricity price in ERCOT?",
    "kind": "refuse",
}

VALID_CLARIFY = {
    "id": "c01_ambiguous_region",
    "question": "How much demand was there in the West?",
    "kind": "clarify",
}


def write_golden(tmp_path, entries):
    path = tmp_path / "golden_set.yaml"
    path.write_text(yaml.safe_dump(entries, sort_keys=False))
    return path


# --- loading valid entries ---


def test_valid_entries_load(tmp_path):
    path = write_golden(
        tmp_path, [copy.deepcopy(VALID_QUERY), VALID_REFUSE, VALID_CLARIFY]
    )
    entries = load_golden_set(path)
    assert [e.id for e in entries] == [
        "q01_total_demand_ranking_2023",
        "r01_prices",
        "c01_ambiguous_region",
    ]
    query = entries[0]
    assert query.kind == "query"
    assert isinstance(query.golden_plan, QueryPlan)
    assert query.golden_plan.time_dimension.date_range == ["2023-01-01", "2023-12-31"]
    assert query.checks.ordered is True
    assert query.checks.period.years == [2023]
    refuse = entries[1]
    assert refuse.kind == "refuse"
    assert refuse.golden_plan is None and refuse.checks is None


def test_non_list_yaml_raises(tmp_path):
    path = tmp_path / "golden_set.yaml"
    path.write_text(yaml.safe_dump({"id": "not-a-list"}))
    with pytest.raises(ValueError, match="YAML list"):
        load_golden_set(path)


# --- structural defects ---


def test_duplicate_ids_raise(tmp_path):
    path = write_golden(
        tmp_path, [copy.deepcopy(VALID_QUERY), copy.deepcopy(VALID_QUERY)]
    )
    with pytest.raises(ValueError, match="duplicate golden ids"):
        load_golden_set(path)


@pytest.mark.parametrize("missing_field", ["expected_metric", "golden_plan", "checks"])
def test_query_entry_missing_required_field_raises(tmp_path, missing_field):
    entry = copy.deepcopy(VALID_QUERY)
    del entry[missing_field]
    path = write_golden(tmp_path, [entry])
    with pytest.raises(ValueError, match=missing_field):
        load_golden_set(path)


@pytest.mark.parametrize("base", [VALID_REFUSE, VALID_CLARIFY], ids=["refuse", "clarify"])
@pytest.mark.parametrize("extra_field", ["golden_plan", "checks"])
def test_refuse_and_clarify_entries_must_not_carry_plan_or_checks(
    tmp_path, base, extra_field
):
    entry = copy.deepcopy(base)
    entry[extra_field] = copy.deepcopy(VALID_QUERY[extra_field])
    path = write_golden(tmp_path, [entry])
    with pytest.raises(ValueError, match="must not carry a plan or checks"):
        load_golden_set(path)


# --- plan validation against the governed surface ---


def test_governed_golden_plan_passes_validator(views):
    entry = GoldenEntry.model_validate(VALID_QUERY)
    assert validate_golden_plans([entry], views) == []


def test_refuse_and_clarify_entries_skipped_by_plan_validation(views):
    entries = [
        GoldenEntry.model_validate(VALID_REFUSE),
        GoldenEntry.model_validate(VALID_CLARIFY),
    ]
    assert validate_golden_plans(entries, views) == []


def test_non_governed_member_caught_by_plan_validation(views):
    entry = GoldenEntry(
        id="q_bad_member",
        question="Total made-up demand?",
        kind="query",
        expected_metric="total_demand",
        golden_plan=QueryPlan(view="demand", measures=["demand.made_up_measure"]),
        checks=Checks(),
    )
    problems = validate_golden_plans([entry], views)
    assert problems, "off-surface measure must be reported"
    assert all(p.startswith("q_bad_member: ") for p in problems)
    assert any("demand.made_up_measure" in p for p in problems)


def test_syntactically_invalid_plan_fails_pydantic(tmp_path):
    entry = copy.deepcopy(VALID_QUERY)
    entry["golden_plan"]["view"] = "raw_eia930_hourly"
    with pytest.raises(ValidationError):
        GoldenEntry.model_validate(entry)
    # The same defect raises through the loader too.
    path = write_golden(tmp_path, [entry])
    with pytest.raises(ValidationError):
        load_golden_set(path)
