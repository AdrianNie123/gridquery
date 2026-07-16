"""Render docs/eval_report.md from a run artifact.

The run artifact (eval/results/latest.json, assembled by eval.artifact)
is the only source of numbers here. This module formats what the
artifact contains: it never computes a new figure and never hand-enters
one, so every number in the report traces back to the scored run.
Rendering is deterministic: the same artifact produces byte-identical
markdown.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = REPO_ROOT / "docs" / "eval_report.md"

# Fixed rendering order: the five PRD 8.3 failure categories first, then
# the two clarify variants reported alongside them.
_FAILURE_MODE_ORDER = (
    "wrong_metric",
    "wrong_parameter",
    "wrong_period",
    "refusal_should_have_answered",
    "answered_should_have_refused",
    "clarified_should_have_answered",
    "answered_should_have_clarified",
)

_ACCURACY_ROWS = (
    ("Overall", "overall_accuracy"),
    ("Metric selection", "metric_selection_accuracy"),
    ("Result", "result_accuracy"),
    ("Refusal", "refusal_accuracy"),
    ("Clarify", "clarify_accuracy"),
)

_TOKEN_LABELS = {
    "input_tokens": "Input tokens",
    "output_tokens": "Output tokens",
    "cache_read_input_tokens": "Cache read input tokens",
    "cache_creation_input_tokens": "Cache creation input tokens",
}


def _pct(value: float | None) -> str:
    """0.8571 -> '85.7%'; None (undefined, zero denominator) -> 'n/a'."""
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _hash12(value: str | None) -> str:
    return value[:12] if value else "n/a"


def _opt(value) -> str:
    return str(value) if value is not None else "n/a"


def _provenance(artifact: dict) -> list[str]:
    return [
        "Run `{run_id}`, commit `{commit}`, model `{model}`, batch `{batch}`.".format(
            run_id=artifact["run_id"],
            commit=artifact["git_commit"],
            model=artifact["model"],
            batch=_opt(artifact["batch_id"]),
        ),
        "",
        "Inputs (sha256, first 12 chars): golden set `{gs}`, "
        "pinned results `{gr}`, system prompt `{sp}`.".format(
            gs=_hash12(artifact["golden_set_sha256"]),
            gr=_hash12(artifact["golden_results_sha256"]),
            sp=_hash12(artifact["system_prompt_sha256"]),
        ),
    ]


def _composition(counts: dict) -> str:
    return (
        f"{counts['total']} questions: {counts['query']} query, "
        f"{counts['refuse']} refuse, {counts['clarify']} clarify."
    )


def _accuracy_section(aggregate: dict) -> list[str]:
    lines = ["| Check | Accuracy |", "|---|---|"]
    for label, key in _ACCURACY_ROWS:
        lines.append(f"| {label} | {_pct(aggregate[key])} |")
    lines += [
        "",
        "A query question passes overall only when all three checks pass: "
        "outcome kind, metric selection (including parameters and period), "
        "and result match against the pinned rows. Refuse and clarify "
        "questions score on outcome kind alone; there is no LLM-as-judge "
        "in v1, so the wording of a refusal or clarification is not graded.",
    ]
    return lines


def _failure_mode_section(failure_modes: dict) -> list[str]:
    lines = ["| Failure mode | Count |", "|---|---|"]
    for mode in _FAILURE_MODE_ORDER:
        lines.append(f"| {mode} | {failure_modes.get(mode, 0)} |")
    # Defensive: render any mode the artifact reports beyond the taxonomy
    # rather than silently dropping it.
    for mode in sorted(set(failure_modes) - set(_FAILURE_MODE_ORDER)):
        lines.append(f"| {mode} | {failure_modes[mode]} |")
    return lines


def _failed_question_section(question: dict) -> list[str]:
    return [
        f"### {question['id']}",
        "",
        f"Question: {question['question']}",
        "",
        "- Expected: kind `{ek}`, metric `{em}`".format(
            ek=question["expected_kind"], em=_opt(question.get("expected_metric"))
        ),
        "- Actual: kind `{ak}`, metric `{am}`".format(
            ak=question["actual_kind"], am=_opt(question.get("actual_metric"))
        ),
        f"- Failure mode: `{_opt(question.get('failure_mode'))}`",
        f"- Detail: {question.get('detail') or '(none)'}",
    ]


def _failed_questions(questions: list[dict]) -> list[str]:
    failed = [q for q in questions if not q["passed"]]
    if not failed:
        return ["No questions failed in this run."]
    lines: list[str] = []
    for i, question in enumerate(failed):
        if i:
            lines.append("")
        lines.extend(_failed_question_section(question))
    return lines


def _usage_section(usage: dict) -> list[str]:
    lines = ["| Counter | Total |", "|---|---|"]
    for key, value in usage.items():
        if key in ("estimated_cost_usd", "pricing_basis"):
            continue
        lines.append(f"| {_TOKEN_LABELS.get(key, key)} | {value:,} |")
    lines += [
        "",
        f"Estimated cost: ${usage['estimated_cost_usd']:.4f} USD.",
        "",
        f"Pricing basis: {usage['pricing_basis']}",
    ]
    return lines


_HOW_MEASURED = [
    "- The golden set (`eval/golden_set.yaml`) is hand-authored and "
    "contains no numbers.",
    "- Expected rows are pinned by executing the hand-authored golden "
    "plans against the tested Cube layer (`make eval-pin`); "
    "`eval/golden_results.json` is the only home of expected numbers.",
    "- Planner calls are sent through the Message Batches API with the "
    "same request body the live path uses "
    "(`nl.planner.build_request_params`).",
    "- Everything after the LLM call is the shipped pipeline: batch "
    "responses are resolved through `nl.interface.resolve_outcome` "
    "(validator, executor, renderer), not a reimplementation.",
    "- Scoring is deterministic. There is no LLM-as-judge in v1.",
    "- Regenerate this report with `make eval`; re-score a saved batch "
    "without API cost with `make eval-score`.",
]


def render_report(artifact: dict) -> str:
    """Render the full markdown for docs/eval_report.md from one artifact."""
    lines: list[str] = ["# GridQuery evaluation report", ""]
    lines.extend(_provenance(artifact))
    lines += ["", "## Composition", "", _composition(artifact["counts"])]
    lines += ["", "## Accuracy", ""]
    lines.extend(_accuracy_section(artifact["aggregate"]))
    lines += ["", "## Failure modes", ""]
    lines.extend(_failure_mode_section(artifact["failure_modes"]))
    lines += ["", "## Failed questions", ""]
    lines.extend(_failed_questions(artifact["questions"]))
    lines += ["", "## Cost and usage", ""]
    lines.extend(_usage_section(artifact["usage"]))
    lines += ["", "## How this was measured", ""]
    lines.extend(_HOW_MEASURED)
    lines.append("")
    return "\n".join(lines)


def write_report(artifact: dict, path: Path = REPORT_PATH) -> Path:
    """Render the report and write it to path (docs/eval_report.md by
    default). Returns the path written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(artifact))
    return path
