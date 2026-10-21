"""Tests for HTTPAdapter, PythonAdapter, and get_adapter factory."""
from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from agent_eval_lab.adapters import HTTPAdapter, PythonAdapter, get_adapter
from agent_eval_lab.schemas import AgentOutput


# ---------------------------------------------------------------------------
# HTTPAdapter
# ---------------------------------------------------------------------------


@respx.mock
def test_http_adapter_normalises_minimal_response() -> None:
    """Agent that only returns {"response": "hello"} → single assistant turn."""
    respx.post("http://fake-agent/chat").mock(
        return_value=Response(200, json={"response": "hello"})
    )
    adapter = HTTPAdapter({"url": "http://fake-agent/chat"})
    output = adapter.run({"content": "hi"})

    assert isinstance(output, AgentOutput)
    assert output.final_response == "hello"
    assert len(output.turns) == 1
    assert output.turns[0].role == "assistant"
    assert output.turns[0].content == "hello"
    assert output.latency_ms >= 0


@respx.mock
def test_http_adapter_normalises_message_key() -> None:
    """Agent returning {"message": "..."} is also normalised correctly."""
    respx.post("http://fake-agent/chat").mock(
        return_value=Response(200, json={"message": "world"})
    )
    adapter = HTTPAdapter({"url": "http://fake-agent/chat"})
    output = adapter.run({})

    assert output.final_response == "world"
    assert output.turns[0].content == "world"


@respx.mock
def test_http_adapter_with_turns() -> None:
    """Agent returning full turns list → all turns preserved."""
    payload = {
        "response": "final",
        "turns": [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "final"},
        ],
    }
    respx.post("http://fake-agent/chat").mock(return_value=Response(200, json=payload))
    adapter = HTTPAdapter({"url": "http://fake-agent/chat"})
    output = adapter.run({"content": "hi"})

    assert output.final_response == "final"
    assert len(output.turns) == 2
    assert output.turns[0].role == "user"


@respx.mock
def test_http_adapter_tokens() -> None:
    """tokens field is propagated."""
    respx.post("http://fake-agent/chat").mock(
        return_value=Response(200, json={"response": "ok", "tokens": 42})
    )
    adapter = HTTPAdapter({"url": "http://fake-agent/chat"})
    output = adapter.run({})
    assert output.tokens == 42


# ---------------------------------------------------------------------------
# PythonAdapter
# ---------------------------------------------------------------------------


def test_python_adapter_calls_entrypoint() -> None:
    """PythonAdapter resolves 'tests.fake_agent:echo_agent' and calls it."""
    adapter = PythonAdapter({"entrypoint": "tests.fake_agent:echo_agent"})
    output = adapter.run({"content": "test input"})

    assert isinstance(output, AgentOutput)
    assert output.final_response == "echo: test input"
    assert len(output.turns) == 2
    assert output.turns[0].role == "user"
    assert output.tokens == 10
    assert output.latency_ms >= 0


def test_python_adapter_latency_non_negative() -> None:
    adapter = PythonAdapter({"entrypoint": "tests.fake_agent:echo_agent"})
    output = adapter.run({})
    assert output.latency_ms >= 0


# ---------------------------------------------------------------------------
# get_adapter factory
# ---------------------------------------------------------------------------


def test_get_adapter_dispatches_http() -> None:
    from agent_eval_lab.models import AgentVersion

    av = AgentVersion(
        name="test_http",
        adapter_type="http",
        config_json=json.dumps({"url": "http://localhost:9999"}),
    )
    adapter = get_adapter(av)
    assert isinstance(adapter, HTTPAdapter)


def test_get_adapter_dispatches_python() -> None:
    from agent_eval_lab.models import AgentVersion

    av = AgentVersion(
        name="test_python",
        adapter_type="python",
        config_json=json.dumps({"entrypoint": "tests.fake_agent:echo_agent"}),
    )
    adapter = get_adapter(av)
    assert isinstance(adapter, PythonAdapter)


def test_get_adapter_unknown_type_raises() -> None:
    from agent_eval_lab.models import AgentVersion

    av = AgentVersion(name="bad", adapter_type="grpc", config_json="{}")
    with pytest.raises(ValueError, match="Unknown adapter_type"):
        get_adapter(av)
