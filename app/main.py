from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models  # noqa: F401 - ensure models are registered on Base
from .db import Base, engine
from .routers import budgets, categories, dashboard, investments, transactions


def create_app() -> FastAPI:
    # Phase 1 uses create_all; a follow-up will switch to Alembic migrations.
    Base.metadata.create_all(bind=engine)

    app = FastAPI(title="Finance Tracker API", version="0.1.0")

    # Mobile app runs on-device; allow cross-origin during development.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(categories.router)
    app.include_router(transactions.router)
    app.include_router(budgets.router)
    app.include_router(investments.router)
    app.include_router(dashboard.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
