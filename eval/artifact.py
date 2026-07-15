"""Run-artifact assembly: the single output contract of an eval run.

One JSON per run lands in eval/results/ and is copied to
eval/results/latest.json, which is the frozen path both docs/eval_report.md
(via eval/report.py) and the Phase 6 Streamlit eval page read. Every
aggregate number is computed here from the per-question results; nothing
downstream hand-enters a figure.
"""

import hashlib
import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from eval.score import FAILURE_MODES, QuestionResult

RESULTS_DIR = Path(__file__).resolve().parent / "results"
LATEST_PATH = RESULTS_DIR / "latest.json"

# Dated pricing basis for the estimated cost line. The authoritative
# numbers in the artifact are the token counters returned by the API.
PRICING_BASIS = "claude-haiku-4-5 Batches API, 2026-07: $0.50/$2.50 per MTok in/out, cache read $0.05, cache write (5m) $0.625"
_PRICE_PER_MTOK = {
    "input_tokens": 0.50,
    "output_tokens": 2.50,
    "cache_read_input_tokens": 0.05,
    "cache_creation_input_tokens": 0.625,
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _accuracy(passed: int, total: int) -> float | None:
    return round(passed / total, 4) if total else None


def aggregate_results(results: list[QuestionResult]) -> dict:
    """Compute every aggregate the artifact reports from the per-question
    results. The two PRD 8.2 check types (metric selection, result) are
    reported separately in addition to overall pass/fail."""
    by_kind = {k: [r for r in results if r.expected_kind == k] for k in ("query", "refuse", "clarify")}
    queries = by_kind["query"]
    answered = [r for r in queries if r.checks.get("kind")]

    failure_modes = {mode: 0 for mode in FAILURE_MODES}
    for r in results:
        if r.failure_mode:
            failure_modes[r.failure_mode] += 1

    usage_totals = {key: 0 for key in _PRICE_PER_MTOK}
    for r in results:
        for key in usage_totals:
            usage_totals[key] += r.usage.get(key) or 0
    cost = sum(usage_totals[k] * _PRICE_PER_MTOK[k] / 1_000_000 for k in usage_totals)

    return {
        "counts": {
            "total": len(results),
            "query": len(queries),
            "refuse": len(by_kind["refuse"]),
            "clarify": len(by_kind["clarify"]),
        },
        "aggregate": {
            "overall_accuracy": _accuracy(sum(r.passed for r in results), len(results)),
            "metric_selection_accuracy": _accuracy(
                sum(r.checks.get("metric", False) for r in answered), len(queries)
            ),
            "result_accuracy": _accuracy(
                sum(r.checks.get("result", False) for r in answered), len(queries)
            ),
            "refusal_accuracy": _accuracy(
                sum(r.passed for r in by_kind["refuse"]), len(by_kind["refuse"])
            ),
            "clarify_accuracy": _accuracy(
                sum(r.passed for r in by_kind["clarify"]), len(by_kind["clarify"])
            ),
        },
        "failure_modes": failure_modes,
        "usage": {
            **usage_totals,
            "estimated_cost_usd": round(cost, 4),
            "pricing_basis": PRICING_BASIS,
        },
    }


def build_artifact(
    results: list[QuestionResult],
    *,
    model: str,
    batch_id: str | None,
    golden_set_text: str,
    golden_results_text: str,
    system_prompt: str,
) -> dict:
    return {
        "run_id": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_commit": _git_commit(),
        "model": model,
        "batch_id": batch_id,
        "golden_set_sha256": _sha256(golden_set_text),
        "golden_results_sha256": _sha256(golden_results_text),
        "system_prompt_sha256": _sha256(system_prompt),
        **aggregate_results(results),
        "questions": [asdict(r) for r in results],
    }


def write_artifact(artifact: dict) -> Path:
    """Write the timestamped artifact and refresh latest.json."""
    RESULTS_DIR.mkdir(exist_ok=True)
    stamp = artifact["run_id"].replace(":", "").replace("-", "")
    path = RESULTS_DIR / f"run_{stamp}.json"
    text = json.dumps(artifact, indent=2)
    path.write_text(text)
    LATEST_PATH.write_text(text)
    return path
