# Offline smoke tests for the Streamlit pages: no API key, no Cube, no
# network. ask() and the meta fetch are patched at their module homes
# (Home.py resolves `from nl.interface import ask` at script execution,
# so a patch active during AppTest.run() is what the page sees).

from unittest import mock

import pytest
import requests
from streamlit.testing.v1 import AppTest

import nl  # noqa: F401  (runs load_dotenv once, before tests touch os.environ)
from nl.answer import Answer

HOME = "app/Home.py"
EVAL_PAGE = "app/pages/3_Eval_Results.py"

NO_ARTIFACT_SENTENCE = "No eval run artifact found - run `make eval` (Phase 5)."


def run_home(monkeypatch, answer=None, views_side_effect=None):
    """Run Home.py with a dummy key, patched views, and a canned ask()."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    views = mock.Mock(return_value={}, side_effect=views_side_effect)
    ask = mock.Mock(return_value=answer)
    with mock.patch("app.governed.cached_views", views), mock.patch(
        "nl.interface.ask", ask
    ):
        at = AppTest.from_file(HOME).run()
        if answer is not None:
            at.text_input[0].set_value("How much did demand grow?")
            at.button[0].click().run()
    return at, ask


def test_eval_page_without_artifact_shows_one_sentence_and_nothing_else(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("GRIDQUERY_EVAL_ARTIFACT", str(tmp_path / "missing.json"))
    at = AppTest.from_file(EVAL_PAGE).run()
    assert not at.exception
    assert [i.value for i in at.info] == [NO_ARTIFACT_SENTENCE]
    assert not at.metric and not at.dataframe


def test_eval_page_with_real_artifact_renders_metrics(monkeypatch):
    monkeypatch.delenv("GRIDQUERY_EVAL_ARTIFACT", raising=False)
    at = AppTest.from_file(EVAL_PAGE).run()
    assert not at.exception
    assert [m.label for m in at.metric] == [
        "Overall", "Metric selection", "Result", "Refusal", "Clarify",
    ]


def test_clarification_preserves_the_input_for_re_asking(monkeypatch):
    question_back = "Clarification needed: which balancing authority?"
    at, ask = run_home(
        monkeypatch, answer=Answer(kind="clarification", text=question_back)
    )
    assert not at.exception
    assert ask.called
    assert question_back in [i.value for i in at.info]
    assert at.text_input[0].value == "How much did demand grow?"


def test_refusal_renders_as_warning_with_catalog_pointer(monkeypatch):
    refusal = "Not answerable through the governed metrics: no prices here"
    at, _ = run_home(monkeypatch, answer=Answer(kind="refusal", text=refusal))
    assert not at.exception
    assert refusal in [w.value for w in at.warning]
    assert any("docs/metric_catalog.md" in c.value for c in at.caption)


def test_missing_api_key_shows_env_guidance_and_stops(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(HOME).run()
    assert not at.exception
    assert any("ANTHROPIC_API_KEY" in e.value and ".env" in e.value for e in at.error)
    assert not at.text_input  # st.stop() before the question form


def test_cube_down_shows_setup_hint_not_a_stack_trace(monkeypatch):
    from app.governed import CUBE_SETUP_HINT

    at, _ = run_home(
        monkeypatch, views_side_effect=requests.exceptions.ConnectionError()
    )
    assert not at.exception
    assert CUBE_SETUP_HINT in [e.value for e in at.error]
