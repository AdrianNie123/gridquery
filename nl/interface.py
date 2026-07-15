"""The single entry point: ask(question) -> Answer.

Pipeline: planner (LLM, cached prefix) -> validator (deterministic) ->
executor (Cube REST) -> answer renderer. Refuse and clarify outcomes exit
early. The Phase 5 eval harness and the Phase 6 front end both call this.
"""

import anthropic

from nl.answer import Answer, render_answer, render_clarification, render_refusal
from nl.catalog import build_system_prompt, fetch_meta, governed_views
from nl.executor import execute_plan
from nl.planner import plan_question
from nl.validator import validate_plan


def _usage_dict(usage) -> dict:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
    }


def resolve_outcome(parsed, views: dict, usage: dict) -> Answer:
    """Turn one planner outcome into an Answer: validator -> executor -> renderer.

    Everything after the LLM call lives here so the Phase 5 eval harness
    can feed batch-parsed planner responses through the exact code the
    live path runs, not a reimplementation.
    """
    outcome = parsed.outcome

    if outcome.action == "refuse":
        return render_refusal(outcome.reason, usage)
    if outcome.action == "clarify":
        return render_clarification(outcome.question, usage)

    violations = validate_plan(outcome.plan, views)
    if violations:
        # The model stepped off the governed surface; refuse, never repair.
        return render_refusal(
            "the proposed query left the governed surface ("
            + "; ".join(violations)
            + ")",
            usage,
        )

    rows = execute_plan(outcome.plan)
    return render_answer(outcome.metric, outcome.plan, rows, usage)


def ask(
    question: str,
    views: dict | None = None,
    client: anthropic.Anthropic | None = None,
) -> Answer:
    """Answer one natural-language question through the governed stack.

    views can be passed in to reuse a /v1/meta fetch across questions
    (the eval harness does this); by default it is fetched fresh.
    """
    if views is None:
        views = governed_views(fetch_meta())
    system_prompt = build_system_prompt(views)

    parsed, usage = plan_question(question, system_prompt, client=client)
    return resolve_outcome(parsed, views, _usage_dict(usage))
