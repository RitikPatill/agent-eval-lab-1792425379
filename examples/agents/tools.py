"""Mock LangChain tools for the example customer-support agent.

Both tools return hard-coded strings so tool-call-sequence assertions
in test cases are fully predictable without any external API calls.
"""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def lookup_order(order_id: str) -> str:
    """Return mock order status for a given order ID."""
    statuses = {
        "ORD-001": "shipped — estimated delivery 2024-04-01",
        "ORD-002": "processing — not yet dispatched",
        "ORD-003": "delivered on 2024-03-20",
    }
    return statuses.get(order_id, f"Order {order_id} not found in system.")


@tool
def process_refund(order_id: str, reason: str) -> str:
    """Initiate a mock refund for a given order and reason."""
    return (
        f"Refund initiated for order {order_id}. "
        f"Reason recorded: '{reason}'. "
        "You will receive a confirmation email within 24 hours and "
        "the amount will be credited in 3-5 business days."
    )
