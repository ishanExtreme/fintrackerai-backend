"""Importing this package registers all built-in nodes (side-effect imports).

To add a capability: create a module here that builds an `AssistantNode` and
calls `register_node(...)`, then import it below.
"""

from . import budgets  # noqa: F401
from . import expense_search  # noqa: F401
from . import expenses  # noqa: F401
from . import investments  # noqa: F401
