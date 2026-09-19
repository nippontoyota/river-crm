import io
import json
import logging
import os
import subprocess
import sys
from datetime import timedelta
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TransactionTestCase, override_settings
from django.utils import timezone

from leads.models import Lead, SystemConfig
from .models import Connection, Heartbeat, IntakeAudit, IntakeForm, MappingVersion, Submission


@override_settings(INTAKE_ENABLED=True, INTAKE_EXECUTION_MODE='database', CELERY_TASK_ALWAYS_EAGER=False,
                   DEBUG=False, SECRET_KEY='preflight-test-signing-key',
                   INTAKE_SECRETS={'main-meta': {'access_token': 'private-token'}}, META_GRAPH_VERSION='v99.0',
                   META_APP_SECRET='private-app-secret', META_VERIFY_TOKEN='private-verify-token',
                   SUPABASE_URL='https://storage.example', SUPABASE_SECRET_KEY='private-storage-key', SUPABASE_BUCKET='test')
class PreflightTests(TransactionTestCase):
    def setUp(self):
        SystemConfig.objects.update_or_create(pk=1, defaults={'lists': {'sources': ['META']}})
        self.connection = Connection.objects.create(name='Meta', origin='META', source='META', secret_ref='main-meta', enabled=True)
        self.connection.activated_at = timezone.now() - timedelta(days=2)
        self.connection.save()
        self.form = IntakeForm.objects.create(connection=self.connection, external_id='123', page_id='456', enabled=True, activated_at=self.connection.activated_at)
        MappingVersion.objects.create(form=self.form, version=1, rules={'required': ['name', 'phone', 'email', 'city']})
        self.out = io.StringIO()

    def graph(self, connection, path, params):
        if path == '123':
            return {'id': '123', 'page': {'id': '456'}}
        if path == '123/leads':
            self.assertEqual(params['limit'], 5)
            return {'data': [{'id': '789', 'created_time': (timezone.now() - timedelta(hours=1)).isoformat()}]}
        return {'id': '789', 'form_id': '123', 'created_time': (timezone.now() - timedelta(hours=1)).isoformat(),
                'field_data': [{'name': 'full_name', 'values': ['Private Customer']}, {'name': 'phone_number', 'values': ['9876543210']}]}

    def run_check(self):
        call_command('intake_check_credentials', stdout=self.out)

    def test_real_fetch_mapping_preview_is_read_only_and_redacted(self):
        before = IntakeForm.objects.values().get()
        with patch('intake.meta.graph', side_effect=self.graph), patch('intake.management.commands.intake_check_credentials.graph', side_effect=self.graph):
            self.run_check()
        self.assertEqual(IntakeForm.objects.values().get(), before)
        for model in (Lead, Submission, IntakeAudit, Heartbeat):
            self.assertFalse(model.objects.exists())
        output = self.out.getvalue()
        self.assertIn('PASS sample retrieval', output)
        self.assertIn('review_fields=["city", "email"]', output)
        self.assertIn('phone_number', output)
        for private in ('Private Customer', '9876543210', 'private-token', 'private-app-secret', 'private-storage-key'):
            self.assertNotIn(private, output)

    def test_no_sample_does_not_claim_complete_success(self):
        with patch('intake.management.commands.intake_check_credentials.graph', side_effect=self.graph), patch('intake.meta.graph', return_value={'data': []}):
            with self.assertRaisesMessage(CommandError, 'sample_retrieval_not_demonstrated'):
                self.run_check()
        self.assertIn('access succeeded; sample retrieval not yet demonstrated', self.out.getvalue())

    def test_actions_entrypoint_checks_migrations_and_preserves_optional_key_fallbacks(self):
        from background import main
        self.addCleanup(logging.disable, logging.root.manager.disable)
        env = {'DATABASE_URL': 'postgresql://fixture/test', 'DJANGO_SECRET_KEY': 'fixture-signing-key',
               'SUPABASE_URL': 'https://example.test', 'SUPABASE_SECRET_KEY': 'fixture-storage-key',
               'SUPABASE_UPLOAD_BUCKET': 'test', 'JWT_SIGNING_KEY': '', 'INTAKE_FINGERPRINT_KEY': ''}
        with patch.dict(os.environ, env), patch('sys.argv', ['background.py', 'preflight']), redirect_stdout(self.out), \
                patch('intake.meta.graph', side_effect=self.graph), patch('intake.management.commands.intake_check_credentials.graph', side_effect=self.graph):
            self.assertEqual(main(), 0)
            self.assertNotIn('JWT_SIGNING_KEY', os.environ)
            self.assertNotIn('INTAKE_FINGERPRINT_KEY', os.environ)
        self.assertIn('PASS sample retrieval', self.out.getvalue())
        self.assertFalse(Heartbeat.objects.exists())
        self.assertFalse(Submission.objects.exists())

    def test_ownership_mismatch_and_missing_config_are_redacted(self):
        with patch('intake.management.commands.intake_check_credentials.graph', return_value={'id': '123', 'page': {'id': '999'}}):
            with self.assertRaisesMessage(CommandError, 'meta_form_ownership_mismatch'):
                self.run_check()
        with override_settings(INTAKE_SECRETS={}):
            with self.assertRaisesMessage(CommandError, 'configuration_required'):
                self.run_check()
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.paused_reason, '')

    def test_token_permissions_rate_limit_and_timeout_errors_are_redacted(self):
        cases = [(400, 190, 'meta_access_required'), (403, 200, 'meta_access_required'), (429, 4, 'meta_temporarily_unavailable')]
        for status, code, expected in cases:
            error = HTTPError('https://graph.facebook.com/private-token', status, 'private-token', {}, io.BytesIO(json.dumps({'error': {'code': code, 'message': 'Private Customer'}}).encode()))
            with patch('intake.meta.build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaisesMessage(CommandError, expected) as caught:
                    self.run_check()
            self.assertNotIn('Private', str(caught.exception))
        with patch('intake.meta.build_opener') as opener:
            opener.return_value.open.side_effect = TimeoutError('private-token')
            with self.assertRaisesMessage(CommandError, 'meta_temporarily_unavailable'):
                self.run_check()
        self.assertNotIn('private-token', self.out.getvalue())


class BackgroundLogTests(SimpleTestCase):
    def test_startup_error_does_not_print_secret_json_or_traceback(self):
        env = {**os.environ, 'INTAKE_SECRETS_JSON': '{"private-token": invalid}', 'DJANGO_SECRET_KEY': 'private-signing-key',
               'DATABASE_URL': 'postgresql://private:private-password@127.0.0.1/test', 'SUPABASE_URL': 'https://example.test',
               'SUPABASE_SECRET_KEY': 'private-storage-key', 'SUPABASE_UPLOAD_BUCKET': 'test'}
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / 'background.py'), 'preflight'],
                                env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1)
        self.assertIn('FAIL background_run_failed', result.stdout)
        self.assertEqual(result.stderr, '')
        self.assertNotIn('private', result.stdout)
