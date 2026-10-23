"""Unit tests for pure data helpers in ui.py (no Streamlit server required)."""
from __future__ import annotations

import math

from agent_eval_lab.ui import _build_heatmap_df


def test_build_heatmap_df_basic() -> None:
    run_detail = {
        "case_results": [
            {
                "case_id": 1,
                "scores": [
                    {"criterion": "helpful", "value": 4.0},
                    {"criterion": "polite", "value": 5.0},
                ],
            },
            {
                "case_id": 2,
                "scores": [
                    {"criterion": "helpful", "value": 2.0},
                ],
            },
        ]
    }
    df = _build_heatmap_df(run_detail)
    assert df.loc[1, "helpful"] == 4.0
    assert df.loc[1, "polite"] == 5.0
    assert df.loc[2, "helpful"] == 2.0
    # case 2 has no "polite" score → NaN
    assert math.isnan(df.loc[2, "polite"])


def test_build_heatmap_df_empty() -> None:
    df = _build_heatmap_df({"case_results": []})
    assert df.empty
