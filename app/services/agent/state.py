"""Shared state for the orchestrator graph.

`messages` is the orchestrator-level conversation (persona system prompt added
per-call, user turns, the orchestrator's handoff tool-calls, and each node's
result as a ToolMessage). `pending` is the queue of handoffs still to dispatch
(compound requests run one node at a time). `task`/`task_tool_call_id` carry the
current sub-query and the handoff tool-call it answers. `route` is what the
conditional edge reads. `results` collects each node's confirmation this turn.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional, TypedDict

from langgraph.graph.message import add_messages


class AssistantState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    pending: list[dict[str, Any]]
    task: Optional[str]
    task_tool_call_id: Optional[str]
    route: str
    results: list[str]
