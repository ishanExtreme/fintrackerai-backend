#!/usr/bin/env sh
set -e

# If alembic_version table doesn't exist (first run), stamp to head so that
# subsequent `alembic upgrade head` only applies new migration scripts.
python3 -c "
import os, subprocess, sys

url = os.environ.get('DATABASE_URL', '')
if not url:
    print('WARNING: DATABASE_URL not set, skipping migration check')
    sys.exit(0)

# Use SQLAlchemy to parse the URL and reconstruct a psycopg2-compatible one.
# This correctly handles passwords with special chars like '@' (encoded as %40).
from sqlalchemy.engine.url import make_url
parsed = make_url(url)
# Rebuild with plain 'postgresql' scheme (psycopg2 doesn't understand '+psycopg2')
from sqlalchemy.dialects import postgresql
clean_url = parsed.set(drivername='postgresql+psycopg2').render()

import psycopg2
conn = psycopg2.connect(clean_url)
cur = conn.cursor()
try:
    cur.execute(\"SELECT 1 FROM pg_class WHERE relname='alembic_version'\")
    exists = cur.fetchone() is not None
finally:
    cur.close()
    conn.close()

if not exists:
    print('INFO: alembic_version not found – stamping to head')
    subprocess.check_call(['uv', 'run', 'alembic', 'stamp', 'head'])
else:
    print('INFO: alembic_version exists – running upgrade')
"

uv run alembic upgrade head

exec "$@"