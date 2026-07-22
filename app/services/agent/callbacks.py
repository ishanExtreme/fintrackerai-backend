"""A LangChain callback handler that logs the agent's internal loop with timing.

It emits a line when each LLM call and each tool call starts and finishes, with
the elapsed time (and token usage where the provider reports it) — so the server
log shows exactly what the agent is doing (which model turn, which tool, how long
each took) and where it stalls. Ported from bike_dash.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from app.logging_config import _ms

logger = logging.getLogger("agent")


class LoggingCallbackHandler(BaseCallbackHandler):
    def __init__(self) -> None:
        # run_id -> (label, start_time)
        self._starts: dict[UUID, tuple[str, float]] = {}

    def on_chat_model_start(
        self, serialized: dict[str, Any], messages: list, *, run_id: UUID, **kwargs: Any
    ) -> None:
        model = (serialized or {}).get("name") or "model"
        msgs = messages[0] if messages else []
        self._starts[run_id] = ("llm", time.perf_counter())
        logger.info("→ LLM call (%s, %d msgs) …", model, len(msgs))
        # Full payload sent to the LLM (system prompt + history) at DEBUG.
        if logger.isEnabledFor(logging.DEBUG):
            for m in msgs:
                role = getattr(m, "type", m.__class__.__name__)
                text = getattr(m, "content", "")
                if not isinstance(text, str):
                    text = str(text)
                logger.debug("    %-9s | %s", role, text.replace("\n", "\\n"))

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        _, start = self._starts.pop(run_id, ("llm", time.perf_counter()))
        tokens = ""
        try:
            usage = response.llm_output.get("usage_metadata") if response.llm_output else None
            gen = response.generations[0][0]
            usage = usage or getattr(gen.message, "usage_metadata", None)
            if usage:
                tokens = f", {usage.get('input_tokens', '?')}→{usage.get('output_tokens', '?')} tok"
        except Exception:
            pass
        logger.info("← LLM done in %s%s", _ms(time.perf_counter() - start), tokens)

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        _, start = self._starts.pop(run_id, ("llm", time.perf_counter()))
        logger.error("✗ LLM FAILED in %s: %s", _ms(time.perf_counter() - start), error)

    def on_tool_start(
        self, serialized: dict[str, Any], input_str: str, *, run_id: UUID, **kwargs: Any
    ) -> None:
        name = (serialized or {}).get("name") or "tool"
        self._starts[run_id] = (name, time.perf_counter())
        logger.info("→ tool %s(%s) …", name, str(input_str)[:120])

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        name, start = self._starts.pop(run_id, ("tool", time.perf_counter()))
        logger.info("← tool %s done in %s", name, _ms(time.perf_counter() - start))

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        name, start = self._starts.pop(run_id, ("tool", time.perf_counter()))
        logger.error("✗ tool %s FAILED in %s: %s", name, _ms(time.perf_counter() - start), error)
