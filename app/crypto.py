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
