"""Unit tests for pure data helpers in ui.py (no Streamlit server required)."""
from __future__ import annotations

import math

import pytest

from agent_eval_lab.ui import _build_compare_df, _build_heatmap_df


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


# ---------------------------------------------------------------------------
# _build_compare_df tests
# ---------------------------------------------------------------------------

_RUN_A = {
    "case_results": [
        {
            "case_id": 1,
            "scores": [
                {"criterion": "helpful", "value": 3.0},
                {"criterion": "polite", "value": 4.0},
            ],
        },
        {
            "case_id": 2,
            "scores": [
                {"criterion": "helpful", "value": 5.0},
                {"criterion": "polite", "value": 5.0},
            ],
        },
    ]
}

_RUN_B = {
    "case_results": [
        {
            "case_id": 1,
            "scores": [
                {"criterion": "helpful", "value": 4.0},
                {"criterion": "polite", "value": 3.0},
            ],
        },
        {
            "case_id": 2,
            "scores": [
                {"criterion": "helpful", "value": 5.0},
                {"criterion": "polite", "value": 4.0},
            ],
        },
    ]
}


def test_build_compare_df_basic() -> None:
    """Delta = score_b - score_a; both cases present → 2 cases × 2 criteria = 4 rows."""
    df = _build_compare_df(_RUN_A, _RUN_B)
    assert len(df) == 4
    row = df[(df["case_id"] == "1") & (df["criterion"] == "helpful")].iloc[0]
    assert row["score_a"] == 3.0
    assert row["score_b"] == 4.0
    assert row["delta"] == pytest.approx(1.0)


def test_build_compare_df_missing_case() -> None:
    """Cases only in one run are excluded (inner join semantics)."""
    run_b_extra = {
        "case_results": _RUN_B["case_results"]
        + [{"case_id": 99, "scores": [{"criterion": "helpful", "value": 5.0}]}]
    }
    df = _build_compare_df(_RUN_A, run_b_extra)
    assert "99" not in df["case_id"].values


def test_build_compare_df_regression_sign() -> None:
    """Delta is negative when run_b score < run_a score."""
    df = _build_compare_df(_RUN_A, _RUN_B)
    row = df[(df["case_id"] == "1") & (df["criterion"] == "polite")].iloc[0]
    assert row["delta"] < 0
