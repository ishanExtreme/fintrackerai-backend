# Finance Tracker — Server

FastAPI + PostgreSQL backend for an LLM-first, open-source personal finance
tracker. Phase 1 covers auth, the flexible category model, transactions
(incl. structured SMS ingest), budgets, investments, and dashboard aggregates.
Phase 2 adds the LLM chat agent (LangGraph orchestrator + Gemini) with
bring-your-own-key support.

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

## Features (Phase 2 — LLM chat agent)

- **LangGraph orchestrator + registered specialist nodes**: a supervisor LLM delegates to `expenses`, `budgets`, and
  `investments` nodes. Adding a capability = one node module + `register_node(...)`.
- **Gemini** via LangChain `init_chat_model("google_genai:gemini-3.5-flash")` —
  provider is a one-line config swap (`LLM_MODEL`).
- **Bring-your-own key:** each user can store their own Gemini key
  (`PUT /settings/llm-key`), Fernet-encrypted at rest; the server falls back to a
  shared `LLM_API_KEY` when the user has none.
- **`POST /chat`** — `{conversation_id, message}` → `{reply, events[], awaiting_user}`.
  "I spent 500 on biryani" records a Food expense; "spent 1200 on a movie ticket"
  auto-creates a *Movie tickets* sub-category under *Personal*; "how much is left
  for food this month?" answers from the budget; adding an expense that nears/exceeds
  a budget returns a warning in the reply and a `budget_warning` event.
- `ask_user` clarification pauses the turn (LangGraph `interrupt`) and resumes on
  the next message with the same `conversation_id`. History uses an in-memory
  checkpointer for now (Postgres checkpointer is a documented follow-up).

> Runs the agent **synchronously** (`graph.invoke`) because the finance tools do
> synchronous DB writes — the orchestrator/node/registry structure otherwise

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
