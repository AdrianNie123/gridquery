# Offline tests for the batch poller's give-up behavior: a batch that
# never ends must stop the poll with an actionable message instead of
# blocking forever. No API key, no network: the client is a stub.

from types import SimpleNamespace

import pytest

import eval.batch as batch


class StuckBatchClient:
    """messages.batches.retrieve always reports the batch in progress."""

    def __init__(self, batch_id):
        self.batch_id = batch_id
        retrieve = lambda _id: SimpleNamespace(
            processing_status="in_progress",
            request_counts=SimpleNamespace(succeeded=0, errored=0, processing=50),
        )
        self.messages = SimpleNamespace(
            batches=SimpleNamespace(retrieve=retrieve)
        )


def test_wait_for_batch_gives_up_with_resume_guidance(monkeypatch, capsys):
    monkeypatch.setattr(batch, "MAX_WAIT_SECONDS", 0)
    batch_id = "msgbatch_stuck"

    with pytest.raises(SystemExit) as excinfo:
        batch.wait_for_batch(batch_id, StuckBatchClient(batch_id))

    message = str(excinfo.value)
    assert batch_id in message
    assert "nothing is lost" in message
    assert f"uv run python -m eval run --resume {batch_id}" in message
    assert f"make eval-score RAW=eval/results/raw_{batch_id}.jsonl" in message


def test_wait_for_batch_returns_when_ended(monkeypatch):
    monkeypatch.setattr(batch, "MAX_WAIT_SECONDS", 0)
    client = StuckBatchClient("msgbatch_done")
    client.messages.batches.retrieve = lambda _id: SimpleNamespace(
        processing_status="ended",
        request_counts=SimpleNamespace(succeeded=50, errored=0, processing=0),
    )
    # An ended batch returns before the deadline check even at a 0s cap.
    assert batch.wait_for_batch("msgbatch_done", client) is None
