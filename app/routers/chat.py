"""Chat endpoint — runs one turn of the LangGraph finance agent (Gemini)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..crypto import resolve_llm_key
from ..db import get_db
from ..services.agent.graph import run_turn

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=schemas.ChatResponse)
def chat(
    req: schemas.ChatRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    llm_key = resolve_llm_key(db, user)
    if not llm_key:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "No LLM key available. Add your own key in settings, or the server must "
            "be configured with a shared LLM_API_KEY.",
        )
    reply, events, awaiting_user = run_turn(
        conversation_id=req.conversation_id,
        message=req.message,
        db=db,
        user_id=user.id,
        llm_key=llm_key,
        tz=req.tz,
    )
    return schemas.ChatResponse(
        conversation_id=req.conversation_id,
        reply=reply,
        events=events,
        awaiting_user=awaiting_user,
    )
