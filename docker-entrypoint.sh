#!/usr/bin/env sh
set -e

# Bring the schema to Alembic head before starting the app.
#
# `alembic upgrade head` is correct and idempotent for a fresh database (it
# creates alembic_version and applies every migration) and for an already
# migrated one (it applies only what's new). The one case it can't handle is a
# database whose tables were created outside Alembic (a prior create_all
# fallback) and therefore has no alembic_version row: `upgrade` would try to
# CREATE tables that already exist. For that case we detect the pre-Alembic
# schema and `stamp head` to adopt it, then upgrade normally.
#
# We inspect the DB through the app's own SQLAlchemy engine so URL parsing,
# driver selection, and special characters in the password are all handled by
# SQLAlchemy — no hand-rolled URL rebuilding.
python3 -c "
import sys

from sqlalchemy import inspect

from app.db import engine

try:
    tables = set(inspect(engine).get_table_names())
except Exception as exc:
    print(f'ERROR: could not connect to the database: {exc}', file=sys.stderr)
    sys.exit(1)

if tables and 'alembic_version' not in tables:
    print('INFO: existing pre-Alembic schema found - stamping to head')
    import subprocess
    subprocess.check_call(['alembic', 'stamp', 'head'])
else:
    print('INFO: database is Alembic-managed (or empty) - upgrade will handle it')
"

alembic upgrade head

exec "$@"
