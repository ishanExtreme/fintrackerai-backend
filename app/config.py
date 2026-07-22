from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: str = "INFO"  # DEBUG shows full LLM payloads (system prompt + history)

    # Comma-separated origins, or "*". The mobile app calls the API directly (not
    # from a browser), so the default is permissive; lock down for a web frontend.
    cors_allow_origins: str = "*"

    database_url: str = "sqlite:///./finance.db"

    # "firebase" (verify Firebase ID tokens) or "dev" (trust X-Dev-* headers)
    auth_mode: str = "firebase"
    firebase_credentials_file: str | None = None
    # The service-account JSON itself (raw or base64). Preferred in production so
    # no secret file is baked into the image. Takes precedence over the file.
    firebase_credentials_json: str = ""
    # Normally inferred from the credential; only needed for the ADC fallback.
    firebase_project_id: str = ""

    # LangChain `provider:model` string; swap provider/model via env only.
    llm_model: str = "google_genai:gemini-3.5-flash"
    # Shared fallback key, used when a user has not supplied their own.
    llm_api_key: str = ""
    llm_timeout_s: float = 45.0
    llm_max_retries: int = 2
    # Cap on agent loop steps (model + tool cycles) per turn.
    agent_recursion_limit: int = 12

    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str | None = None

    # Separate, usually cheaper, model for SMS extraction. Falls back to llm_model.
    sms_llm_model: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
