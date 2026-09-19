#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
# Existing manually configured Render services may not have a pre-deploy command.
# migrate is idempotent when the pre-deploy step also runs it.
python manage.py migrate --noinput
