"""Shared agent builder for the example customer-support agents.

Usage
-----
    from examples.agents.base import build_agent, invoke_agent

    graph = build_agent("You are a helpful agent.")
    result = invoke_agent(graph, {"role": "user", "content": "Hi!"})
    # result = {"response": str, "turns": [...], "tokens": int | None}
"""
from __future__ import annotations

from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph
from langgraph.graph.message import MessagesState
from langgraph.prebuilt import ToolNode

from examples.agents.tools import lookup_order, process_refund

_TOOLS = [lookup_order, process_refund]
_MODEL_ID = "claude-haiku-4-5-20251001"


def build_agent(system_prompt: str):  # type: ignore[return]
    """Return a compiled LangGraph StateGraph bound to the mock tools."""
    llm = ChatAnthropic(model=_MODEL_ID).bind_tools(_TOOLS)

    def call_model(state: MessagesState) -> dict[str, Any]:
        from langchain_core.messages import SystemMessage

        messages = [SystemMessage(content=system_prompt)] + state["messages"]
        response = llm.invoke(messages)
        return {"messages": [response]}

    tool_node = ToolNode(_TOOLS)

    def should_continue(state: MessagesState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")

    return graph.compile()


def invoke_agent(graph: Any, input_dict: dict[str, Any]) -> dict[str, Any]:
    """Run a compiled LangGraph and return a PythonAdapter-compatible dict.

    Parameters
    ----------
    graph:
        Compiled LangGraph returned by ``build_agent``.
    input_dict:
        ``{"role": "user", "content": "..."}`` — the adapter passes the raw
        input JSON from the test case here.

    Returns
    -------
    dict with keys ``response`` (str), ``turns`` (list), ``tokens`` (int|None).
    """
    content = input_dict.get("content", "")
    initial_state = {"messages": [HumanMessage(content=content)]}
    final_state = graph.invoke(initial_state)

    messages = final_state["messages"]
    turns: list[dict[str, Any]] = []
    total_tokens: int | None = None

    for msg in messages:
        if isinstance(msg, HumanMessage):
            turns.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            turn: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                turn["tool_calls"] = [
                    {"name": tc["name"], "args": tc["args"]} for tc in msg.tool_calls
                ]
            turns.append(turn)
            # Accumulate token usage when available
            if hasattr(msg, "usage_metadata") and msg.usage_metadata:
                usage = msg.usage_metadata
                total_tokens = (total_tokens or 0) + (
                    usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
                )
        elif isinstance(msg, ToolMessage):
            turns.append({"role": "tool", "content": str(msg.content)})

    # Final response is the last assistant message
    assistant_turns = [t for t in turns if t["role"] == "assistant"]
    final_response = assistant_turns[-1]["content"] if assistant_turns else ""

    return {"response": final_response, "turns": turns, "tokens": total_tokens}
