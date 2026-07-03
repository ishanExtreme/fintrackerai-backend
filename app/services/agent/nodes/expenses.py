"""Expenses specialist: record spending and answer questions about it.

Simple ReAct node — it may create categories on the fly (e.g. a "Movie tickets"
sub-category under "Personal") while recording an expense.
"""

from __future__ import annotations

from ..nodes.base import AssistantNode, register_node
from ..tools import add_expense, delete_expenses, find_or_create_category, query_spending

_PROMPT = """\
You record the user's spending and answer questions about it. Amounts are in
Indian Rupees. Given a request like "I spent 500 on biryani", call `add_expense`
with a sensible category (e.g. Food). If the item implies a new, more specific
category (e.g. "movie ticket"), create it as a sub-category of a fitting parent
by passing `parent_category` (e.g. category "Movie tickets", parent_category
"Personal"). Default the date to today unless the user gives one. For questions
like "how much did I spend on food this month", call `query_spending`.

To delete expenses, use `delete_expenses` — but ONLY when the request names a
specific category, e.g. "delete all food expenses for June" or "remove the food
expense from yesterday". You cannot delete an entire month across all categories,
or delete all expenses: if the user asks for something that broad (e.g. "delete
everything", "clear all my expenses", "wipe June"), do NOT call any tool — tell
them that for safety that has to be done from Settings → Reset expenses in the
app.

Reply with one short confirmation or answer, and include any budget warning the
tool returns."""


register_node(
    AssistantNode(
        name="expenses",
        description=(
            "Record spending, answer how much was spent (by category / month), and "
            "delete a specific category's expenses for a month or day."
        ),
        system_prompt=_PROMPT,
        tools=[add_expense, delete_expenses, find_or_create_category, query_spending],
    )
)
