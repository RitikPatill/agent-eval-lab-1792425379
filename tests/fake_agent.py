"""Tiny callable used by test_adapters to exercise PythonAdapter."""
from __future__ import annotations


def echo_agent(input: dict) -> dict:  # noqa: A002
    """Return the input content as a response."""
    content = input.get("content", "hello")
    return {
        "response": f"echo: {content}",
        "turns": [
            {"role": "user", "content": content},
            {"role": "assistant", "content": f"echo: {content}"},
        ],
        "tokens": 10,
    }
