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
    """Poll until the batch has ended, printing progress."""
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
