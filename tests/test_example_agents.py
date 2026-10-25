"""Unit tests for example agent modules.

These are smoke tests only — no LLM calls, no network access.
The LLM is monkeypatched so the tests run without ANTHROPIC_API_KEY.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

langchain_core = pytest.importorskip("langchain_core")
from langchain_core.messages import AIMessage


def _make_mock_graph(response_text: str = "I can help with that."):
    """Return a mock compiled LangGraph that yields a fixed AIMessage."""
    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "messages": [
            AIMessage(content=response_text),
        ]
    }
    return mock_graph


def test_v1_returns_adapter_shape(monkeypatch):
    """v1 run_agent returns a dict with the required adapter keys."""
    import examples.agents.v1_brusque as v1_mod

    # Reset lazy-init so our mock graph takes effect
    v1_mod._graph = _make_mock_graph("Order not found.")

    result = v1_mod.run_agent({"role": "user", "content": "Where is my order?"})

    assert "response" in result
    assert isinstance(result["response"], str)
    assert isinstance(result["turns"], list)
    assert len(result["turns"]) >= 1


def test_v2_returns_adapter_shape(monkeypatch):
    """v2 run_agent returns a dict with the required adapter keys."""
    import examples.agents.v2_polite as v2_mod

    # Reset lazy-init so our mock graph takes effect
    v2_mod._graph = _make_mock_graph(
        "I'm so sorry to hear that! Let me look into this right away."
    )

    result = v2_mod.run_agent({"role": "user", "content": "My package is missing."})

    assert "response" in result
    assert isinstance(result["response"], str)
    assert isinstance(result["turns"], list)
    assert len(result["turns"]) >= 1


def test_v1_and_v2_importable():
    """Both agent modules can be imported without error (and without a real LLM)."""
    import examples.agents.v1_brusque  # noqa: F401
    import examples.agents.v2_polite  # noqa: F401


def test_invoke_agent_tool_call_turn(monkeypatch):
    """invoke_agent serialises tool-call turns correctly."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from examples.agents.base import invoke_agent

    # Build a message sequence with a tool call
    tool_call = {"name": "lookup_order", "args": {"order_id": "ORD-001"}, "id": "call_1"}
    ai_with_tool = AIMessage(content="", tool_calls=[tool_call])
    tool_result = ToolMessage(content="shipped", tool_call_id="call_1")
    final_ai = AIMessage(content="Your order was shipped.")

    mock_graph = MagicMock()
    mock_graph.invoke.return_value = {
        "messages": [
            HumanMessage(content="Where is ORD-001?"),
            ai_with_tool,
            tool_result,
            final_ai,
        ]
    }

    result = invoke_agent(mock_graph, {"role": "user", "content": "Where is ORD-001?"})

    assert result["response"] == "Your order was shipped."
    roles = [t["role"] for t in result["turns"]]
    assert "tool" in roles
    # The assistant turn with tool_calls should include them
    tool_call_turns = [t for t in result["turns"] if t.get("tool_calls")]
    assert len(tool_call_turns) == 1
    assert tool_call_turns[0]["tool_calls"][0]["name"] == "lookup_order"
