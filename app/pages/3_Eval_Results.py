"""Eval results: renders eval/results/latest.json exactly as written.

Every figure on this page comes from the run artifact produced by the
Phase 5 harness (`make eval`). If there is no artifact, the page says so
and shows nothing else: no placeholder metrics.
"""

import json
from pathlib import Path

import streamlit as st

ARTIFACT_PATH = Path(__file__).resolve().parents[2] / "eval" / "results" / "latest.json"

st.set_page_config(page_title="Eval results", page_icon="⚡")
st.title("Eval results")

try:
    artifact = json.loads(ARTIFACT_PATH.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    st.info("No eval run artifact found - run `make eval` (Phase 5).")
    st.stop()


def as_percent(value) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


st.caption(
    f"Run {artifact['run_id']} at commit {artifact['git_commit']}, "
    f"model {artifact['model']}, batch {artifact.get('batch_id') or 'n/a'}. "
    f"{artifact['counts']['total']} questions: {artifact['counts']['query']} query, "
    f"{artifact['counts']['refuse']} refuse, {artifact['counts']['clarify']} clarify."
)

agg = artifact["aggregate"]
cols = st.columns(5)
for col, (label, key) in zip(
    cols,
    [
        ("Overall", "overall_accuracy"),
        ("Metric selection", "metric_selection_accuracy"),
        ("Result", "result_accuracy"),
        ("Refusal", "refusal_accuracy"),
        ("Clarify", "clarify_accuracy"),
    ],
):
    col.metric(label, as_percent(agg[key]))

st.subheader("Failure modes")
modes = artifact["failure_modes"]
if any(modes.values()):
    st.bar_chart({m: c for m, c in modes.items() if c}, horizontal=True)
st.dataframe(
    [{"failure mode": m, "count": c} for m, c in modes.items()],
    width="stretch",
    hide_index=True,
)

st.subheader("Per-question detail")
questions = artifact["questions"]
st.dataframe(
    [
        {
            "id": q["id"],
            "question": q["question"],
            "expected kind": q["expected_kind"],
            "actual kind": q["actual_kind"],
            "expected metric": q.get("expected_metric"),
            "actual metric": q.get("actual_metric"),
            "passed": q["passed"],
            "failure mode": q.get("failure_mode"),
            "detail": q.get("detail"),
        }
        for q in questions
    ],
    width="stretch",
    hide_index=True,
)

failed = [q for q in questions if not q["passed"]]
if failed:
    with st.expander(f"Failed questions ({len(failed)}): plans and checks"):
        for q in failed:
            st.markdown(f"**{q['id']}** - {q['question']}")
            st.json({"checks": q["checks"], "actual_plan": q.get("actual_plan")})

usage = artifact["usage"]
st.subheader("Usage and cost")
st.dataframe(
    [{"counter": k, "value": v} for k, v in usage.items() if k != "pricing_basis"],
    width="stretch",
    hide_index=True,
)
st.caption(f"Pricing basis: {usage['pricing_basis']}")
