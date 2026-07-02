"""BYO LLM key: encryption round-trip, resolution precedence, and endpoints."""

from app import models
from app.config import get_settings
from app.crypto import decrypt, encrypt, resolve_llm_key
from app.db import SessionLocal


def test_encrypt_roundtrip_hides_plaintext():
    token = encrypt("super-secret-key")
    assert token != "super-secret-key"
    assert decrypt(token) == "super-secret-key"


def test_resolve_prefers_user_key_then_shared_then_none():
    db = SessionLocal()
    settings = get_settings()
    original = settings.llm_api_key
    try:
        u = models.User(firebase_uid="key-user")
        db.add(u)
        db.commit()
        db.refresh(u)

        settings.llm_api_key = ""
        assert resolve_llm_key(db, u) is None

        settings.llm_api_key = "shared-123"
        assert resolve_llm_key(db, u) == "shared-123"

        db.add(
            models.LlmCredential(
                user_id=u.id, provider="google_genai", encrypted_key=encrypt("user-abc")
            )
        )
        db.commit()
        assert resolve_llm_key(db, u) == "user-abc"
    finally:
        settings.llm_api_key = original
        db.close()


def test_llm_key_endpoints(client):
    assert client.get("/settings/llm-key").json()["configured"] is False

    put = client.put("/settings/llm-key", json={"api_key": "my-gemini-key"}).json()
    assert put["configured"] is True
    assert put["using"] == "user"

    status = client.get("/settings/llm-key").json()
    assert status["configured"] is True
    assert status["provider"] == "google_genai"

    client.delete("/settings/llm-key")
    assert client.get("/settings/llm-key").json()["configured"] is False
