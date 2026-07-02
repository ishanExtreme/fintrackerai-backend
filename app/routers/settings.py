"""User settings — bring-your-own LLM key management.

The key is stored Fernet-encrypted; it is never returned by the API.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..auth import get_current_user
from ..config import get_settings
from ..crypto import EncryptionNotConfigured, encrypt
from ..db import get_db

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/llm-key", response_model=schemas.LlmKeyStatus)
def get_llm_key_status(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cred = (
        db.query(models.LlmCredential)
        .filter(models.LlmCredential.user_id == user.id)
        .first()
    )
    if cred:
        return schemas.LlmKeyStatus(configured=True, provider=cred.provider, using="user")
    shared = bool(get_settings().llm_api_key)
    return schemas.LlmKeyStatus(
        configured=False, provider=None, using="shared" if shared else "none"
    )


@router.put("/llm-key", response_model=schemas.LlmKeyStatus)
def set_llm_key(
    payload: schemas.LlmKeyIn,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    try:
        encrypted = encrypt(payload.api_key)
    except EncryptionNotConfigured:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Server has no FERNET_KEY configured, so per-user keys can't be stored.",
        )
    cred = (
        db.query(models.LlmCredential)
        .filter(models.LlmCredential.user_id == user.id)
        .first()
    )
    if cred:
        cred.provider = payload.provider
        cred.encrypted_key = encrypted
    else:
        cred = models.LlmCredential(
            user_id=user.id, provider=payload.provider, encrypted_key=encrypted
        )
        db.add(cred)
    db.commit()
    return schemas.LlmKeyStatus(configured=True, provider=payload.provider, using="user")


@router.delete("/llm-key", status_code=status.HTTP_204_NO_CONTENT)
def delete_llm_key(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cred = (
        db.query(models.LlmCredential)
        .filter(models.LlmCredential.user_id == user.id)
        .first()
    )
    if cred:
        db.delete(cred)
        db.commit()
    return None
