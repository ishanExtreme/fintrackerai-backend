"""The chat model, shared by the orchestrator and every node.

`settings.llm_model` is a LangChain `provider:model` string (e.g.
`google_genai:gemini-3.5-flash`), so swapping provider/model is pure config.

we support **bring-your-own** keys: the
active key comes from `runtime.current_llm_key()` (the user's decrypted key, else
the shared server key). Models are cached per key so each distinct key reuses one
model instance without leaking across users.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain.chat_models import init_chat_model

from app.config import get_settings

from .runtime import current_llm_key

logger = logging.getLogger("agent")


@lru_cache(maxsize=32)
def _build_model(model: str, api_key: str, timeout: float, max_retries: int):
    logger.info("LLM build: model=%s (key=…%s)", model, api_key[-4:] if api_key else "none")
    return init_chat_model(
        model,
        api_key=api_key,
        timeout=timeout,
        max_retries=max_retries,
    )


def get_model(model: str | None = None):
    """Get the LLM model instance.

    Args:
        model: Optional model override (e.g. SMS_LLM_MODEL). Falls back to
               settings.llm_model when None or empty.
    """
    settings = get_settings()
    model_name = model if model else settings.llm_model
    key = current_llm_key() or settings.llm_api_key or ""
    return _build_model(model_name, key, settings.llm_timeout_s, settings.llm_max_retries)