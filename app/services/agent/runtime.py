"""Per-request runtime shared with the agent's tools.

The graph and tools are built once and reused, but each `/chat` turn carries its
own DB session, authenticated user, resolved LLM key, and today's date — and
accumulates structured `events` the app can render (e.g. a budget warning). We
thread these through `contextvars` (not function args) because LangGraph invokes
the tools and doesn't pass our parameters through. Each turn opens a
`request_scope(...)` that sets them for the run and restores them after — safe
under concurrent requests.
"""

from __future__ import annotations

import contextlib
import datetime as dt
from contextvars import ContextVar
from typing import Any, Iterator

from sqlalchemy.orm import Session

from ...schemas import ChatEvent

_db: ContextVar[Session | None] = ContextVar("agent_db", default=None)
_user_id: ContextVar[int | None] = ContextVar("agent_user_id", default=None)
_today: ContextVar[dt.date | None] = ContextVar("agent_today", default=None)
_llm_key: ContextVar[str | None] = ContextVar("agent_llm_key", default=None)
_events: ContextVar[list[ChatEvent] | None] = ContextVar("agent_events", default=None)


@contextlib.contextmanager
def request_scope(
    *, db: Session, user_id: int, llm_key: str | None, today: dt.date | None = None
) -> Iterator[list[ChatEvent]]:
    """Bind per-request state for one agent run; yields the events accumulator."""
    events: list[ChatEvent] = []
    tokens = [
        _db.set(db),
        _user_id.set(user_id),
        _today.set(today or dt.date.today()),
        _llm_key.set(llm_key),
        _events.set(events),
    ]
    try:
        yield events
    finally:
        for var, tok in zip((_db, _user_id, _today, _llm_key, _events), tokens):
            var.reset(tok)


def current_db() -> Session:
    db = _db.get()
    if db is None:
        raise RuntimeError("current_db() called outside request_scope")
    return db


def current_user_id() -> int:
    uid = _user_id.get()
    if uid is None:
        raise RuntimeError("current_user_id() called outside request_scope")
    return uid


def current_today() -> dt.date:
    return _today.get() or dt.date.today()


def current_llm_key() -> str | None:
    return _llm_key.get()


def record_event(type: str, **data: Any) -> None:
    """Emit a structured event for the app to render alongside the reply."""
    bucket = _events.get()
    if bucket is not None:
        bucket.append(ChatEvent(type=type, data=data))
