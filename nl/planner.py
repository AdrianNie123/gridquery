"""The one LLM call: question -> typed outcome.

claude-haiku-4-5 with structured outputs. The system prompt (grounding
rules + governed surface + metric catalog) is the static prefix and
carries a cache_control breakpoint; the question is the only volatile
content and comes after it. No agentic loop, no tools: the model's whole
job is constrained selection and parameterization.

The request body is assembled by build_request_params, which is shared
with the Phase 5 eval harness's batch runner. Both paths must send
byte-identical requests so the eval measures the shipped system.
"""

import anthropic
from anthropic import transform_schema
from pydantic import TypeAdapter

from nl.schema import PlannerResponse

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 2048

# The structured-output format, transformed exactly the way the SDK's
# messages.parse transforms an output_format type. Computed once: it sits
# in the cached prefix, so it must be byte-stable across calls.
OUTPUT_FORMAT = {
    "type": "json_schema",
    "schema": transform_schema(TypeAdapter(PlannerResponse).json_schema()),
}


def build_request_params(question: str, system_prompt: str) -> dict:
    """The canonical Messages API body for one planner call.

    The live path (plan_question) splats this into messages.create; the
    batch path (eval/batch.py) submits it per custom_id. Anything added
    here reaches both paths or neither.
    """
    return {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        "messages": [{"role": "user", "content": question}],
        "output_config": {"format": OUTPUT_FORMAT},
    }


def parse_planner_text(text: str) -> PlannerResponse:
    """Parse the model's structured-output text into the typed outcome.

    Equivalent to the SDK's own parse path, which validates the text block
    against the output_format type. Shared by the live and batch paths.
    """
    return PlannerResponse.model_validate_json(text)


def plan_question(
    question: str,
    system_prompt: str,
    client: anthropic.Anthropic | None = None,
):
    """Return (PlannerResponse, usage) for one question.

    usage is surfaced so callers (CLI, tests, the Phase 5 harness) can
    verify prompt-cache behavior via cache_read_input_tokens.
    """
    if client is None:
        client = anthropic.Anthropic()
    response = client.messages.create(**build_request_params(question, system_prompt))
    text_blocks = [block for block in response.content if block.type == "text"]
    if not text_blocks:
        raise RuntimeError(
            f"planner response contained no text block (stop_reason={response.stop_reason})"
        )
    return parse_planner_text(text_blocks[0].text), response.usage
