"""Deterministic scoring of one planner outcome against a golden entry.

The scorer consumes the Answer produced by nl.interface.resolve_outcome,
so everything after the LLM call (validator, executor, renderer) is the
shipped code, never a reimplementation. Three independent checks per
query question (PRD 8.2): outcome kind, metric selection with
parameter-level predicates, and result match against pinned rows. Exact
plan match is deliberately not required: a year filter and a covering
date range are equivalent encodings of the same period and must both
pass, while an off-by-one period must fail as wrong_period.

Failure taxonomy (PRD 8.3): wrong_metric, wrong_parameter, wrong_period,
refusal_should_have_answered, answered_should_have_refused, plus the
clarify variants clarified_should_have_answered and
answered_should_have_clarified, reported alongside.
"""

import math
from dataclasses import dataclass, field

from nl.answer import Answer
from nl.catalog import DATA_WINDOW_END, DATA_WINDOW_START
from nl.schema import QueryPlan

from eval.golden import GoldenEntry, PeriodSpec

# Expected values are produced by the same engine over the same data, so
# agreement is near-exact; the tolerance absorbs float summation-order
# noise only. Never loosened without investigation (locked decision).
REL_TOL = 1e-6
ABS_TOL = 1e-9

FAILURE_MODES = (
    "wrong_metric",
    "wrong_parameter",
    "wrong_period",
    "refusal_should_have_answered",
    "answered_should_have_refused",
    "clarified_should_have_answered",
    "answered_should_have_clarified",
)

_KIND_TO_EXPECTED = {"query": "answer", "refuse": "refusal", "clarify": "clarification"}


@dataclass
class QuestionResult:
    id: str
    question: str
    expected_kind: str
    actual_kind: str
    expected_metric: str | None = None
    actual_metric: str | None = None
    actual_plan: dict | None = None
    checks: dict = field(default_factory=dict)
    passed: bool = False
    failure_mode: str | None = None
    detail: str = ""
    usage: dict = field(default_factory=dict)


# --- period canonicalization -------------------------------------------------


def _clamp(start: str, end: str) -> tuple[str, str]:
    return max(start, DATA_WINDOW_START), min(end, DATA_WINDOW_END)


def _years_to_interval(years: list[int]) -> tuple[str, str] | None:
    """Contiguous years -> the clamped date interval they cover; None if
    the year set is non-contiguous (compared as a set instead)."""
    ys = sorted(set(years))
    if ys != list(range(ys[0], ys[-1] + 1)):
        return None
    return _clamp(f"{ys[0]}-01-01", f"{ys[-1]}-12-31")


def canonical_period(plan: QueryPlan):
    """Reduce a plan's period constraints to a canonical form.

    Returns ("interval", start, end) for date-interval periods (ISO,
    inclusive, clamped to the governed window), ("years", frozenset) when
    the plan requests a non-contiguous year set, or the full-window
    interval when nothing constrains the period. Date ranges and year
    filters intersect when both are present.
    """
    start, end = DATA_WINDOW_START, DATA_WINDOW_END
    year_sets: list[set[int]] = []

    td = plan.time_dimension
    if td is not None and td.date_range:
        start, end = max(start, td.date_range[0]), min(end, td.date_range[1])

    for f in plan.filters:
        if not f.member.endswith(".year"):
            continue
        if f.operator == "equals" and f.values:
            year_sets.append({int(v) for v in f.values})
        elif f.operator == "gte" and f.values:
            start = max(start, f"{int(f.values[0])}-01-01")
        elif f.operator == "gt" and f.values:
            start = max(start, f"{int(f.values[0]) + 1}-01-01")
        elif f.operator == "lte" and f.values:
            end = min(end, f"{int(f.values[0])}-12-31")
        elif f.operator == "lt" and f.values:
            end = min(end, f"{int(f.values[0]) - 1}-12-31")
        # notEquals and set/notSet exclude rather than request; unbounded.

    if year_sets:
        years = set.intersection(*year_sets)
        interval = _years_to_interval(sorted(years))
        if interval is None:
            return ("years", frozenset(years))
        start, end = max(start, interval[0]), min(end, interval[1])

    return ("interval", start, end)


def expected_period(spec: PeriodSpec | None):
    """Canonical form of the period a golden entry declares."""
    if spec is None or spec.full_window:
        return ("interval", DATA_WINDOW_START, DATA_WINDOW_END)
    if spec.years is not None:
        interval = _years_to_interval(spec.years)
        if interval is None:
            return ("years", frozenset(spec.years))
        return ("interval", *interval)
    if spec.date_range is not None:
        return ("interval", *_clamp(spec.date_range[0], spec.date_range[1]))
    return ("interval", DATA_WINDOW_START, DATA_WINDOW_END)


# --- parameter checks ---------------------------------------------------------


def _short(member: str) -> str:
    return member.split(".", 1)[1] if "." in member else member


def _ba_filter_values(plan: QueryPlan) -> set[str] | None:
    """The BA set the plan restricts to; None if it uses a non-equals
    operator on ba_code (never equivalent to a golden restriction)."""
    values: set[str] = set()
    for f in plan.filters:
        if not f.member.endswith(".ba_code"):
            continue
        if f.operator != "equals":
            return None
        values.update(f.values)
    return values


ALL_BAS = {"PJM", "ERCO", "CISO"}


def check_params(entry: GoldenEntry, plan: QueryPlan) -> tuple[bool, bool, str]:
    """Returns (params_ok, period_ok, detail). Period is separated so a
    period miss classifies as wrong_period, not wrong_parameter."""
    checks = entry.checks
    golden = entry.golden_plan
    problems = []

    if plan.view != golden.view:
        problems.append(f"view {plan.view} != {golden.view}")

    missing = set(golden.measures) - set(plan.measures)
    if missing:
        problems.append(f"missing measures {sorted(missing)}")

    actual_bas = _ba_filter_values(plan)
    expected_bas = set(checks.ba_filter)
    if actual_bas is None:
        problems.append("non-equals operator on ba_code")
    else:
        # No restriction and an explicit all-three filter are the same slice.
        actual_norm = set() if actual_bas == ALL_BAS else actual_bas
        expected_norm = set() if expected_bas == ALL_BAS else expected_bas
        if actual_norm != expected_norm:
            problems.append(f"ba filter {sorted(actual_bas)} != {sorted(expected_bas)}")

    actual_groups = {_short(d) for d in plan.dimensions}
    if actual_groups != set(checks.group_by):
        problems.append(
            f"grouping {sorted(actual_groups)} != {sorted(checks.group_by)}"
        )

    period_ok = canonical_period(plan) == expected_period(checks.period)
    if not period_ok:
        problems.append(
            f"period {canonical_period(plan)} != {expected_period(checks.period)}"
        )

    params_ok = not [p for p in problems if not p.startswith("period ")]
    return params_ok, period_ok, "; ".join(problems)


def check_metric(entry: GoldenEntry, actual_metric: str | None) -> bool:
    if actual_metric is None:
        return False
    accepted = {entry.expected_metric, *entry.checks.metric_aliases}
    return actual_metric.strip().casefold() in {a.casefold() for a in accepted}


# --- row comparison -----------------------------------------------------------


def _cell(row: dict, member: str, granularity: str | None = None):
    """Look up a member's value in a Cube result row. Time dimensions with
    a granularity may appear under member.granularity as well."""
    if member in row:
        return row[member]
    if granularity is not None and f"{member}.{granularity}" in row:
        return row[f"{member}.{granularity}"]
    raise KeyError(member)


def _project(rows: list[dict], golden: QueryPlan):
    """Project rows onto the golden plan's columns: a dimension-key tuple
    (strings) and a measure dict (floats or None). Extra columns in the
    row are ignored; a missing golden column raises KeyError."""
    dim_cols = list(golden.dimensions)
    td = golden.time_dimension
    time_col = td.dimension if td is not None and td.granularity else None
    granularity = td.granularity if td is not None else None

    projected = []
    for row in rows:
        key = tuple(str(_cell(row, d)) for d in dim_cols)
        if time_col is not None:
            key += (str(_cell(row, time_col, granularity)),)
        measures = {}
        for m in golden.measures:
            value = _cell(row, m)
            measures[m] = None if value is None else float(value)
        projected.append((key, measures))
    return projected


def _measures_match(expected: dict, actual: dict) -> bool:
    for member, exp in expected.items():
        act = actual.get(member, "missing")
        if exp is None or act is None:
            # Null matches only null: absence of data is not zero.
            if exp is not act:
                return False
        elif act == "missing" or not math.isclose(
            exp, act, rel_tol=REL_TOL, abs_tol=ABS_TOL
        ):
            return False
    return True


def compare_rows(
    pinned: list[dict], actual: list[dict], golden: QueryPlan, ordered: bool
) -> tuple[bool, str]:
    """Compare actual rows to pinned rows over the golden plan's columns.

    Unordered comparison keys rows by their dimension tuple (a duplicate
    key on either side means the grain differs and fails); ordered
    comparison (rankings) requires the same sequence.
    """
    try:
        exp_rows = _project(pinned, golden)
        act_rows = _project(actual, golden)
    except KeyError as e:
        return False, f"missing column {e.args[0]} in result rows"

    if len(exp_rows) != len(act_rows):
        return False, f"row count {len(act_rows)} != {len(exp_rows)}"

    if ordered:
        for i, ((ek, em), (ak, am)) in enumerate(zip(exp_rows, act_rows)):
            if ek != ak:
                return False, f"row {i} key {ak} != {ek}"
            if not _measures_match(em, am):
                return False, f"row {i} measures differ for key {ek}"
        return True, ""

    exp_by_key = dict(exp_rows)
    act_by_key = dict(act_rows)
    if len(exp_by_key) != len(exp_rows) or len(act_by_key) != len(act_rows):
        return False, "duplicate dimension keys: result grain differs"
    if set(exp_by_key) != set(act_by_key):
        missing = sorted(set(exp_by_key) - set(act_by_key))
        extra = sorted(set(act_by_key) - set(exp_by_key))
        return False, f"row keys differ (missing {missing}, extra {extra})"
    for key, em in exp_by_key.items():
        if not _measures_match(em, act_by_key[key]):
            return False, f"measures differ for key {key}"
    return True, ""


# --- one question, one result -------------------------------------------------


def score_question(
    entry: GoldenEntry, answer: Answer, pinned_rows: list[dict] | None
) -> QuestionResult:
    """Score one resolved outcome against its golden entry.

    answer is the output of nl.interface.resolve_outcome for the batch-
    parsed planner response; pinned_rows are the expected rows for the
    entry's golden plan (None for refuse/clarify entries).
    """
    result = QuestionResult(
        id=entry.id,
        question=entry.question,
        expected_kind=entry.kind,
        actual_kind=answer.kind,
        expected_metric=entry.expected_metric,
        actual_metric=answer.metric,
        actual_plan=answer.plan.model_dump(exclude_none=True) if answer.plan else None,
        usage=answer.usage,
    )
    expected_kind = _KIND_TO_EXPECTED[entry.kind]
    kind_ok = answer.kind == expected_kind
    result.checks["kind"] = kind_ok

    if entry.kind != "query":
        # Refuse/clarify score on outcome kind alone (no LLM-as-judge in v1).
        result.passed = kind_ok
        if not kind_ok:
            result.failure_mode = (
                "answered_should_have_refused"
                if entry.kind == "refuse"
                else "answered_should_have_clarified"
            )
            result.detail = f"expected {expected_kind}, got {answer.kind}"
        return result

    if not kind_ok:
        # Validator-converted refusals land here too: the shipped system
        # refused a question it should have answered.
        result.failure_mode = (
            "refusal_should_have_answered"
            if answer.kind == "refusal"
            else "clarified_should_have_answered"
        )
        result.detail = answer.text
        return result

    metric_ok = check_metric(entry, answer.metric)
    params_ok, period_ok, param_detail = check_params(entry, answer.plan)
    rows_ok, row_detail = compare_rows(
        pinned_rows or [], answer.rows or [], entry.golden_plan, entry.checks.ordered
    )
    result.checks.update(
        {"metric": metric_ok, "params": params_ok, "period": period_ok, "result": rows_ok}
    )
    result.passed = metric_ok and params_ok and period_ok and rows_ok
    result.detail = "; ".join(d for d in (param_detail, row_detail) if d)

    if not result.passed:
        if not metric_ok:
            result.failure_mode = "wrong_metric"
        elif not period_ok:
            result.failure_mode = "wrong_period"
        else:
            result.failure_mode = "wrong_parameter"
    return result
