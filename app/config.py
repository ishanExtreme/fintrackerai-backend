from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Logging
    log_level: str = "INFO"  # DEBUG shows full LLM payloads (system prompt + history)

    # CORS: comma-separated list of allowed origins, or "*" for any (default).
    # The mobile app talks to the API directly (not from a browser), so the
    # default is permissive; lock this down if you expose a web frontend.
    cors_allow_origins: str = "*"

    # Database
    database_url: str = "sqlite:///./finance.db"

    # Auth: "firebase" (verify Firebase ID tokens) or "dev" (trust X-Dev-* headers)
    auth_mode: str = "firebase"
    # Path to the service-account JSON downloaded from the Firebase console.
    firebase_credentials_file: str | None = None
    # Alternative to the file path: the raw service-account JSON itself (raw or
    # base64-encoded). Prefer this in production (e.g. a single env var / secret)
    # so no secret file is baked into the image. Takes precedence over the file.
    firebase_credentials_json: str = ""
    # Optional Firebase project id. Normally inferred from the service-account
    # credential; only needed for the ADC fallback or to override.
    firebase_project_id: str = ""

    # --- LLM agent (Phase 2 — LangGraph orchestrator + Gemini) ---
    # LangChain `provider:model` string; swap provider/model via env only.
    llm_model: str = "google_genai:gemini-3.5-flash"
    # Shared server key (Gemini from ai.google.dev). Used when a user has not
    # supplied their own key. For google_genai it is passed to the model directly.
    llm_api_key: str = ""
    # Per-LLM-call timeout (seconds) and retry budget.
    llm_timeout_s: float = 45.0
    llm_max_retries: int = 2
    # Safety cap on agent loop steps (model + tool cycles) per turn.
    agent_recursion_limit: int = 12

    # Fernet key used to encrypt per-user bring-your-own LLM keys at rest.
    # Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    fernet_key: str | None = None

    # SMS capture: separate LLM model (cheaper/faster) for structured extraction.
    # Falls back to llm_model when unset. Same 'provider:model' string format.
    sms_llm_model: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
