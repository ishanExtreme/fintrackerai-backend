from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Logging
    log_level: str = "INFO"  # DEBUG shows full LLM payloads (system prompt + history)

    # Database
    database_url: str = "sqlite:///./finance.db"

    # Auth: "firebase" (verify Firebase ID tokens) or "dev" (trust X-Dev-* headers)
    auth_mode: str = "firebase"
    firebase_credentials_file: str | None = None

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
