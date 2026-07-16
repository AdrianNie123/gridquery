"""CLI for the eval harness.

  uv run python -m eval pin                    # pin expected rows (Cube running)
  uv run python -m eval run                    # full batch run -> artifact + report
  uv run python -m eval score --raw <file>     # re-score a saved raw batch (no API cost)
  uv run python -m eval report                 # regenerate docs/eval_report.md from latest.json

run and score need Cube running (result checks execute the model's plans
through the shipped executor) and pinned results present. run needs
ANTHROPIC_API_KEY in .env; score and report do not touch the API.
"""

import argparse
import json
import sys
from pathlib import Path

import anthropic

from nl.catalog import build_system_prompt, fetch_meta, governed_views
from nl.interface import resolve_outcome
from nl.planner import MODEL, parse_planner_text

from eval.artifact import LATEST_PATH, build_artifact, write_artifact
from eval.batch import load_raw_results, run_batch
from eval.golden import GOLDEN_SET_PATH, load_golden_set, validate_golden_plans
from eval.pin import GOLDEN_RESULTS_PATH, load_pinned_results, pin_golden_results
from eval.score import score_question


def _load_and_validate(views: dict):
    entries = load_golden_set()
    problems = validate_golden_plans(entries, views)
    if problems:
        raise SystemExit(
            "golden plans failed validation against the governed surface:\n"
            + "\n".join(problems)
        )
    return entries


def _score_raw(entries, raw: dict[str, dict], views: dict) -> list:
    """Score every entry from raw batch output through the shipped
    pipeline (resolve_outcome). Missing, errored, or unparseable results
    are a hard stop (stop-and-ask trigger), never silently skipped."""
    pinned = load_pinned_results()
    broken = []
    results = []
    for entry in entries:
        line = raw.get(entry.id)
        if line is None or line.get("result_type") != "succeeded":
            broken.append(f"{entry.id}: {line.get('result_type') if line else 'missing'}")
            continue
        message = line["message"]
        texts = [b["text"] for b in message["content"] if b.get("type") == "text"]
        if not texts:
            broken.append(f"{entry.id}: no text block (stop_reason={message.get('stop_reason')})")
            continue
        try:
            parsed = parse_planner_text(texts[0])
        except Exception as e:
            broken.append(f"{entry.id}: unparseable planner output: {e}")
            continue
        answer = resolve_outcome(parsed, views, dict(message["usage"]))
        results.append(score_question(entry, answer, pinned.get(entry.id)))
    if broken:
        raise SystemExit(
            "batch results unusable for some questions; decide whether to "
            "resubmit before scoring a partial run:\n" + "\n".join(broken)
        )
    return results


def _write_outputs(results, *, batch_id: str | None, system_prompt: str) -> None:
    artifact = build_artifact(
        results,
        model=MODEL,
        batch_id=batch_id,
        golden_set_text=GOLDEN_SET_PATH.read_text(),
        golden_results_text=GOLDEN_RESULTS_PATH.read_text(),
        system_prompt=system_prompt,
    )
    path = write_artifact(artifact)
    from eval.report import write_report

    report_path = write_report(artifact)
    agg = artifact["aggregate"]
    print(f"artifact: {path}")
    print(f"report:   {report_path}")
    print(
        f"overall {agg['overall_accuracy']}, metric-selection "
        f"{agg['metric_selection_accuracy']}, result {agg['result_accuracy']}"
    )
    for mode, count in artifact["failure_modes"].items():
        if count:
            print(f"  {mode}: {count}")


def cmd_pin(_args) -> int:
    path = pin_golden_results()
    print(f"pinned expected rows -> {path}")
    return 0


def cmd_run(_args) -> int:
    views = governed_views(fetch_meta())
    entries = _load_and_validate(views)
    system_prompt = build_system_prompt(views)
    client = anthropic.Anthropic()
    batch_id, raw_path = run_batch(entries, system_prompt, client)
    print(f"raw results: {raw_path}")
    results = _score_raw(entries, load_raw_results(raw_path), views)
    _write_outputs(results, batch_id=batch_id, system_prompt=system_prompt)
    return 0


def cmd_score(args) -> int:
    raw_path = Path(args.raw)
    if not raw_path.exists():
        raise SystemExit(f"raw batch file not found: {raw_path}")
    views = governed_views(fetch_meta())
    entries = _load_and_validate(views)
    system_prompt = build_system_prompt(views)
    batch_id = raw_path.stem.removeprefix("raw_") or None
    results = _score_raw(entries, load_raw_results(raw_path), views)
    _write_outputs(results, batch_id=batch_id, system_prompt=system_prompt)
    return 0


def cmd_report(_args) -> int:
    if not LATEST_PATH.exists():
        raise SystemExit(f"no run artifact at {LATEST_PATH}; run `make eval` first")
    from eval.report import write_report

    path = write_report(json.loads(LATEST_PATH.read_text()))
    print(f"report: {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("pin").set_defaults(func=cmd_pin)
    sub.add_parser("run").set_defaults(func=cmd_run)
    score = sub.add_parser("score")
    score.add_argument("--raw", required=True, help="path to a saved raw_<batch_id>.jsonl")
    score.set_defaults(func=cmd_score)
    sub.add_parser("report").set_defaults(func=cmd_report)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
