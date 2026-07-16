"""Message Batches submission and collection for the eval run.

Each golden question becomes one batch request whose params come from
nl.planner.build_request_params, the same builder the live path splats
into messages.create, so the batched eval provably sends the request the
shipped system sends (locked decision; proven by
nl/tests/test_planner_request.py). Results are keyed by custom_id, never
by position, and the raw per-question output is persisted as JSONL so a
run can be re-scored without resubmitting (make eval-score).
"""

import json
import time
from pathlib import Path

import anthropic

from nl.planner import build_request_params

from eval.golden import GoldenEntry

RESULTS_DIR = Path(__file__).resolve().parent / "results"

POLL_SECONDS = 15
MAX_WAIT_SECONDS = 30 * 60


def submit_batch(
    entries: list[GoldenEntry],
    system_prompt: str,
    client: anthropic.Anthropic,
) -> str:
    """Submit one batch with every golden question. Returns the batch id."""
    requests = [
        {
            "custom_id": entry.id,
            "params": build_request_params(entry.question, system_prompt),
        }
        for entry in entries
    ]
    batch = client.messages.batches.create(requests=requests)
    return batch.id


def wait_for_batch(batch_id: str, client: anthropic.Anthropic) -> None:
    """Poll until the batch has ended, printing progress.

    Gives up after MAX_WAIT_SECONDS: the batch keeps processing server-side
    and nothing is lost, so a stuck poll should hand control back rather
    than block the terminal indefinitely."""
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while True:
        batch = client.messages.batches.retrieve(batch_id)
        counts = batch.request_counts
        print(
            f"batch {batch_id}: {batch.processing_status} "
            f"(succeeded {counts.succeeded}, errored {counts.errored}, "
            f"processing {counts.processing})"
        )
        if batch.processing_status == "ended":
            return
        if time.monotonic() >= deadline:
            raise SystemExit(
                f"batch {batch_id} still {batch.processing_status} after "
                f"{MAX_WAIT_SECONDS // 60} minutes of polling. It keeps "
                "processing server-side and nothing is lost. Resume with\n"
                f"  uv run python -m eval run --resume {batch_id}\n"
                "and once the raw results are collected, re-score for free with\n"
                f"  make eval-score RAW=eval/results/raw_{batch_id}.jsonl"
            )
        time.sleep(POLL_SECONDS)


def collect_batch(batch_id: str, client: anthropic.Anthropic) -> Path:
    """Stream batch results and persist them raw, one JSON line per
    question: {custom_id, result_type, message | error}."""
    RESULTS_DIR.mkdir(exist_ok=True)
    raw_path = RESULTS_DIR / f"raw_{batch_id}.jsonl"
    with raw_path.open("w") as handle:
        for item in client.messages.batches.results(batch_id):
            line = {"custom_id": item.custom_id, "result_type": item.result.type}
            if item.result.type == "succeeded":
                line["message"] = item.result.message.model_dump(mode="json")
            else:
                line["error"] = item.result.model_dump(mode="json")
            handle.write(json.dumps(line) + "\n")
    return raw_path


def load_raw_results(raw_path: Path) -> dict[str, dict]:
    """Read a persisted raw batch file back into {custom_id: line}."""
    results = {}
    for line in raw_path.read_text().splitlines():
        if not line.strip():
            continue
        parsed = json.loads(line)
        results[parsed["custom_id"]] = parsed
    return results


def run_batch(
    entries: list[GoldenEntry],
    system_prompt: str,
    client: anthropic.Anthropic,
) -> tuple[str, Path]:
    """Submit, wait, and persist. Returns (batch_id, raw_path)."""
    batch_id = submit_batch(entries, system_prompt, client)
    wait_for_batch(batch_id, client)
    raw_path = collect_batch(batch_id, client)
    return batch_id, raw_path
