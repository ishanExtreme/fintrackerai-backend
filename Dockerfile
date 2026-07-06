FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Install uv (same tooling as local dev) and use it to install the project.
RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY app ./app
COPY alembic.ini alembic/ ./alembic/
RUN uv pip install --system --no-cache .

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /srv
USER appuser

EXPOSE 8000

# Run database migrations on startup, then start the server.
CMD ["sh", "-c", "uv run alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
