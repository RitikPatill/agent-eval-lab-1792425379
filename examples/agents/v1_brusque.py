"""Customer-support agent v1 — terse / brusque style.

Entrypoint string for AgentVersion config:
    "examples.agents.v1_brusque:run_agent"
"""
from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = (
    "You are a terse customer-support agent. "
    "Answer briefly and directly. Do not apologise unnecessarily. "
    "Give the customer exactly what they asked for and nothing more. "
    "Use short sentences. Do not add pleasantries."
)

_graph = None  # lazy-init so import is cheap


def run_agent(input_dict: dict[str, Any]) -> dict[str, Any]:
    """PythonAdapter entrypoint.  Lazy-initialises the LangGraph on first call."""
    global _graph
    if _graph is None:
        from examples.agents.base import build_agent

        _graph = build_agent(SYSTEM_PROMPT)

    from examples.agents.base import invoke_agent

    return invoke_agent(_graph, input_dict)
