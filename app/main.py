import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401 - ensure models are registered on Base
from .config import get_settings
from .db import Base, engine
from .logging_config import setup_logging
from .routers import (
    budgets,
    capture_rules,
    categories,
    chat,
    dashboard,
    investments,
    settings,
    transactions,
)

# Install our colored, timing-friendly logging before anything logs.
setup_logging(get_settings().log_level)


log = logging.getLogger("app.startup")


def _init_schema() -> None:
    """Bring the database schema up to date.

    Schema is Alembic-managed: on startup we run ``alembic upgrade head`` so a
    fresh database is created (and an existing one migrated) from the versioned
    migrations. If Alembic can't run for any reason, we fall back to
    ``create_all`` so local/dev startup never hard-fails.
    """
    try:
        from alembic import command
        from alembic.config import Config

        server_dir = Path(__file__).resolve().parent.parent
        # Build the Config WITHOUT the .ini file: passing the ini makes Alembic's
        # env.py run fileConfig(), which (disable_existing_loggers=True) would
        # wipe uvicorn's error/access loggers and silence all request logs.
        # We point it at the migrations dir directly instead; env.py reads the
        # DB URL from app settings.
        cfg = Config()
        cfg.set_main_option("script_location", str(server_dir / "alembic"))
        command.upgrade(cfg, "head")
        log.info("Database schema is at Alembic head.")
    except Exception as exc:  # noqa: BLE001 - dev-friendly fallback
        log.warning("Alembic upgrade failed (%s); falling back to create_all.", exc)
        Base.metadata.create_all(bind=engine)


def create_app() -> FastAPI:
    _init_schema()

    app = FastAPI(title="Finance Tracker API", version="0.1.0")

    # CORS. The mobile app calls the API directly (not from a browser), so the
    # default is "*". Set CORS_ALLOW_ORIGINS to a comma-separated allowlist to
    # lock it down. Auth is Bearer-token (no cookies), so we don't enable
    # credentialed CORS — a wildcard origin with credentials is invalid anyway.
    origins = [o.strip() for o in get_settings().cors_allow_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(categories.router)
    app.include_router(transactions.router)
    app.include_router(capture_rules.router)
    app.include_router(budgets.router)
    app.include_router(investments.router)
    app.include_router(dashboard.router)
    app.include_router(chat.router)
    app.include_router(settings.router)

    @app.get("/", tags=["meta"])
    def root() -> dict[str, str]:
        return {"message": "Finance Tracker API. See /docs for the OpenAPI UI."}

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
