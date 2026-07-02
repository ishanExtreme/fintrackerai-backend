from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite:///./finance.db"

    # Auth: "firebase" (verify Firebase ID tokens) or "dev" (trust X-Dev-* headers)
    auth_mode: str = "firebase"
    firebase_credentials_file: str | None = None

    # LLM (Phase 2)
    anthropic_api_key: str | None = None
    fernet_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
