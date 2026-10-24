"""Streamlit UI for Agent Eval Lab."""
from __future__ import annotations

import json
import os
import time
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_BASE: str = os.getenv("API_BASE_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _get(path: str) -> Any:
    import httpx

    try:
        resp = httpx.get(f"{API_BASE}{path}", timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"API error on GET {path}: {exc}")
        st.stop()


def _post(path: str, payload: dict) -> Any:  # type: ignore[type-arg]
    import httpx

    try:
        resp = httpx.post(f"{API_BASE}{path}", json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        st.error(f"API error on POST {path}: {exc}")
        st.stop()


# ---------------------------------------------------------------------------
# Pure data helper (no streamlit import — keeps unit tests cheap)
# ---------------------------------------------------------------------------


def _build_heatmap_df(run_detail: dict) -> pd.DataFrame:  # type: ignore[type-arg]
    """
    Takes the RunDetail JSON dict (with nested case_results → scores).
    Returns a DataFrame indexed by case_id, columns = criterion names,
    values = mean score (float). Missing scores → NaN.
    """
    case_results = run_detail.get("case_results", [])
    if not case_results:
        return pd.DataFrame()

    rows: dict[int, dict[str, float]] = {}
    for cr in case_results:
        case_id = cr["case_id"]
        if case_id not in rows:
            rows[case_id] = {}
        for score in cr.get("scores", []):
            criterion = score["criterion"]
            value = float(score["value"])
            # average if multiple scores for same criterion (shouldn't happen, but safe)
            existing = rows[case_id].get(criterion)
            if existing is None:
                rows[case_id][criterion] = value
            else:
                rows[case_id][criterion] = (existing + value) / 2.0

    df = pd.DataFrame.from_dict(rows, orient="index")
    df.index.name = "case_id"
    return df


def _build_compare_df(run_a: dict, run_b: dict) -> pd.DataFrame:  # type: ignore[type-arg]
    """Return long-form DataFrame with columns: case_id, criterion, score_a, score_b, delta.

    Only includes cases present in BOTH runs (inner join semantics).
    """

    def _scores_by_case(run: dict) -> dict[str, dict[str, float]]:  # type: ignore[type-arg]
        result: dict[str, dict[str, float]] = {}
        for cr in run.get("case_results", []):
            cid = str(cr["case_id"])
            if cid not in result:
                result[cid] = {}
            for score in cr.get("scores", []):
                result[cid][score["criterion"]] = float(score["value"])
        return result

    scores_a = _scores_by_case(run_a)
    scores_b = _scores_by_case(run_b)
    common_cases = set(scores_a.keys()) & set(scores_b.keys())

    rows = []
    for cid in sorted(common_cases):
        all_criteria = set(scores_a[cid].keys()) | set(scores_b[cid].keys())
        for criterion in sorted(all_criteria):
            sa = scores_a[cid].get(criterion, float("nan"))
            sb = scores_b[cid].get(criterion, float("nan"))
            import math

            delta = (sb - sa) if not (math.isnan(sa) or math.isnan(sb)) else float("nan")
            rows.append({"case_id": cid, "criterion": criterion, "score_a": sa, "score_b": sb, "delta": delta})

    return pd.DataFrame(rows, columns=["case_id", "criterion", "score_a", "score_b", "delta"])


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


def _render_trace_drawer(case_result: dict, criteria: list[str]) -> None:  # type: ignore[type-arg]
    """Render turns, tool calls, output, latency/token stats, and per-criterion scores+reasoning."""
    st.caption(f"Latency: {case_result.get('latency_ms', '?')} ms | Tokens: {case_result.get('tokens', '?')}")

    turns = json.loads(case_result.get("trace_json") or "[]")
    if turns:
        st.subheader("Turns")
        for turn in turns:
            role = turn.get("role", "assistant")
            content = turn.get("content", "")
            with st.chat_message(role):
                st.write(content)
                for tc in turn.get("tool_calls") or []:
                    st.json(tc)
    else:
        st.info("No trace recorded for this case.")

    scores = case_result.get("scores", [])
    if scores:
        st.subheader("Scores & Reasoning")
        for score in scores:
            criterion = score.get("criterion", "?")
            value = score.get("value", 0)
            reasoning = score.get("reasoning", "")
            st.metric(criterion, f"{value:.1f}/5")
            if reasoning:
                st.caption(reasoning)


def page_suites() -> None:
    st.header("Suites")
    suites = _get("/suites")
    if not suites:
        st.info("No suites found. Seed the database first.")
        return

    st.dataframe(suites, use_container_width=True)

    suite_options = {s["name"]: s["id"] for s in suites}
    selected_name = st.selectbox("View cases for suite", list(suite_options.keys()))
    if selected_name:
        suite_id = suite_options[selected_name]
        cases = _get(f"/suites/{suite_id}/cases")
        st.subheader(f"Cases — {selected_name}")
        if cases:
            st.dataframe(cases, use_container_width=True)
        else:
            st.info("No cases in this suite.")


def page_rubrics() -> None:
    st.header("Rubrics")
    rubrics = _get("/rubrics")
    if not rubrics:
        st.info("No rubrics found.")
        return

    for r in rubrics:
        with st.expander(f"[{r['id']}] {r['name']}"):
            st.code(r["criteria_yaml"], language="yaml")


def page_agents() -> None:
    st.header("Agent Versions")
    agents = _get("/agents")
    if not agents:
        st.info("No agent versions registered.")
        return
    st.dataframe(agents, use_container_width=True)


def page_runs() -> None:
    st.header("Runs")

    # ------------------------------------------------------------------
    # 1. Progress polling (shown above the form when active)
    # ------------------------------------------------------------------
    if run_id := st.session_state.get("polling_run_id"):
        detail = _get(f"/runs/{run_id}")
        done = len(detail["case_results"])
        # Try to get total from a separate suite call
        suite_detail = _get(f"/suites/{detail['suite_id']}")
        total = suite_detail.get("cases_count", 1)
        st.progress(
            done / max(total, 1),
            text=f"{detail['status']} — {done}/{total} cases completed",
        )
        if detail["status"] in ("done", "failed"):
            del st.session_state["polling_run_id"]
            st.cache_data.clear()
            st.success(f"Run {run_id} finished with status: {detail['status']}")
        else:
            time.sleep(2)
            st.rerun()

    # ------------------------------------------------------------------
    # 2. Launch Run form
    # ------------------------------------------------------------------
    st.subheader("Launch a New Run")
    suites = _get("/suites")
    rubrics = _get("/rubrics")
    agents = _get("/agents")

    if not suites or not rubrics or not agents:
        st.warning("Need at least one suite, one rubric, and one agent version to launch a run.")
    else:
        with st.form("launch"):
            suite_map = {s["name"]: s["id"] for s in suites}
            rubric_map = {r["name"]: r["id"] for r in rubrics}
            agent_map = {a["name"]: a["id"] for a in agents}

            chosen_suite = st.selectbox("Suite", list(suite_map.keys()))
            chosen_rubric = st.selectbox("Rubric", list(rubric_map.keys()))
            chosen_agent = st.selectbox("Agent Version", list(agent_map.keys()))
            submitted = st.form_submit_button("Launch Run")

        if submitted:
            new_run = _post(
                "/runs",
                {
                    "suite_id": suite_map[chosen_suite],
                    "rubric_id": rubric_map[chosen_rubric],
                    "agent_version_id": agent_map[chosen_agent],
                },
            )
            st.session_state["polling_run_id"] = new_run["id"]
            st.rerun()

    # ------------------------------------------------------------------
    # 3. Heatmap for an existing run
    # ------------------------------------------------------------------
    st.subheader("Score Heatmap")
    all_runs = _get("/runs")
    if not all_runs:
        st.info("No runs yet.")
        return

    run_labels = {f"Run {r['id']} — {r['status']}": r["id"] for r in all_runs}
    selected_label = st.selectbox("Select run", list(run_labels.keys()))
    if selected_label:
        selected_run_id = run_labels[selected_label]
        run_detail = _get(f"/runs/{selected_run_id}")
        df = _build_heatmap_df(run_detail)

        if df.empty:
            st.info("No scored results yet for this run.")
        else:
            fig = go.Figure(
                data=go.Heatmap(
                    z=df.values.tolist(),
                    x=list(df.columns),
                    y=[str(idx) for idx in df.index],
                    zmin=1,
                    zmax=5,
                    colorscale="RdYlGn",
                    colorbar={"title": "Score"},
                )
            )
            fig.update_layout(
                title=f"Run {selected_run_id} — Score Heatmap",
                xaxis_title="Criterion",
                yaxis_title="Case ID",
            )
            st.plotly_chart(fig, use_container_width=True)

            # Case inspector
            case_results = run_detail.get("case_results", [])
            case_ids = [str(cr["case_id"]) for cr in case_results]
            if case_ids:
                st.subheader("Inspect a Case")
                selected_case = st.selectbox(
                    "Select case:",
                    options=case_ids,
                    key="selected_case_id",
                )
                matched = next((cr for cr in case_results if str(cr["case_id"]) == selected_case), None)
                if matched:
                    _render_trace_drawer(matched, list(df.columns))


def page_compare() -> None:
    st.header("Compare Runs")

    all_runs = _get("/runs")
    if not all_runs or len(all_runs) < 2:
        st.info("Need at least two runs to compare.")
        return

    run_labels = {f"Run {r['id']} — {r['status']}": r["id"] for r in all_runs}
    label_list = list(run_labels.keys())

    col1, col2 = st.columns(2)
    with col1:
        label_a = st.selectbox("Run A (baseline)", label_list, key="compare_run_a")
    with col2:
        label_b = st.selectbox("Run B (new)", label_list, index=min(1, len(label_list) - 1), key="compare_run_b")

    if st.button("Load comparison"):
        st.session_state["_compare_run_a_detail"] = _get(f"/runs/{run_labels[label_a]}")
        st.session_state["_compare_run_b_detail"] = _get(f"/runs/{run_labels[label_b]}")

    run_a_detail = st.session_state.get("_compare_run_a_detail")
    run_b_detail = st.session_state.get("_compare_run_b_detail")

    if not run_a_detail or not run_b_detail:
        st.info("Select two runs and click **Load comparison**.")
        return

    compare_df = _build_compare_df(run_a_detail, run_b_detail)
    if compare_df.empty:
        st.warning("No overlapping cases between the two runs.")
        return

    # Summary delta table
    st.subheader("Delta Summary (Run B − Run A)")
    summary = compare_df.groupby("criterion")[["score_a", "score_b", "delta"]].mean().round(2)
    st.dataframe(summary, use_container_width=True)

    # Delta heatmap
    pivot = compare_df.pivot(index="case_id", columns="criterion", values="delta")
    text_vals = [[f"{v:+.1f}" if v == v else "" for v in row] for row in pivot.values.tolist()]  # noqa: PLR0124
    fig = go.Figure(
        data=go.Heatmap(
            z=pivot.values.tolist(),
            x=list(pivot.columns),
            y=list(pivot.index),
            zmin=-4,
            zmid=0,
            zmax=4,
            colorscale="RdYlGn",
            colorbar={"title": "Delta"},
            text=text_vals,
            texttemplate="%{text}",
        )
    )
    fig.update_layout(
        title=f"Run {run_labels[label_a]} vs Run {run_labels[label_b]} — Score Deltas",
        xaxis_title="Criterion",
        yaxis_title="Case ID",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Side-by-side case inspector
    st.subheader("Inspect a Case Side-by-Side")
    case_ids = list(pivot.index)
    selected_case = st.selectbox("Select case:", options=case_ids, key="compare_selected_case")

    cr_a = next((cr for cr in run_a_detail.get("case_results", []) if str(cr["case_id"]) == selected_case), None)
    cr_b = next((cr for cr in run_b_detail.get("case_results", []) if str(cr["case_id"]) == selected_case), None)

    criteria = list(pivot.columns)
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"**Run A** (id={run_labels[label_a]})")
        if cr_a:
            _render_trace_drawer(cr_a, criteria)
        else:
            st.info("No result for this case in Run A.")
    with col_b:
        st.markdown(f"**Run B** (id={run_labels[label_b]})")
        if cr_b:
            _render_trace_drawer(cr_b, criteria)
        else:
            st.info("No result for this case in Run B.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Agent Eval Lab", layout="wide")
    page = st.sidebar.radio("Navigate", ["Suites", "Rubrics", "Agents", "Runs", "Compare"])
    {
        "Suites": page_suites,
        "Rubrics": page_rubrics,
        "Agents": page_agents,
        "Runs": page_runs,
        "Compare": page_compare,
    }[page]()


if __name__ == "__main__":
    main()
