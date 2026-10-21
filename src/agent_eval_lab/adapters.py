from __future__ import annotations

import importlib
import logging
import time
from typing import Any

import httpx

from agent_eval_lab.models import AgentVersion
from agent_eval_lab.schemas import AgentOutput, TurnSchema

logger = logging.getLogger(__name__)


def _normalise(raw: dict[str, Any], latency_ms: int) -> AgentOutput:
    """Coerce an agent response dict to AgentOutput."""
    turns_raw: list[dict[str, Any]] = raw.get("turns", [])

    # Parse turns if present
    turns = [
        TurnSchema(
            role=t.get("role", "assistant"),
            content=t.get("content", ""),
            tool_calls=t.get("tool_calls", []),
        )
        for t in turns_raw
    ]

    # Resolve final_response from common shapes
    if "response" in raw:
        final_response = str(raw["response"])
    elif "message" in raw:
        final_response = str(raw["message"])
    elif turns:
        # Last assistant turn
        assistant_turns = [t for t in turns if t.role == "assistant"]
        final_response = assistant_turns[-1].content if assistant_turns else turns[-1].content
    else:
        logger.warning("Unrecognised agent response shape: %s", list(raw.keys()))
        final_response = ""

    # Synthesise a single assistant turn when no turns were provided
    if not turns:
        turns = [TurnSchema(role="assistant", content=final_response)]

    return AgentOutput(
        turns=turns,
        final_response=final_response,
        latency_ms=latency_ms,
        tokens=raw.get("tokens") or raw.get("usage", {}).get("total_tokens"),
    )


class HTTPAdapter:
    """POST {input} to config["url"], expect {"response": str, "turns": [...]}."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._url: str = config["url"]
        self._timeout: float = float(config.get("timeout_s", 30))

    def run(self, input: dict[str, Any]) -> AgentOutput:  # noqa: A002
        t0 = time.perf_counter()
        response = httpx.post(self._url, json=input, timeout=self._timeout)
        response.raise_for_status()
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return _normalise(response.json(), latency_ms)


class PythonAdapter:
    """Import config["entrypoint"] = "mypackage.module:fn", call fn(input) -> dict."""

    def __init__(self, config: dict[str, Any]) -> None:
        entrypoint: str = config["entrypoint"]
        module_path, _, fn_name = entrypoint.rpartition(":")
        module = importlib.import_module(module_path)
        self._fn = getattr(module, fn_name)

    def run(self, input: dict[str, Any]) -> AgentOutput:  # noqa: A002
        t0 = time.perf_counter()
        result: dict[str, Any] = self._fn(input)
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return _normalise(result, latency_ms)


def get_adapter(agent_version: AgentVersion) -> HTTPAdapter | PythonAdapter:
    """Factory: dispatch on agent_version.adapter_type."""
    config = agent_version.config
    if agent_version.adapter_type == "http":
        return HTTPAdapter(config)
    if agent_version.adapter_type == "python":
        return PythonAdapter(config)
    raise ValueError(f"Unknown adapter_type: {agent_version.adapter_type!r}")
