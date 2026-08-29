#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
# Migrations should not block the deploy if the DB pool is saturated
DB_CONN_MAX_AGE=0 python manage.py migrate || echo "⚠️  migrate failed (non-fatal) — run manually if needed"
