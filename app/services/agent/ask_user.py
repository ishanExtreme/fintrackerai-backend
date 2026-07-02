"""`ask_user` — the clarification primitive available to every node.

Calls LangGraph `interrupt()`, which pauses the whole turn. The `/chat` endpoint
returns the question (`awaiting_user=true`); the user's next message (same
`conversation_id`) resumes the exact node that asked, with their answer as this
tool's return value. The orchestrator's remaining plan is checkpointed, so work
continues after the clarification.
"""

from __future__ import annotations

from langchain_core.tools import tool
from langgraph.types import interrupt


@tool
def ask_user(question: str) -> str:
    """Ask the user a question and wait for their answer. Use ONLY when you
    genuinely need clarification to proceed (e.g. which category, or which month).
    Returns the user's answer as text."""
    answer = interrupt({"question": question})
    return answer if isinstance(answer, str) else str(answer)
