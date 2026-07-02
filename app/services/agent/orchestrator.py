"""The orchestrator node: an LLM with one handoff tool per registered node.

It routes by calling `to_<node>(query=...)` with the exact sub-request. Handoff
tools are never executed — we read the model's tool-calls and route via
`state['route']`. Compound requests become a `pending` queue dispatched one node
at a time. No tool-calls → the model's text is the final reply. A single node's
result is returned verbatim (no extra LLM call); several are combined with one.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from .llm import get_model
from .nodes.base import all_nodes
from .prompts import orchestrator_system_prompt
from .state import AssistantState

logger = logging.getLogger("agent")

END_ROUTE = "__end__"

_COMBINE_PROMPT = (
    "Combine the specialist results below into ONE short, plain confirmation for "
    "the user (no markdown, one or two sentences). Keep any budget warning."
)


class _HandoffArgs(BaseModel):
    query: str = Field(description="The exact sub-request to give this specialist, in plain language.")


@lru_cache
def _handoff_tools() -> list:
    """One schema-only handoff tool per registered node (never executed)."""
    tools = []
    for n in all_nodes():
        tools.append(
            StructuredTool.from_function(
                func=lambda query: "",  # unused: we read the tool-call, don't run it
                name=f"to_{n.name}",
                description=f"Delegate to the {n.name} specialist. {n.description}",
                args_schema=_HandoffArgs,
            )
        )
    return tools


# Chat models aren't hashable, so we can't use lru_cache here. Cache the bound
# model by id(model); get_model() returns a per-key cached instance, so the id
# is stable across a user's requests.
_HANDOFF_BOUND: dict[int, Any] = {}


def _bind_handoffs(model):
    bound = _HANDOFF_BOUND.get(id(model))
    if bound is None:
        bound = model.bind_tools(_handoff_tools())
        _HANDOFF_BOUND[id(model)] = bound
    return bound


def orchestrator(state: AssistantState) -> dict:
    known = {n.name for n in all_nodes()}

    # Draining a multi-node plan from a previous LLM response: dispatch the next
    # queued handoff without re-asking the model.
    pending = list(state.get("pending") or [])
    if pending:
        nxt = pending[0]
        logger.info("orchestrator → %s (queued): %r", nxt["node"], nxt["query"])
        return {"route": nxt["node"], "task": nxt["query"], "task_tool_call_id": nxt["tool_call_id"]}

    # Plan fully dispatched: finish WITHOUT another LLM call for a single node;
    # combine with one call only if several ran.
    results = state.get("results") or []
    if results:
        if len(results) == 1:
            logger.info("orchestrator → final reply from single node (no LLM)")
            return {"messages": [AIMessage(content=results[0])], "route": END_ROUTE}
        logger.info("orchestrator → combine %d node results (1 LLM call)", len(results))
        summary = get_model().invoke(
            [SystemMessage(content=_COMBINE_PROMPT), HumanMessage(content="\n".join(results))]
        )
        return {"messages": [summary], "route": END_ROUTE}

    prompt = orchestrator_system_prompt(all_nodes())
    resp = _bind_handoffs(get_model()).invoke([SystemMessage(content=prompt)] + state["messages"])

    calls = [c for c in (resp.tool_calls or []) if c["name"].removeprefix("to_") in known]
    if not calls:
        logger.info("orchestrator → final reply (no handoff)")
        return {"messages": [resp], "route": END_ROUTE}

    queue = [
        {"node": c["name"].removeprefix("to_"), "query": c["args"].get("query", ""), "tool_call_id": c["id"]}
        for c in calls
    ]
    first = queue[0]
    logger.info("orchestrator dispatch %s", [q["node"] for q in queue])
    return {
        "messages": [resp],
        "pending": queue,
        "route": first["node"],
        "task": first["query"],
        "task_tool_call_id": first["tool_call_id"],
    }
