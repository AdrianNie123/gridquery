"""The one LLM call: question -> typed outcome.

claude-haiku-4-5 with structured outputs. The system prompt (grounding
rules + governed surface + metric catalog) is the static prefix and
carries a cache_control breakpoint; the question is the only volatile
content and comes after it. No agentic loop, no tools: the model's whole
job is constrained selection and parameterization.
"""

import anthropic

from nl.schema import PlannerResponse

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 2048


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
    response = client.messages.parse(
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
    return response.parsed_output, response.usage
