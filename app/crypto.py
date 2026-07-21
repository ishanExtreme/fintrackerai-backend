"""Encryption + resolution for bring-your-own LLM keys.

Per-user LLM API keys are stored Fernet-encrypted (never plaintext). The active
key for a request is the user's own key if present, else the shared server key
(`LLM_API_KEY`).
"""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from . import models
from .config import get_settings


class EncryptionNotConfigured(RuntimeError):
    """Raised when a BYO key operation is attempted without FERNET_KEY set."""


def _fernet() -> Fernet:
    key = get_settings().fernet_key
    if not key:
        raise EncryptionNotConfigured(
            "FERNET_KEY is not set — cannot store per-user LLM keys."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def resolve_llm_key(db: Session, user: models.User) -> str | None:
    """The Gemini key to use for this user: their own (decrypted) or the shared."""
    cred = (
        db.query(models.LlmCredential)
        .filter(models.LlmCredential.user_id == user.id)
        .first()
    )
    if cred:
        try:
            return decrypt(cred.encrypted_key)
        except (InvalidToken, EncryptionNotConfigured):
            # Corrupt/undecryptable stored key — fall back to the shared key.
            pass
    return get_settings().llm_api_key or None


def resolve_sms_llm_key(db: Session, user: models.User) -> str | None:
    """The key for this user's SMS-capture agent.

    Prefers the dedicated SMS key; if unset, falls back to the chat key, then
    the shared server key — so SMS capture keeps working even when only a chat
    key (or the shared key) is configured.
    """
    cred = (
        db.query(models.SmsLlmCredential)
        .filter(models.SmsLlmCredential.user_id == user.id)
        .first()
    )
    if cred:
        try:
            return decrypt(cred.encrypted_key)
        except (InvalidToken, EncryptionNotConfigured):
            pass
    return resolve_llm_key(db, user)


def resolve_sms_llm_model(db: Session, user: models.User) -> str | None:
    """The ``provider:model`` override for this user's SMS-capture agent.

    Order: per-user SMS model → ``SMS_LLM_MODEL`` env → ``None`` (``get_model``
    then falls back to ``LLM_MODEL``).
    """
    cred = (
        db.query(models.SmsLlmCredential)
        .filter(models.SmsLlmCredential.user_id == user.id)
        .first()
    )
    if cred and cred.model:
        return cred.model
    return get_settings().sms_llm_model or None
