# Offline tests for run-artifact assembly (eval/artifact.py): every
# aggregate the artifact reports is computed from per-question results,
# nothing hand-entered. Synthetic QuestionResult inputs only; no Cube,
# no API key, no filesystem writes.

import hashlib
import json

import pytest

from eval.artifact import _PRICE_PER_MTOK, aggregate_results, build_artifact
from eval.score import FAILURE_MODES, QuestionResult


def qr(id, expected_kind, actual_kind, passed, checks, failure_mode=None, usage=None):
    return QuestionResult(
        id=id,
        question=f"question for {id}",
        expected_kind=expected_kind,
        actual_kind=actual_kind,
        checks=checks,
        passed=passed,
        failure_mode=failure_mode,
        usage=usage or {},
    )


def synthetic_results():
    """3 query (1 pass, 1 wrong_metric, 1 unanswered), 2 refuse (1 pass),
    1 clarify (pass). Usage totals sum to round MTok numbers."""
    all_pass = {"kind": True, "metric": True, "params": True, "period": True, "result": True}
    wrong_metric = {"kind": True, "metric": False, "params": True, "period": True, "result": False}
    return [
        qr(
            "q1", "query", "answer", True, all_pass,
            usage={"input_tokens": 1_000_000, "output_tokens": 200_000},
        ),
        qr(
            "q2", "query", "answer", False, wrong_metric,
            failure_mode="wrong_metric",
            usage={
                "input_tokens": 1_000_000,
                "output_tokens": 200_000,
                "cache_read_input_tokens": 10_000_000,
            },
        ),
        # Unanswered query: the shipped system refused. No metric/result
        # checks exist, so it must count against both accuracies.
        qr(
            "q3", "query", "refusal", False, {"kind": False},
            failure_mode="refusal_should_have_answered",
            usage={"cache_creation_input_tokens": 800_000},
        ),
        qr("r1", "refuse", "refusal", True, {"kind": True}),
        qr(
            "r2", "refuse", "answer", False, {"kind": False},
            failure_mode="answered_should_have_refused",
        ),
        qr("c1", "clarify", "clarification", True, {"kind": True}),
    ]


# --- aggregate_results ---


def test_counts():
    agg = aggregate_results(synthetic_results())
    assert agg["counts"] == {"total": 6, "query": 3, "refuse": 2, "clarify": 1}


def test_accuracies():
    agg = aggregate_results(synthetic_results())["aggregate"]
    assert agg["overall_accuracy"] == round(3 / 6, 4)
    # Denominator is all query entries: the unanswered q3 counts as a
    # metric-selection failure even though it never produced a metric.
    assert agg["metric_selection_accuracy"] == round(1 / 3, 4)
    assert agg["result_accuracy"] == round(1 / 3, 4)
    assert agg["refusal_accuracy"] == round(1 / 2, 4)
    assert agg["clarify_accuracy"] == 1.0


def test_failure_mode_counts():
    modes = aggregate_results(synthetic_results())["failure_modes"]
    assert set(modes) == set(FAILURE_MODES)
    assert modes["wrong_metric"] == 1
    assert modes["refusal_should_have_answered"] == 1
    assert modes["answered_should_have_refused"] == 1
    for untriggered in (
        "wrong_parameter",
        "wrong_period",
        "clarified_should_have_answered",
        "answered_should_have_clarified",
    ):
        assert modes[untriggered] == 0


def test_usage_totals_and_estimated_cost():
    usage = aggregate_results(synthetic_results())["usage"]
    totals = {
        "input_tokens": 2_000_000,
        "output_tokens": 400_000,
        "cache_read_input_tokens": 10_000_000,
        "cache_creation_input_tokens": 800_000,
    }
    for key, expected in totals.items():
        assert usage[key] == expected
    expected_cost = sum(
        totals[k] * _PRICE_PER_MTOK[k] / 1_000_000 for k in totals
    )
    assert usage["estimated_cost_usd"] == round(expected_cost, 4)
    # With this pricing basis: 2*0.50 + 0.4*2.50 + 10*0.05 + 0.8*0.625.
    assert usage["estimated_cost_usd"] == pytest.approx(3.0)
    assert "pricing_basis" in usage


def test_none_usage_values_count_as_zero():
    results = [
        qr("q1", "query", "answer", True, {"kind": True}, usage={"input_tokens": None}),
    ]
    usage = aggregate_results(results)["usage"]
    assert usage["input_tokens"] == 0
    assert usage["estimated_cost_usd"] == 0.0


def test_refusal_accuracy_none_when_no_refuse_entries():
    queries_only = [r for r in synthetic_results() if r.expected_kind == "query"]
    agg = aggregate_results(queries_only)["aggregate"]
    assert agg["refusal_accuracy"] is None
    assert agg["clarify_accuracy"] is None


def test_empty_results_report_none_accuracies():
    agg = aggregate_results([])
    assert agg["counts"]["total"] == 0
    assert agg["aggregate"]["overall_accuracy"] is None


# --- build_artifact ---


def test_build_artifact_hashes_and_metadata():
    artifact = build_artifact(
        synthetic_results(),
        model="claude-haiku-4-5",
        batch_id="msgbatch_test",
        golden_set_text="golden set text",
        golden_results_text="pinned rows text",
        system_prompt="system prompt text",
    )
    assert artifact["model"] == "claude-haiku-4-5"
    assert artifact["batch_id"] == "msgbatch_test"
    assert artifact["golden_set_sha256"] == hashlib.sha256(b"golden set text").hexdigest()
    assert (
        artifact["golden_results_sha256"]
        == hashlib.sha256(b"pinned rows text").hexdigest()
    )
    assert (
        artifact["system_prompt_sha256"]
        == hashlib.sha256(b"system prompt text").hexdigest()
    )
    assert "run_id" in artifact
    assert "git_commit" in artifact
    # The aggregate block is embedded unchanged.
    assert artifact["counts"]["total"] == 6
    assert artifact["failure_modes"]["wrong_metric"] == 1


def test_build_artifact_per_question_dicts_round_trip():
    results = synthetic_results()
    artifact = build_artifact(
        results,
        model="claude-haiku-4-5",
        batch_id=None,
        golden_set_text="g",
        golden_results_text="p",
        system_prompt="s",
    )
    questions = artifact["questions"]
    assert len(questions) == len(results)
    assert all(isinstance(q, dict) for q in questions)
    first = questions[0]
    assert first["id"] == "q1"
    assert first["expected_kind"] == "query"
    assert first["checks"]["result"] is True
    assert first["failure_mode"] is None
    # asdict output must be JSON-serializable as-is (write_artifact contract).
    json.dumps(artifact)
