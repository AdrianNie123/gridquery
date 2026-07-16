"""Pin expected eval results by executing golden plans against Cube.

This is the only writer of expected numbers in the harness (integrity
rule 1): the hand-authored golden set carries plans, never values, and
this module produces eval/golden_results.json by running those plans
through the same executor the shipped pipeline uses, against the tested
Cube layer. Regeneration policy (docs/plans/phase5.md): re-pin after any
data re-landing and review the diff; a pin diff without a corresponding
data change is a stop-and-investigate event.
"""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from nl.catalog import fetch_meta, governed_views
from nl.executor import execute_plan

from eval.golden import GoldenEntry, load_golden_set, validate_golden_plans

GOLDEN_RESULTS_PATH = Path(__file__).resolve().parent / "golden_results.json"


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def pin_golden_results(
    entries: list[GoldenEntry] | None = None,
    path: Path = GOLDEN_RESULTS_PATH,
) -> Path:
    """Execute every golden plan and write the pinned rows, keyed by id."""
    if entries is None:
        entries = load_golden_set()

    views = governed_views(fetch_meta())
    problems = validate_golden_plans(entries, views)
    if problems:
        raise ValueError(
            "golden plans failed validation against the live governed surface:\n"
            + "\n".join(problems)
        )

    pinned = {}
    for entry in entries:
        if entry.golden_plan is None:
            continue
        pinned[entry.id] = execute_plan(entry.golden_plan)

    document = {
        "metadata": {
            "pinned_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": _git_commit(),
            "entries": len(pinned),
        },
        "results": pinned,
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return path


def load_pinned_results(path: Path = GOLDEN_RESULTS_PATH) -> dict[str, list[dict]]:
    return json.loads(path.read_text())["results"]
