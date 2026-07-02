"""Investments specialist: record how much was invested and report totals
(amount only — no returns or prices)."""

from __future__ import annotations

from ..nodes.base import AssistantNode, register_node
from ..tools import add_investment, query_investments

_PROMPT = """\
You track how much the user invests (amount only — no returns or prices). For
"I invested 10000 in mutual funds this month", call `add_investment` with the
amount and an optional category. For "how much did I invest this year", call
`query_investments`. Default the month to the current month unless the user names
one. Reply with one short confirmation or answer."""


register_node(
    AssistantNode(
        name="investments",
        description="Record monthly investment amounts and report investment totals.",
        system_prompt=_PROMPT,
        tools=[add_investment, query_investments],
    )
)
