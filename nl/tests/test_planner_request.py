"""Live/batch request equivalence for the planner (offline, no API key).

The Phase 5 batch runner submits build_request_params per custom_id; the
live path splats the same dict into messages.create. These tests capture
the actual outgoing HTTP bodies through a mock transport and prove:

1. the live path sends exactly build_request_params, and
2. that body is byte-identical to what the SDK's messages.parse with
   output_format=PlannerResponse (the pre-refactor path) would send,

so the eval harness measures the shipped system and the cached prefix is
unchanged by the refactor.
"""

import json

import anthropic
import httpx
import pytest

from nl.catalog import build_system_prompt
from nl.planner import MAX_TOKENS, MODEL, build_request_params, parse_planner_text, plan_question
from nl.schema import PlannerResponse

_REFUSAL_JSON = json.dumps(
    {"outcome": {"action": "refuse", "reason": "not governed"}}
)

_CANNED_MESSAGE = {
    "id": "msg_offline_test",
    "type": "message",
    "role": "assistant",
    "model": MODEL,
    "content": [{"type": "text", "text": _REFUSAL_JSON}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 1, "output_tokens": 1},
}


def _capturing_client(captured: list[dict]) -> anthropic.Anthropic:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=_CANNED_MESSAGE)

    return anthropic.Anthropic(
        api_key="offline-test-key",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.fixture(scope="module")
def system_prompt(views):
    return build_system_prompt(views)


def test_live_path_sends_exactly_the_shared_params(system_prompt):
    captured: list[dict] = []
    client = _capturing_client(captured)
    question = "Which balancing authority had the highest total demand in 2023?"

    parsed, usage = plan_question(question, system_prompt, client=client)

    assert len(captured) == 1
    assert captured[0] == build_request_params(question, system_prompt)
    assert parsed.outcome.action == "refuse"
    assert usage.input_tokens == 1


def test_body_identical_to_sdk_parse_path(system_prompt):
    """The refactor must not change the request the API sees.

    messages.parse with output_format=PlannerResponse was the Phase 4
    request path; the prefix it sent is what the prompt cache keys on.
    """
    question = "What was total demand in ERCOT in 2023?"

    captured_create: list[dict] = []
    plan_question(question, system_prompt, client=_capturing_client(captured_create))

    captured_parse: list[dict] = []
    _capturing_client(captured_parse).messages.parse(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": question}],
        output_format=PlannerResponse,
    )

    assert json.dumps(captured_create[0], sort_keys=True) == json.dumps(
        captured_parse[0], sort_keys=True
    )


def test_shared_params_are_byte_stable(system_prompt):
    """The batch runner serializes the params repeatedly; the cached
    prefix is a byte-level match, so two builds must serialize equal."""
    question = "How did peak demand change in PJM?"
    first = json.dumps(build_request_params(question, system_prompt), sort_keys=True)
    second = json.dumps(build_request_params(question, system_prompt), sort_keys=True)
    assert first == second


@pytest.mark.parametrize(
    "payload, action",
    [
        (
            {
                "outcome": {
                    "action": "query",
                    "metric": "total_demand",
                    "plan": {
                        "view": "demand",
                        "measures": ["demand.total_demand_mwh"],
                    },
                }
            },
            "query",
        ),
        ({"outcome": {"action": "refuse", "reason": "no governed metric"}}, "refuse"),
        ({"outcome": {"action": "clarify", "question": "Which region?"}}, "clarify"),
    ],
)
def test_parse_planner_text_outcomes(payload, action):
    parsed = parse_planner_text(json.dumps(payload))
    assert parsed.outcome.action == action
