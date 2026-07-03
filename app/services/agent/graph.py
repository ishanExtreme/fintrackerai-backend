"""Assemble the supervisor graph from the node registry and run turns.

Topology (all generated from the registry — adding a node needs no change here):

    START → orchestrator ─(conditional: route)─→ <node> → orchestrator → … → END

Each `<node>` runs its sub-agent on just its sub-query and returns the result to
the orchestrator as a ToolMessage (answering the handoff tool-call), then loops
back. `ask_user` anywhere pauses the whole turn (interrupt); the next turn (same
conversation_id) resumes it.

Runs **synchronously** (our tools do sync DB writes)
"""

from __future__ import annotations

import datetime as dt
import logging
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging_config import timed
from app.schemas import ChatEvent

from .callbacks import LoggingCallbackHandler
from .llm import get_model
from .nodes.base import AssistantNode, all_nodes, message_text
from .orchestrator import END_ROUTE, orchestrator
from .runtime import request_scope
from .state import AssistantState

logger = logging.getLogger("agent")


def _make_runner(node: AssistantNode):
    def run(state: AssistantState) -> dict:
        task = state.get("task") or ""
        tool_call_id = state.get("task_tool_call_id")
        logger.info("node[%s] task=%r", node.name, task)
        result = node.run(get_model(), task)
        logger.info("node[%s] result=%r", node.name, result)
        pending = [p for p in (state.get("pending") or []) if p["tool_call_id"] != tool_call_id]
        return {
            "messages": [ToolMessage(content=result, tool_call_id=tool_call_id)],
            "results": (state.get("results") or []) + [result],
            "pending": pending,
            "task": None,
            "task_tool_call_id": None,
        }

    run.__name__ = f"run_{node.name}"
    return run


@lru_cache
def _graph():
    import app.services.agent.nodes  # noqa: F401  (side-effect: registers nodes)

    nodes = all_nodes()
    builder = StateGraph(AssistantState)
    builder.add_node("orchestrator", orchestrator)
    builder.add_edge(START, "orchestrator")

    route_map = {n.name: n.name for n in nodes}
    route_map[END_ROUTE] = END
    builder.add_conditional_edges("orchestrator", lambda s: s.get("route", END_ROUTE), route_map)

    for n in nodes:
        builder.add_node(n.name, _make_runner(n))
        builder.add_edge(n.name, "orchestrator")

    graph = builder.compile(checkpointer=InMemorySaver())
    logger.info("chat agent graph built — nodes=%s", [n.name for n in nodes])
    return graph


def _today_in_tz(tz: str | None) -> dt.date | None:
    """Today's date in the user's IANA timezone, or None to fall back to server local."""
    if not tz:
        return None
    try:
        return dt.datetime.now(ZoneInfo(tz)).date()
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning("invalid tz %r; using server local date", tz)
        return None


def run_turn(
    *,
    conversation_id: str,
    message: str,
    db: Session,
    user_id: int,
    llm_key: str | None,
    tz: str | None = None,
    today: dt.date | None = None,
) -> tuple[str, list[ChatEvent], bool]:
    """Run (or resume) one turn. Returns (reply, events, awaiting_user)."""
    settings = get_settings()
    today = today or _today_in_tz(tz)
    graph = _graph()
    cfg = {
        "configurable": {"thread_id": conversation_id},
        "recursion_limit": settings.agent_recursion_limit,
        "callbacks": [LoggingCallbackHandler()],
    }

    prev = graph.get_state(cfg)
    resuming = bool(prev.interrupts) if prev else False
    logger.info("turn [%s] %s msg=%r", conversation_id[:8], "RESUME" if resuming else "new", message)

    with request_scope(db=db, user_id=user_id, llm_key=llm_key, today=today) as events:
        payload = (
            Command(resume=message)
            if resuming
            else {
                "messages": [HumanMessage(content=message)],
                "pending": [],
                "results": [],
                "route": "",
            }
        )
        with timed(logger, f"agent turn [{conversation_id[:8]}]"):
            result = graph.invoke(payload, config=cfg)

        state = graph.get_state(cfg)
        if state and state.interrupts:
            q = state.interrupts[0].value or {}
            reply = q.get("question", "") if isinstance(q, dict) else str(q)
            awaiting = True
        else:
            reply = message_text(result["messages"][-1])
            awaiting = False

        acts = list(events)
        logger.info(
            "turn [%s] reply=%r events=%s awaiting=%s",
            conversation_id[:8], reply, [e.type for e in acts], awaiting,
        )
        return reply, acts, awaiting
