#!/usr/bin/env sh
set -e

# If alembic_version table doesn't exist (first run), stamp to head so that
# subsequent `alembic upgrade head` only applies new migration scripts.
python3 -c "
import os, subprocess, sys, re

url = os.environ.get('DATABASE_URL', '')
if not url:
    print('WARNING: DATABASE_URL not set, skipping migration check')
    sys.exit(0)

# psycopg2.connect does not understand 'postgresql+psycopg2://' scheme;
# strip the '+psycopg2' suffix so psycopg2 can parse it.
clean_url = re.sub(r'\+psycopg2$', '', url)

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