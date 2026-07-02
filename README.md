# Finance Tracker — Server

FastAPI + PostgreSQL backend for an LLM-first, open-source personal finance
tracker. Phase 1 covers auth, the flexible category model, transactions
(incl. structured SMS ingest), budgets, investments, and dashboard aggregates.
The LLM chat layer lands in Phase 2.

## Features (Phase 1)

- **Firebase Google auth** — the app signs in with Firebase and sends the ID
  token as `Authorization: Bearer <token>`. The server verifies it and
  gets-or-creates the user. A `dev` auth mode (header-based) exists for local
  testing.
- **Flexible, hierarchical categories** — any category can have a parent, so the
  LLM (or user) can create a parent (e.g. *Personal*) and a sub-category
  (e.g. *Movie tickets*) on the fly. Each carries `description`, `image`,
  `type`, `tags`, and `created_by` (`user` | `llm`).
- **Transactions** with an on-device **SMS ingest** endpoint that accepts only
  structured fields (never raw SMS text) and dedupes on a hash.
- **Per-category monthly budgets**; budget status rolls sub-category spend up
  into the parent's budget.
- **Investments** (amount-only per month — no returns/prices).
- **Dashboard aggregates** for spend-per-category, budget status, and monthly
  investment totals.

## Run locally (Docker)

```bash
cp .env.example .env          # set AUTH_MODE, Firebase creds, etc.
docker compose up --build
# API at http://localhost:8000 , docs at http://localhost:8000/docs
```

## Run locally (no Docker)

Uses [uv](https://docs.astral.sh/uv/) for env + dependency management.

```bash
uv venv                 # create .venv
uv pip install -e ".[dev]"
# Quick start with sqlite + dev auth:
DATABASE_URL="sqlite:///./finance.db" AUTH_MODE=dev uv run uvicorn app.main:app --reload
```

In `dev` auth mode, pass `X-Dev-Uid` / `X-Dev-Email` headers to simulate a user
(defaults to `dev-user`).

## Tests

```bash
uv pip install -e ".[dev]"
uv run pytest
```

Tests use SQLite + `dev` auth, so no Firebase credentials are required.

## Auth modes

| `AUTH_MODE` | Behavior |
|-------------|----------|
| `firebase`  | Verifies Firebase ID tokens (`Authorization: Bearer`). Needs `FIREBASE_CREDENTIALS_FILE` or Application Default Credentials. |
| `dev`       | Trusts `X-Dev-Uid` / `X-Dev-Email` headers. **Local/testing only.** |

## Notes

- Schema is created via `Base.metadata.create_all` for Phase 1; a follow-up will
  introduce Alembic migrations.
- BYO LLM key (`LlmCredential`, encrypted via `FERNET_KEY`) and the `/chat`
  tool-calling endpoint arrive in Phase 2.
