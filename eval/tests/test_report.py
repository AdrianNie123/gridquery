# Tests for eval/report.py: the report renders only what the artifact
# contains, formats accuracies and failure modes exactly, and is
# deterministic. Offline, no API key needed.

import pytest

from eval.artifact import PRICING_BASIS, build_artifact
from eval.report import render_report, write_report
from eval.score import FAILURE_MODES, QuestionResult

USAGE = {
    "input_tokens": 1200,
    "output_tokens": 340,
    "cache_read_input_tokens": 7780,
    "cache_creation_input_tokens": 0,
}


def make_result(
    id,
    expected_kind,
    *,
    actual_kind,
    passed,
    checks=None,
    failure_mode=None,
    detail="",
    expected_metric=None,
    actual_metric=None,
):
    return QuestionResult(
        id=id,
        question=f"Question text for {id}?",
        expected_kind=expected_kind,
        actual_kind=actual_kind,
        expected_metric=expected_metric,
        actual_metric=actual_metric,
        checks=checks or {},
        passed=passed,
        failure_mode=failure_mode,
        detail=detail,
        usage=dict(USAGE),
    )


@pytest.fixture(scope="module")
def results():
    # 6 questions, 3 passed: overall 50.0%, refusal 1/3 = 33.3%.
    return [
        make_result(
            "q01_total_demand_pass",
            "query",
            actual_kind="answer",
            passed=True,
            checks={"kind": True, "metric": True, "params": True, "period": True, "result": True},
            expected_metric="total_demand",
            actual_metric="total_demand",
        ),
        make_result(
            "q02_peak_demand_wrong_period",
            "query",
            actual_kind="answer",
            passed=False,
            checks={"kind": True, "metric": True, "params": True, "period": False, "result": False},
            failure_mode="wrong_period",
            detail="period ('interval', '2022-01-01', '2022-12-31') != ('interval', '2023-01-01', '2023-12-31')",
            expected_metric="peak_demand",
            actual_metric="peak_demand",
        ),
        make_result(
            "r01_refuse_pass",
            "refuse",
            actual_kind="refusal",
            passed=True,
            checks={"kind": True},
        ),
        make_result(
            "r02_refuse_answered",
            "refuse",
            actual_kind="answer",
            passed=False,
            checks={"kind": False},
            failure_mode="answered_should_have_refused",
            detail="expected refusal, got answer",
            actual_metric="total_demand",
        ),
        make_result(
            "r03_refuse_answered",
            "refuse",
            actual_kind="answer",
            passed=False,
            checks={"kind": False},
            failure_mode="answered_should_have_refused",
            detail="expected refusal, got answer",
            actual_metric="renewable_share",
        ),
        make_result(
            "c01_clarify_pass",
            "clarify",
            actual_kind="clarification",
            passed=True,
            checks={"kind": True},
        ),
    ]


@pytest.fixture(scope="module")
def artifact(results):
    return build_artifact(
        results,
        model="claude-haiku-4-5",
        batch_id="msgbatch_test123",
        golden_set_text="golden set fixture text",
        golden_results_text="pinned results fixture text",
        system_prompt="system prompt fixture text",
    )


@pytest.fixture(scope="module")
def report(artifact):
    return render_report(artifact)


def test_provenance_fields_present(artifact, report):
    assert artifact["run_id"] in report
    assert artifact["git_commit"] in report
    assert "claude-haiku-4-5" in report
    assert "msgbatch_test123" in report
    for key in ("golden_set_sha256", "golden_results_sha256", "system_prompt_sha256"):
        assert artifact[key][:12] in report


def test_composition_line(report):
    assert "6 questions: 2 query, 3 refuse, 1 clarify." in report


def test_accuracy_percentages(report):
    assert "| Overall | 50.0% |" in report
    assert "| Metric selection | 100.0% |" in report
    assert "| Result | 50.0% |" in report
    assert "| Refusal | 33.3% |" in report
    assert "| Clarify | 100.0% |" in report


def test_accuracy_na_when_denominator_is_zero(results):
    # No refuse or clarify questions: those accuracies are None in the
    # artifact and must render as n/a, never as a number.
    queries_only = [r for r in results if r.expected_kind == "query"]
    artifact = build_artifact(
        queries_only,
        model="claude-haiku-4-5",
        batch_id=None,
        golden_set_text="g",
        golden_results_text="r",
        system_prompt="s",
    )
    report = render_report(artifact)
    assert "| Refusal | n/a |" in report
    assert "| Clarify | n/a |" in report
    assert "batch `n/a`" in report


def test_failure_mode_table_complete_with_zeros(report):
    expected_counts = {mode: 0 for mode in FAILURE_MODES}
    expected_counts["wrong_period"] = 1
    expected_counts["answered_should_have_refused"] = 2
    for mode in FAILURE_MODES:
        assert f"| {mode} | {expected_counts[mode]} |" in report


def test_failure_mode_order_prd_categories_first(report):
    positions = [report.index(f"| {mode} |") for mode in FAILURE_MODES]
    assert positions == sorted(positions)


def test_failed_questions_detailed_passed_absent(report):
    assert "### q02_peak_demand_wrong_period" in report
    assert "### r02_refuse_answered" in report
    assert "### r03_refuse_answered" in report
    # Passed questions do not appear anywhere in the report.
    assert "q01_total_demand_pass" not in report
    assert "r01_refuse_pass" not in report
    assert "c01_clarify_pass" not in report
    # Failed-question detail: expected vs actual kind and metric,
    # failure mode, and the detail string.
    assert "Question text for q02_peak_demand_wrong_period?" in report
    assert "- Expected: kind `query`, metric `peak_demand`" in report
    assert "- Actual: kind `answer`, metric `peak_demand`" in report
    assert "- Failure mode: `wrong_period`" in report
    assert "!= ('interval', '2023-01-01', '2023-12-31')" in report
    assert "- Expected: kind `refuse`, metric `n/a`" in report


def test_no_failures_renders_single_sentence(results):
    all_passed = [r for r in results if r.passed]
    artifact = build_artifact(
        all_passed,
        model="claude-haiku-4-5",
        batch_id="msgbatch_allpass",
        golden_set_text="g",
        golden_results_text="r",
        system_prompt="s",
    )
    report = render_report(artifact)
    assert "No questions failed in this run." in report
    assert "### " not in report.split("## Failed questions")[1].split("## Cost")[0]


def test_usage_section(artifact, report):
    usage = artifact["usage"]
    assert f"| Input tokens | {usage['input_tokens']:,} |" in report
    assert f"| Output tokens | {usage['output_tokens']:,} |" in report
    assert f"| Cache read input tokens | {usage['cache_read_input_tokens']:,} |" in report
    assert f"| Cache creation input tokens | {usage['cache_creation_input_tokens']:,} |" in report
    assert f"${usage['estimated_cost_usd']:.4f} USD." in report
    assert PRICING_BASIS in report


def test_style_no_em_dashes(report):
    assert "—" not in report


def test_deterministic(artifact):
    assert render_report(artifact) == render_report(artifact)


def test_write_report(artifact, tmp_path):
    path = tmp_path / "eval_report.md"
    written = write_report(artifact, path=path)
    assert written == path
    assert path.read_text() == render_report(artifact)
