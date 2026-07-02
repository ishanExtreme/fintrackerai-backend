"""Budgets specialist: set per-category monthly limits and answer "how much is
left" questions."""

from __future__ import annotations

from ..nodes.base import AssistantNode, register_node
from ..tools import query_budget_remaining, query_spending, set_budget

_PROMPT = """\
You manage the user's monthly budgets (in Indian Rupees). For "set a 5000 food
budget", call `set_budget`. For "how much do I have left for food this month",
call `query_budget_remaining`. You can also use `query_spending` for spend totals.
Default the month to the current month unless the user names one. Reply with one
short confirmation or answer."""


register_node(
    AssistantNode(
        name="budgets",
        description="Set monthly category budgets and report remaining budget.",
        system_prompt=_PROMPT,
        tools=[set_budget, query_budget_remaining, query_spending],
    )
)
