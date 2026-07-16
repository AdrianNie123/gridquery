"""NL query page: one question in, one governed answer out.

Everything flows through nl.interface.ask(); this page only renders the
Answer it gets back. No number on this page is produced anywhere but the
Cube result rows inside that Answer.
"""

import os

import anthropic
import requests
import streamlit as st

from app.governed import (
    CUBE_SETUP_HINT,
    cached_views,
    caveat_notes,
    humanize_rows,
    parameters_line,
    refresh_views,
)
from nl.executor import CubeQueryError
from nl.interface import ask

st.set_page_config(page_title="GridQuery", page_icon="⚡")
st.title("GridQuery")
st.caption(
    "Ask about U.S. grid demand and generation mix (PJM, ERCO, CISO; 2019 "
    "onward). Answers come only from governed Cube metrics; questions "
    "outside that surface are refused or clarified by design."
)


@st.cache_resource
def cached_client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def render_answer_kind(answer) -> None:
    st.subheader(f"Metric: {answer.metric}")
    st.markdown(f"**Parameters:** {parameters_line(answer.plan)}")
    if answer.rows:
        st.dataframe(humanize_rows(answer.rows), width="stretch")
    else:
        st.info("No rows returned for this slice.")
    for note in caveat_notes(answer.plan, answer.rows or []):
        st.caption(f"Note: {note}")
    with st.expander("Query plan and usage"):
        st.json(answer.plan.model_dump(exclude_none=True))
        st.json(answer.usage)


def render_refusal_kind(answer) -> None:
    st.warning(answer.text)
    st.caption(
        "Refusal is a feature: this product only answers through its "
        "governed metrics. The full answerable surface is documented in "
        "docs/metric_catalog.md."
    )


def render_clarification_kind(answer) -> None:
    st.info(answer.text)
    st.caption(
        "Edit your question above to add the missing detail and ask again."
    )


with st.sidebar:
    if st.button("Refresh governed surface"):
        refresh_views()
        st.rerun()

if not os.environ.get("ANTHROPIC_API_KEY"):
    st.error(
        "ANTHROPIC_API_KEY is not set. Put it in a `.env` file at the "
        "repository root (see `.env.example`) and reload."
    )
    st.stop()

try:
    views = cached_views()
except requests.exceptions.RequestException:
    st.error(CUBE_SETUP_HINT)
    st.stop()

# The form makes the API call happen only on explicit submit, never on an
# incidental rerun. key= binds the input to session_state, so the text stays
# populated after a clarification and the user can refine and re-ask
# (single-shot loop).
with st.form("nl_question"):
    question = st.text_input(
        "Your question",
        key="question",
        placeholder="Which balancing authority had the highest total demand in 2023?",
    )
    submitted = st.form_submit_button("Run query")

if submitted and question:
    try:
        with st.spinner("Planning and querying the governed layer..."):
            answer = ask(question, views=views, client=cached_client())
    except (requests.exceptions.RequestException, CubeQueryError):
        st.error(CUBE_SETUP_HINT)
        st.stop()
    except anthropic.AnthropicError as e:
        st.error(
            "The planner call to the Anthropic API failed "
            f"({e.__class__.__name__}). Check ANTHROPIC_API_KEY in `.env` "
            "and your network, then retry."
        )
        st.stop()

    if answer.kind == "answer":
        render_answer_kind(answer)
    elif answer.kind == "refusal":
        render_refusal_kind(answer)
    else:
        render_clarification_kind(answer)
