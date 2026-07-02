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
cp .env.example .env          # set AUTH_MODE, Firebase creds, LLM key, etc.
docker compose up --build
# API at http://localhost:8000 , docs at http://localhost:8000/docs
```

`docker compose` reads `server/.env` automatically for the values in
`docker-compose.yml`. The bundled Postgres (`db`) is exposed on host port `5435`.

> **Changed the DB user/password/name?** Postgres only initializes them on the
> first run of an empty data volume. After changing them, recreate the volume:
> `docker compose down -v && docker compose up`.

### Try it in 30 seconds (no Firebase, no LLM key)

For a quick local trial you can skip Firebase entirely with `dev` auth:

```bash
printf 'AUTH_MODE=dev\nFERNET_KEY=%s\n' \
  "$(python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')" > .env
docker compose up --build
# Every request is the "dev-user"; add X-Dev-Uid to simulate other users.
curl -X POST localhost:8000/transactions -H 'content-type: application/json' \
  -d '{"amount":500,"category_id":1,"note":"biryani"}'
```

`/chat` additionally needs an LLM key (see **Bring your own LLM key** below or set
a shared `LLM_API_KEY`).

### Configuration (`.env`)

| Var | Purpose |
|-----|---------|
| `DATABASE_URL` | SQLAlchemy URL. Compose sets this to the bundled Postgres. |
| `AUTH_MODE` | `firebase` (verify ID tokens) or `dev` (header-based, local only). |
| `FIREBASE_CREDENTIALS_FILE` | Service-account JSON path (firebase mode). |
| `LLM_MODEL` | LangChain `provider:model`, e.g. `google_genai:gemini-3.5-flash`. |
| `LLM_API_KEY` | Shared server LLM key; used when a user has no key of their own. |
| `FERNET_KEY` | Encrypts per-user BYO LLM keys at rest (required to store them). |
| `LOG_LEVEL` | `INFO` (agent timing + LLM/tool lines) or `DEBUG` (full LLM payloads). |

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

## Bring your own LLM key

Each user can store their own LLM (Gemini) key — it's Fernet-encrypted at rest
and used instead of the shared `LLM_API_KEY`. Requires `FERNET_KEY` to be set on
the server.

```bash
# Store your key (authenticated as the user):
curl -X PUT localhost:8000/settings/llm-key \
  -H 'content-type: application/json' -d '{"api_key":"<your-gemini-key>"}'

# Check status (never returns the key):
curl localhost:8000/settings/llm-key      # {"configured":true,"provider":"google_genai","using":"user"}

# Remove it (falls back to the shared server key, if any):
curl -X DELETE localhost:8000/settings/llm-key
```

Key resolution per request: **user's own key → shared `LLM_API_KEY` → error**.

## Notes

- Schema is created via `Base.metadata.create_all` for now; Alembic migrations
  are a documented follow-up before production.
- Conversation history uses an in-memory LangGraph checkpointer; a Postgres
  checkpointer (so history/`ask_user` survive restarts) is a documented follow-up.

## License

MIT — see [`LICENSE`](LICENSE).
