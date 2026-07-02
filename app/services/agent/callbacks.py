"""Lightweight logging callback for agent runs (tool starts/ends)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler

logger = logging.getLogger("agent")


class LoggingCallbackHandler(BaseCallbackHandler):
    def on_tool_start(self, serialized: dict[str, Any], input_str: str, **kwargs: Any) -> None:
        name = (serialized or {}).get("name", "tool")
        logger.info("tool[%s] input=%s", name, input_str)

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        text = output if isinstance(output, str) else str(output)
        logger.info("tool → %s", text[:200])
