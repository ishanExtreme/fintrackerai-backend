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

# Use psycopg2 to check if alembic_version table exists
import psycopg2
conn = psycopg2.connect(url)
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
    print('INFO: alembic_version already exists – running upgrade')
"

uv run alembic upgrade head

exec "$@"