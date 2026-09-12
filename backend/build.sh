#!/usr/bin/env bash
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
# Migrations run as the web service's required pre-deploy command.
