"""Customer-support agent v2 — warm / polite style.

Entrypoint string for AgentVersion config:
    "examples.agents.v2_polite:run_agent"
"""
from __future__ import annotations

from typing import Any

SYSTEM_PROMPT = (
    "You are a warm, empathetic customer-support agent. "
    "Always acknowledge the customer's frustration and apologise where appropriate. "
    "Thank the customer for reaching out. "
    "Offer clear next steps and let them know you are here to help. "
    "Use a friendly, professional tone. "
    "End every response with a reassurance that the issue will be resolved."
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
