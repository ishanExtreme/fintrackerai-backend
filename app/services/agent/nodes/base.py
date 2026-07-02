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
        if self.graph_factory is not None:
            out = built.invoke({"task": task})
            return (out.get("result") or "").strip() or f"{self.name} done."
        out = built.invoke({"messages": [HumanMessage(content=task)]})
        content = getattr(out["messages"][-1], "content", "")
        text = content if isinstance(content, str) else str(content)
        return text.strip() or f"{self.name} done."


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
