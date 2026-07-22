# Contributing to Finance Tracker (server)

Thanks for your interest in contributing! This is the FastAPI backend for an
LLM-first, self-hostable personal finance tracker. Contributions of all
kinds — bug reports, features, docs, tests — are welcome.

## Ground rules

- **Never commit secrets.** `.env`, `secrets/`, and any service-account or
  `*-service-account.json` / `firebase-*.json` files are gitignored — keep it
  that way. Use `.env.example` to document new variables (with placeholder
  values only).
- Be respectful and constructive in issues and reviews.
- By contributing, you agree your contributions are licensed under the
  project's [MIT License](LICENSE).

## Development setup

Uses [uv](https://docs.astral.sh/uv/) for env + dependency management.

```bash
uv venv
uv pip install -e ".[dev]"

# Fastest inner loop: SQLite + dev auth, no Firebase or LLM key needed.
DATABASE_URL="sqlite:///./finance.db" AUTH_MODE=dev \
  uv run uvicorn app.main:app --reload
# API at http://localhost:8000 , docs at http://localhost:8000/docs
```

In `dev` auth mode every request is `dev-user`; pass `X-Dev-Uid` / `X-Dev-Email`
headers to simulate other users. See [README.md](README.md) for the full
configuration reference and Docker/Firebase setup.

## Running tests

```bash
uv run pytest
```

Tests use SQLite + `dev` auth (configured in [`tests/conftest.py`](tests/conftest.py)),
so they need no Firebase credentials and make no network calls. **Please add or
update tests** for any behavior change, and make sure the full suite passes
before opening a PR.

## Project layout

```
app/
  main.py              # app factory + router wiring + startup migration
  config.py            # env-driven settings
  db.py, models.py     # SQLAlchemy engine/session + ORM models
  auth.py              # Firebase / dev auth dependency
  routers/             # HTTP endpoints (categories, transactions, budgets, …)
  services/            # business logic
    agent/             # LangGraph orchestrator + specialist nodes (chat)
    sms_capture.py     # LLM extraction of expenses from SMS
    capture_rules.py   # "remember" payee/place auto-labeling
alembic/               # migrations (applied automatically on startup)
tests/                 # pytest suite (SQLite + dev auth)
```

## Making changes

1. **Branch** off `dev` (`git checkout -b my-change`).
2. Keep changes focused; match the style and comment density of surrounding
   code.
3. **Database schema changes require an Alembic migration.** After editing
   `models.py`, generate one:
   ```bash
   alembic revision --autogenerate -m "describe your change"
   ```
   Review the generated migration, then confirm `alembic upgrade head` applies
   cleanly on a fresh SQLite DB.
4. If you add or rename an environment variable, update both
   [`config.py`](app/config.py) and [`.env.example`](.env.example), and mention
   it in the README config table.
5. Run `uv run pytest` and make sure everything is green.

## Opening a pull request

- Describe **what** changed and **why**; link any related issue.
- Include test coverage for new behavior.
- Note any new environment variables, migrations, or breaking changes.
- Keep the PR scoped to one logical change where possible.

## Reporting bugs / requesting features

Open a GitHub issue with:

- **Bugs:** what you expected, what happened, steps to reproduce, and relevant
  logs (run with `LOG_LEVEL=DEBUG` for detail). **Redact any secrets or personal
  financial data** before pasting logs.
- **Features:** the problem you're trying to solve and, if you have one, a
  proposed approach.

Thanks again for helping make this project better!
