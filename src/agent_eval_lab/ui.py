"""Streamlit UI for Agent Eval Lab."""
from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title="Agent Eval Lab", layout="wide")
    page = st.sidebar.radio("Navigate", ["Suites", "Rubrics", "Agents", "Runs"])
    {
        "Suites": page_suites,
        "Rubrics": page_rubrics,
        "Agents": page_agents,
        "Runs": page_runs,
    }[page]()


if __name__ == "__main__":
    main()
