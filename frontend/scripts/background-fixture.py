"""Local-only browser fixture. DATABASE_URL must point to test_crm_background_browser."""
import os
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

url = os.environ.get('DATABASE_URL', '')
parsed = urlparse(url)
if parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.path != '/test_crm_background_browser':
    raise SystemExit('Use an isolated localhost DATABASE_URL named test_crm_background_browser.')
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))
os.environ.update(DJANGO_SETTINGS_MODULE='config.settings', DJANGO_DEBUG='true',
    DJANGO_SECRET_KEY='isolated-background-browser-signing-key', INTAKE_EXECUTION_MODE='database',
    INTAKE_ENABLED='true', CELERY_TASK_ALWAYS_EAGER='false', META_APP_SECRET='isolated-meta-test-secret',
    META_VERIFY_TOKEN='fixture-verify', META_GRAPH_VERSION='v99.0',
    INTAKE_SECRETS_JSON='{"fixture":{"access_token":"fixture-only"}}',
    SUPABASE_URL='', SUPABASE_SECRET_KEY='', SUPABASE_SERVICE_ROLE_KEY='', CACHE_URL='',
    CORS_ALLOWED_ORIGINS='http://localhost:3064', CSRF_TRUSTED_ORIGINS='http://localhost:3064')
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from accounts.models import User
from intake.models import Connection, Heartbeat, IntakeForm
from leads.models import SystemConfig

mode = sys.argv[1]
with override_settings(BASE_DIR=Path('/tmp/crm-background-browser'), PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
                       REST_FRAMEWORK={**settings.REST_FRAMEWORK, 'DEFAULT_THROTTLE_RATES': {'anon': '10000/minute', 'user': '10000/minute'}}):
    if mode == 'seed':
        import psycopg
        with psycopg.connect(url, dbname='postgres', autocommit=True) as connection:
            if not connection.execute("SELECT 1 FROM pg_database WHERE datname='test_crm_background_browser'").fetchone():
                connection.execute('CREATE DATABASE test_crm_background_browser TEMPLATE template0 ENCODING \'UTF8\'')
        call_command('migrate', verbosity=0)
        call_command('flush', interactive=False, verbosity=0)
        from feedback.models import FeedbackState
        FeedbackState.objects.create(pk=1)
        User.objects.create_user(email='background-browser@example.com', password='BackgroundBrowser123!', role='ADMIN')
        SystemConfig.objects.update_or_create(pk=1, defaults={'lists': {'sources': ['META']}})
        connection = Connection.objects.create(name='Background Meta fixture', origin='META', source='META', secret_ref='fixture', enabled=True, activated_at=timezone.now() - timedelta(days=2))
        IntakeForm.objects.create(connection=connection, name='River Indie fixture', page_id='456', external_id='123', enabled=True, activated_at=connection.activated_at)
    elif mode == 'process':
        def graph(connection, path, params):
            created = (timezone.now() - timedelta(hours=1)).isoformat()
            if path == '123/leads':
                return {'data': [{'id': value, 'created_time': created} for value in ('222', '333')]}
            if path == '123':
                return {'id': '123', 'page': {'id': '456'}}
            return {'id': path, 'form_id': '123', 'created_time': created, 'field_data': [
                {'name': 'full_name', 'values': ['Automatic Customer ' + path]},
                {'name': 'phone_number', 'values': ['9876543' + path]}]}
        with patch('intake.meta.graph', side_effect=graph):
            call_command('intake_process_pending', automatic_meta=True, reminders=True)
    elif mode == 'error':
        IntakeForm.objects.update(fetch_requested_at=None, last_reconciled_at=timezone.now() - timedelta(minutes=61), reconcile_error='meta_temporarily_unavailable')
        Heartbeat.objects.filter(name='processor_success').update(seen_at=timezone.now() - timedelta(minutes=16))
    elif mode == 'serve':
        call_command('runserver', '127.0.0.1:8064', use_reloader=False)
    else:
        raise SystemExit('Use seed, process, error or serve')
