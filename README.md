# Finance Tracker — Server

An **LLM-first, self-hostable** personal finance tracker backend. It turns
natural language (*"I spent 500 on biryani"*) and bank/UPI SMS into categorized
transactions, tracks per-category monthly budgets and investments, and serves
dashboard aggregates.

This is the backend/API only. It powers a companion Android (Flutter) app but is
a standalone HTTP service — you can self-host it and point any client at it.
....

> A reference instance is deployed on Google Cloud Run:
> `https://fintrackerai-backend-481204614409.asia-south1.run.app`
> (`/health` for a liveness check, `/docs` for the OpenAPI UI).

## Features

- **Talk to it in plain language — that's the whole interface.** Instead of
  forms and menus, you *tell* the app what you want and an LLM agent does it:
  *"I spent 500 on biryani"* records a Food expense, *"set my food budget to
  8000 this month"* sets a budget, *"how much is left for food?"* answers from
  your spend, *"put 10k into my index fund"* logs an investment, and *"what did
  I spend on last weekend?"* searches your transactions. Recording expenses,
  creating categories, setting budgets, tracking investments, and querying it
  all happen through natural language — no forms required.
- **Per-user, hierarchical categories.** Any category can have a parent, so the
  LLM or the user can create a parent (*Personal*) and a sub-category
  (*Movie tickets*) on the fly. Each carries `description`, `type`, `tags`, and
  `created_by` (`user` | `llm`).
- **Transactions** with an on-device **SMS capture** pipeline: the phone gates
  OTP/junk locally, then financial SMS is sent to the server, where an LLM
  extracts structured fields (amount, counterparty, date, …). The phone also
  passes the **capture location** (reverse-geocoded to a place name) alongside
  the SMS, giving the LLM a strong extra signal to infer the *type* of payment —
  e.g. a charge near a restaurant reads as dining, near a fuel station as
  transport — so captures are categorized more accurately. Captures are deduped
  on a hash and land in a review queue.
- **Capture rules ("remember").** Teach the system to auto-label recurring
  payees/UPI ids or geofenced places so repeat captures are pre-categorized.
- **Per-category monthly budgets** with roll-up of sub-category spend into the
  parent, plus limit-reaching warnings surfaced by the chat agent.
- **Investments** (amount-only per month — no returns or live prices).
- **Dashboard aggregates** for spend-per-category, budget status, and monthly
  investment totals.
- **LangGraph chat agent (Gemini).** A supervisor LLM delegates to specialist
  nodes (`expenses`, `budgets`, `investments`, `expense_search`). The provider
  is a one-line config swap via `LLM_MODEL`.
- **Bring-your-own key.** Each user can store their own Gemini key
  (Fernet-encrypted at rest); the server falls back to a shared `LLM_API_KEY`.
  A separate, usually cheaper, key/model can be set just for SMS extraction.

## Quick start (30 seconds, no Firebase, no LLM key)

For a local trial you can skip Firebase entirely with `dev` auth and SQLite:

```bash
uv venv && uv pip install -e ".[dev]"
DATABASE_URL="sqlite:///./finance.db" AUTH_MODE=dev \
  uv run uvicorn app.main:app --reload
# API at http://localhost:8000 , docs at http://localhost:8000/docs
```

In `dev` mode every request is `dev-user`; pass `X-Dev-Uid` / `X-Dev-Email`
headers to simulate other users. `/chat` and SMS capture still need an LLM key
(see **Bring your own LLM key** below, or set a shared `LLM_API_KEY`).

## Self-host with Docker

```bash
cp .env.example .env      # fill in AUTH_MODE, Firebase creds, LLM key, FERNET_KEY
docker compose up --build
```

`docker compose` reads `./.env` automatically. This brings up the API on port
`8000` plus a bundled Postgres (exposed on host port `5435`). The schema is
migrated to the latest Alembic revision automatically on startup.

> **Changed the DB user/password/name?** Postgres only initializes those on the
> first run of an empty data volume. After changing them, recreate the volume:
> `docker compose down -v && docker compose up`.

## Configuration

All configuration is via environment variables (or a `.env` file). See
[`.env.example`](.env.example) for the annotated template. **Never commit real
secrets** — `.env` and `secrets/` are gitignored.

| Var | Purpose |
|-----|---------|
| `DATABASE_URL` | SQLAlchemy URL. Compose points this at the bundled Postgres; use `sqlite:///./finance.db` for a quick local run. |
| `AUTH_MODE` | `firebase` (verify ID tokens) or `dev` (header-based, **local only**). |
| `FIREBASE_CREDENTIALS_FILE` | Path to a Firebase service-account JSON (firebase mode). |
| `FIREBASE_CREDENTIALS_JSON` | The service-account JSON inline (raw or base64). Preferred in production so no secret file is baked into the image; takes precedence over the file. |
| `FIREBASE_PROJECT_ID` | Optional; normally inferred from the credential. |
| `LLM_MODEL` | LangChain `provider:model`, e.g. `google_genai:gemini-3.5-flash`. |
| `LLM_API_KEY` | Shared server LLM key; used when a user has no key of their own. Leave blank to require every user to bring their own. |
| `SMS_LLM_MODEL` | Optional cheaper/faster `provider:model` for SMS extraction; falls back to `LLM_MODEL`. |
| `FERNET_KEY` | Encrypts per-user BYO LLM keys at rest (required to store them). Generate with the command below. |
| `CORS_ALLOW_ORIGINS` | Comma-separated allowlist, or `*` (default). Restrict if you add a web frontend. |
| `LLM_TIMEOUT_S`, `LLM_MAX_RETRIES`, `AGENT_RECURSION_LIMIT` | Agent tuning. |
| `LOG_LEVEL` | `INFO` (timing + LLM/tool lines) or `DEBUG` (full LLM payloads). |

Generate a `FERNET_KEY`:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Auth modes

| `AUTH_MODE` | Behavior |
|-------------|----------|
| `firebase`  | Verifies Firebase ID tokens (`Authorization: Bearer`). Needs `FIREBASE_CREDENTIALS_JSON`/`FIREBASE_CREDENTIALS_FILE`, or Application Default Credentials. |
| `dev`       | Trusts `X-Dev-Uid` / `X-Dev-Email` headers. **Local/testing only.** |

To set up Firebase auth: create a Firebase project, enable Google Sign-In, and
download a service-account JSON from **Project settings → Service accounts**.
Point `FIREBASE_CREDENTIALS_FILE` at it, or paste the JSON into
`FIREBASE_CREDENTIALS_JSON` (recommended for hosted deployments).

## Bring your own LLM key

Each user can store their own Gemini key (from
[ai.google.dev](https://ai.google.dev)) — Fernet-encrypted at rest and used
instead of the shared `LLM_API_KEY`. Requires `FERNET_KEY` to be set.

```bash
# Store your key (authenticated as the user):
curl -X PUT localhost:8000/settings/llm-key \
  -H 'content-type: application/json' -d '{"api_key":"<your-gemini-key>"}'

# Check status (never returns the key):
curl localhost:8000/settings/llm-key   # {"configured":true,"provider":"google_genai","using":"user"}

# Remove it (falls back to the shared server key, if any):
curl -X DELETE localhost:8000/settings/llm-key
```

Key resolution per request: **user's own key → shared `LLM_API_KEY` → error**.
The SMS key resolves independently (`/settings/sms-llm-key`): **SMS key → chat
key → shared key**.

## API overview

Full interactive docs at `/docs`. Main route groups:

| Prefix | What |
|--------|------|
| `/categories` | CRUD + `/tree`; reparenting; per-user hierarchy. |
| `/transactions` | CRUD, `/ingest` (structured), `/capture` (SMS→LLM), `/review-batch`, filters (`source`, `reviewed`). |
| `/capture-rules` | Remember payees/places to auto-label future captures. |
| `/budgets` | Per-category monthly budgets + `/budget-status`. |
| `/investments` | Amount-only monthly investments. |
| `/dashboard` | `/spending`, `/budget-status`, `/investments` aggregates. |
| `/chat` | `{conversation_id, message}` → `{reply, events[], awaiting_user}`. |
| `/settings` | BYO LLM key + SMS LLM key management. |
| `/`, `/health` | Meta / liveness. |

## Tests

```bash
uv pip install -e ".[dev]"
uv run pytest
```

Tests use SQLite + `dev` auth, so no Firebase credentials or network calls are
required.

## Notes & known follow-ups

- **Migrations** are Alembic-managed and applied automatically on startup
  (`app.main._init_schema`), with a `create_all` fallback for local dev.
- **Conversation history** uses an in-memory LangGraph checkpointer, so chat
  history and paused `ask_user` turns are lost on restart. A Postgres
  checkpointer is the documented next step.
- **SMS capture** currently handles expenses only (`is_expense=false` is
  skipped); the DLT sender allowlist lives in the client, not the server.

## License

MIT — see [`LICENSE`](LICENSE). Copyright (c) 2026 Ishan Mishra.
