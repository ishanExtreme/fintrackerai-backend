"""Node registry — the extensibility seam.

A new capability = one module that builds an `AssistantNode` (name + a one-line
`description` the orchestrator routes on) and calls `register_node(...)`. The
orchestrator's handoff tools, its "available specialists" prompt section, and the
graph wiring are all generated from the registry — no central file to edit.

Two ways to implement a node:
- **Simple** — give it a `system_prompt` + `tools`; it runs as a ReAct sub-agent
  (`create_agent`), with `ask_user` appended automatically.
- **Custom graph** — give it a `graph_factory(model)` returning a compiled
  subgraph that takes `{"task": str}` and returns `{"result": str}`.

Built sub-agents are cached per model object (keyed by id), so bring-your-own-key
users each get their own compiled agent instead of sharing the first caller's.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage

from app.services.agent.ask_user import ask_user
from app.services.agent.runtime import current_today


def _dated_task(task: str) -> str:
    """Anchor the specialist's turn to today's date.

    Sub-agents are built once and cached per model, so the live date can't live
    in their (static) system prompt. Prepend it to each task instead, so nodes
    can resolve relative dates ("yesterday", "last Friday") into a concrete
    YYYY-MM-DD for their tools.
    """
    return f"Today's date is {current_today().isoformat()}.\n\n{task}"


def message_text(message: Any) -> str:
    """Plain text of a message whose `content` may be a list of blocks.

    Gemini (and other providers) return `content` as a list of content-block
    dicts (e.g. ``{'type': 'text', 'text': ..., 'extras': {...}}``) rather than a
    bare string. Join just the text blocks — ``str(content)`` would leak the raw
    repr (signatures and all) into the reply.
    """
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    parts: list[str] = []
    for part in content or []:
        if isinstance(part, str):
            parts.append(part)
        elif isinstance(part, dict) and part.get("type") == "text":
            parts.append(part.get("text", ""))
    return "".join(parts).strip()


@dataclass
class AssistantNode:
    """A specialist the orchestrator can delegate to."""

    name: str
    description: str
    system_prompt: str = ""
    tools: list[Any] = field(default_factory=list)
    graph_factory: Optional[Callable[[Any], Any]] = None

    _built: dict[int, Any] = field(default_factory=dict, init=False, repr=False)

    def _get_built(self, model: Any) -> Any:
        built = self._built.get(id(model))
        if built is None:
            if self.graph_factory is not None:
                built = self.graph_factory(model)
            else:
                built = create_agent(
                    model, [*self.tools, ask_user], system_prompt=self.system_prompt
                )
            self._built[id(model)] = built
        return built

    def run(self, model: Any, task: str) -> str:
        """Execute the node on its sub-query, returning the result text."""
        built = self._get_built(model)
        task = _dated_task(task)
        if self.graph_factory is not None:
            out = built.invoke({"task": task})
            return (out.get("result") or "").strip() or f"{self.name} done."
        out = built.invoke({"messages": [HumanMessage(content=task)]})
        return message_text(out["messages"][-1]) or f"{self.name} done."


_REGISTRY: dict[str, AssistantNode] = {}


def register_node(node: AssistantNode) -> AssistantNode:
    if node.name in _REGISTRY:
        raise ValueError(f"node {node.name!r} already registered")
    _REGISTRY[node.name] = node
    return node


def all_nodes() -> list[AssistantNode]:
    return list(_REGISTRY.values())


def get_node(name: str) -> AssistantNode:
    return _REGISTRY[name]
