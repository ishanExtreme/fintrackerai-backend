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


# A separate key/model for the SMS extraction agent, so it can run a
# cheaper/faster model than the conversational agent. Falls back to the chat
# key + SMS_LLM_MODEL/LLM_MODEL when unset (see crypto.resolve_sms_llm_*).


@router.get("/sms-llm-key", response_model=schemas.LlmKeyStatus)
def get_sms_llm_key_status(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cred = (
        db.query(models.SmsLlmCredential)
        .filter(models.SmsLlmCredential.user_id == user.id)
        .first()
    )
    if cred:
        return schemas.LlmKeyStatus(
            configured=True, provider=cred.provider, using="user", model=cred.model
        )
    # No dedicated SMS key: extraction reuses the chat/shared key.
    has_chat = (
        db.query(models.LlmCredential)
        .filter(models.LlmCredential.user_id == user.id)
        .first()
        is not None
    )
    settings = get_settings()
    if has_chat:
        using = "chat"
    elif settings.llm_api_key:
        using = "shared"
    else:
        using = "none"
    return schemas.LlmKeyStatus(
        configured=False,
        provider=None,
        using=using,
        model=settings.sms_llm_model or None,
    )


@router.put("/sms-llm-key", response_model=schemas.LlmKeyStatus)
def set_sms_llm_key(
    payload: schemas.SmsLlmKeyIn,
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
    model = (payload.model or "").strip() or None
    cred = (
        db.query(models.SmsLlmCredential)
        .filter(models.SmsLlmCredential.user_id == user.id)
        .first()
    )
    if cred:
        cred.provider = payload.provider
        cred.encrypted_key = encrypted
        cred.model = model
    else:
        cred = models.SmsLlmCredential(
            user_id=user.id,
            provider=payload.provider,
            encrypted_key=encrypted,
            model=model,
        )
        db.add(cred)
    db.commit()
    return schemas.LlmKeyStatus(
        configured=True, provider=payload.provider, using="user", model=model
    )


@router.delete("/sms-llm-key", status_code=status.HTTP_204_NO_CONTENT)
def delete_sms_llm_key(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    cred = (
        db.query(models.SmsLlmCredential)
        .filter(models.SmsLlmCredential.user_id == user.id)
        .first()
    )
    if cred:
        db.delete(cred)
        db.commit()
    return None
