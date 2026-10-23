"""Tests for M4 scorers: LLM judge, deterministic scorers, and integration."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response
from sqlmodel import Session, select

from agent_eval_lab.models import (
    AgentVersion,
    CaseResult,
    EvalCase,
    Rubric,
    Run,
    Score,
    Suite,
)
from agent_eval_lab.scorers import (
    ScorerResult,
    _json_schema_score,
    _llm_judge,
    _regex_score,
    _tool_call_score,
    score_case_result,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_case(input_json: str = '{"content": "hello"}', expected_json: str = "{}") -> EvalCase:
    return EvalCase(suite_id=1, input_json=input_json, expected_json=expected_json)


def _make_result(output_json: str = '{}', trace_json: str = "[]") -> CaseResult:
    return CaseResult(run_id=1, case_id=1, output_json=output_json, trace_json=trace_json)


# ---------------------------------------------------------------------------
# _regex_score tests
# ---------------------------------------------------------------------------

def test_regex_score_pattern_match() -> None:
    criterion = {"name": "mentions_refund", "type": "regex", "pattern": r"refund"}
    case = _make_case()
    cr = _make_result(output_json='{"final_response": "We will process your refund shortly."}')

    result = _regex_score(criterion, case, cr)
    assert result.score == 5.0
    assert "matched" in result.reasoning.lower()


def test_regex_score_pattern_no_match() -> None:
    criterion = {"name": "mentions_refund", "type": "regex", "pattern": r"refund"}
    case = _make_case()
    cr = _make_result(output_json='{"final_response": "Thank you for contacting us."}')

    result = _regex_score(criterion, case, cr)
    assert result.score == 1.0
    assert "not match" in result.reasoning.lower()


def test_regex_score_contains_partial() -> None:
    # 2 of 3 strings match → score = 2/3 * 4 + 1 ≈ 3.67
    criterion = {"name": "key_phrases", "type": "regex"}
    case = _make_case(expected_json='{"contains": ["apologize", "order number", "investigate"]}')
    cr = _make_result(
        output_json='{"final_response": "We apologize for the delay. Please share your order number."}'
    )

    result = _regex_score(criterion, case, cr)
    expected_score = 2 / 3 * 4.0 + 1.0
    assert abs(result.score - expected_score) < 0.01
    assert "2/3" in result.reasoning


# ---------------------------------------------------------------------------
# _json_schema_score tests
# ---------------------------------------------------------------------------

def test_json_schema_valid() -> None:
    schema = {
        "type": "object",
        "properties": {"final_response": {"type": "string"}},
        "required": ["final_response"],
    }
    criterion = {"name": "output_schema", "type": "json_schema", "schema": schema}
    case = _make_case()
    cr = _make_result(output_json='{"final_response": "hello"}')

    result = _json_schema_score(criterion, case, cr)
    assert result.score == 5.0


def test_json_schema_invalid() -> None:
    schema = {
        "type": "object",
        "properties": {"final_response": {"type": "string"}},
        "required": ["final_response"],
    }
    criterion = {"name": "output_schema", "type": "json_schema", "schema": schema}
    case = _make_case()
    cr = _make_result(output_json='{"tokens": 5}')  # missing final_response

    result = _json_schema_score(criterion, case, cr)
    assert result.score == 1.0
    assert len(result.reasoning) > 0


# ---------------------------------------------------------------------------
# _tool_call_score tests
# ---------------------------------------------------------------------------

def test_tool_call_sequence_match() -> None:
    criterion = {"name": "tool_order", "type": "tool_call_sequence", "tools": ["search", "answer"]}
    case = _make_case()
    trace = [
        {"role": "assistant", "content": "", "tool_calls": [{"name": "search"}]},
        {"role": "assistant", "content": "done", "tool_calls": [{"name": "answer"}]},
    ]
    cr = _make_result(trace_json=json.dumps(trace))

    result = _tool_call_score(criterion, case, cr)
    assert result.score == 5.0


def test_tool_call_sequence_missing() -> None:
    criterion = {"name": "tool_order", "type": "tool_call_sequence", "tools": ["search", "answer"]}
    case = _make_case()
    trace = [
        {"role": "assistant", "content": "", "tool_calls": [{"name": "answer"}]},
    ]
    cr = _make_result(trace_json=json.dumps(trace))

    result = _tool_call_score(criterion, case, cr)
    assert result.score == 1.0


# ---------------------------------------------------------------------------
# _llm_judge tests
# ---------------------------------------------------------------------------

def test_llm_judge_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch anthropic.Anthropic so no real API call is made."""

    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 4, "reasoning": "good response"}')]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    mock_anthropic_class = MagicMock(return_value=mock_client)

    monkeypatch.setattr("anthropic.Anthropic", mock_anthropic_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    criterion = {"name": "helpful", "type": "llm_judge", "guidance": "1=unhelpful, 5=fully helpful"}
    case = _make_case()
    cr = _make_result(output_json='{"final_response": "Here is how I can help you."}')

    result = _llm_judge(criterion, case, cr)
    assert result.score == 4.0
    assert result.reasoning == "good response"


def test_llm_judge_strips_code_fence(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM wrapping JSON in ```json blocks is handled correctly."""
    mock_message = MagicMock()
    mock_message.content = [
        MagicMock(text='```json\n{"score": 3, "reasoning": "okay"}\n```')
    ]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mock_anthropic_class = MagicMock(return_value=mock_client)

    monkeypatch.setattr("anthropic.Anthropic", mock_anthropic_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    criterion = {"name": "polite", "guidance": "1=rude, 5=warm"}
    case = _make_case()
    cr = _make_result(output_json='{"final_response": "Hello!"}')

    result = _llm_judge(criterion, case, cr)
    assert result.score == 3.0
    assert result.reasoning == "okay"


# ---------------------------------------------------------------------------
# score_case_result integration (DB persistence)
# ---------------------------------------------------------------------------

def test_score_case_result_persists(monkeypatch: pytest.MonkeyPatch) -> None:
    """score_case_result writes Score rows for each criterion."""
    from agent_eval_lab import db as db_module

    with Session(db_module.engine) as session:
        suite = Suite(name="test_suite_sc")
        session.add(suite)
        session.commit()
        session.refresh(suite)

        case = EvalCase(
            suite_id=suite.id,  # type: ignore[arg-type]
            input_json='{"content": "test"}',
            expected_json='{"contains": ["help"]}',
        )
        session.add(case)
        session.commit()
        session.refresh(case)

        rubric = Rubric(
            name="test_rubric_sc",
            criteria_yaml="- name: regex_check\n  type: regex\n  pattern: help\n",
        )
        session.add(rubric)

        agent_version = AgentVersion(
            name="test_av_sc",
            adapter_type="http",
            config_json='{"url": "http://fake"}',
        )
        session.add(agent_version)
        session.commit()
        session.refresh(rubric)
        session.refresh(agent_version)

        run = Run(
            suite_id=suite.id,  # type: ignore[arg-type]
            rubric_id=rubric.id,  # type: ignore[arg-type]
            agent_version_id=agent_version.id,  # type: ignore[arg-type]
        )
        session.add(run)
        session.commit()
        session.refresh(run)

        cr = CaseResult(
            run_id=run.id,  # type: ignore[arg-type]
            case_id=case.id,  # type: ignore[arg-type]
            output_json='{"final_response": "I can help you with that."}',
            trace_json="[]",
        )
        session.add(cr)
        session.commit()
        session.refresh(cr)

        criteria = rubric.criteria
        score_case_result(cr, case, criteria, session)

        scores = session.exec(select(Score).where(Score.case_result_id == cr.id)).all()
        assert len(scores) == 1
        assert scores[0].criterion == "regex_check"
        assert scores[0].value == 5.0  # "help" matches pattern "help"


# ---------------------------------------------------------------------------
# Full runner integration test
# ---------------------------------------------------------------------------

@respx.mock
def test_runner_populates_scores(monkeypatch: pytest.MonkeyPatch) -> None:
    """execute_run seeds CaseResult rows and then populates Score rows."""
    from agent_eval_lab import db as db_module
    from agent_eval_lab.runner import execute_run

    # Mock the HTTP agent
    respx.post("http://fake-agent-scores/chat").mock(
        return_value=Response(200, json={"response": "We can help you with your order."})
    )

    # Mock Anthropic so no real call is made (for llm_judge criteria)
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text='{"score": 4, "reasoning": "helpful response"}')]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message
    mock_anthropic_class = MagicMock(return_value=mock_client)

    monkeypatch.setattr("anthropic.Anthropic", mock_anthropic_class)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    with Session(db_module.engine) as session:
        suite = Suite(name="runner_score_suite")
        session.add(suite)
        session.commit()
        session.refresh(suite)

        case = EvalCase(
            suite_id=suite.id,  # type: ignore[arg-type]
            input_json='{"content": "Where is my order?"}',
            expected_json='{"contains": ["order"]}',
        )
        session.add(case)
        session.commit()

        # Use a regex criterion so we don't need the real LLM
        criteria_yaml = "- name: mentions_order\n  type: regex\n  pattern: order\n"
        rubric = Rubric(name="runner_rubric", criteria_yaml=criteria_yaml)
        session.add(rubric)

        agent_version = AgentVersion(
            name="runner_av",
            adapter_type="http",
            config_json='{"url": "http://fake-agent-scores/chat"}',
        )
        session.add(agent_version)
        session.commit()
        session.refresh(suite)
        session.refresh(rubric)
        session.refresh(agent_version)

        run = Run(
            suite_id=suite.id,  # type: ignore[arg-type]
            rubric_id=rubric.id,  # type: ignore[arg-type]
            agent_version_id=agent_version.id,  # type: ignore[arg-type]
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    with Session(db_module.engine) as session:
        execute_run(run_id, session)  # type: ignore[arg-type]

    with Session(db_module.engine) as session:
        run = session.get(Run, run_id)
        assert run is not None
        assert run.status == "done"

        case_results = session.exec(
            select(CaseResult).where(CaseResult.run_id == run_id)
        ).all()
        assert len(case_results) == 1

        scores = session.exec(
            select(Score).where(Score.case_result_id == case_results[0].id)
        ).all()
        assert len(scores) == 1
        assert scores[0].criterion == "mentions_order"
        assert scores[0].value == 5.0  # "order" present in "We can help you with your order."
