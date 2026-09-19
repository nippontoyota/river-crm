"""Brokerless integration checks; run against isolated PostgreSQL for real locks."""
import hashlib
import hmac
import io
import json
import signal
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import Lead, SystemConfig
from uploads.models import UploadBatch
from .meta import MetaFailure
from .models import Connection, Heartbeat, IntakeAudit, IntakeForm, MappingVersion, Submission
from .processor import ProcessingDeadline, fetch_page
from .services import accept
from .tasks import reconcile_form, reconcile_forms, sweep_receipts


@override_settings(INTAKE_ENABLED=True, INTAKE_EXECUTION_MODE='database', CELERY_TASK_ALWAYS_EAGER=True,
                   INTAKE_SECRETS={'meta': {'access_token': 'test-token'}}, META_APP_SECRET='test-secret',
                   META_VERIFY_TOKEN='test-verify', META_GRAPH_VERSION='v99.0',
                   PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ProcessorTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='processor@example.com', password='test', role='ADMIN')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        SystemConfig.objects.update_or_create(pk=1, defaults={'lists': {'sources': ['META']}})
        self.connection = Connection.objects.create(name='Meta', origin='META', source='META', secret_ref='meta', enabled=True, activated_at=timezone.now() - timedelta(days=2))
        self.form = IntakeForm.objects.create(connection=self.connection, name='Form', page_id='456', external_id='123', enabled=True, activated_at=self.connection.activated_at)
        self.path = f'/api/intake/forms/{self.form.pk}/fetch/'
        self.submitted = timezone.now() - timedelta(minutes=1)
        # Any accidental Celery publication fails this test, including eager execution.
        broker = patch('celery.app.task.Task.apply_async', side_effect=AssertionError('Broker must not be used'))
        self.broker = broker.start()
        self.addCleanup(broker.stop)

    def run_processor(self, **kwargs):
        out = io.StringIO()
        with self.captureOnCommitCallbacks(execute=True):
            call_command('intake_process_pending', stdout=out, **kwargs)
        self.broker.assert_not_called()
        return out.getvalue()

    def receipt(self, external_id='222'):
        with self.captureOnCommitCallbacks(execute=True), transaction.atomic():
            receipt, _ = accept(self.form, external_id)
        return receipt

    def graph(self, connection, path, params):
        if path == '123':
            return {'page': {'id': '456'}}
        if path == '999':
            return {'name': 'Test campaign'}
        return {'id': path, 'form_id': '123', 'created_time': self.submitted.isoformat(),
                'field_data': [{'name': 'full_name', 'values': ['Test customer']}, {'name': 'phone_number', 'values': ['9876543' + path]}],
                'campaign_id': '999'}

    def page(self, *ids, cursor=''):
        payload = {'data': [{'id': value, 'created_time': self.submitted.isoformat()} for value in ids]}
        if cursor:
            payload['paging'] = {'next': 'https://untrusted.example/never-follow', 'cursors': {'after': cursor}}
        return payload

    def test_signed_webhook_is_saved_without_graph_then_imported_once(self):
        event = {'object': 'page', 'entry': [{'id': '456', 'changes': [{'field': 'leadgen', 'value': {'form_id': '123', 'leadgen_id': '222'}}]}]}
        raw = json.dumps(event).encode()
        signature = 'sha256=' + hmac.new(b'test-secret', raw, hashlib.sha256).hexdigest()
        path = '/api/integrations/meta/webhook/'
        self.assertEqual(self.client.post(path, raw, content_type='application/json').status_code, 403)
        with patch('intake.meta.graph') as graph, self.captureOnCommitCallbacks(execute=True):
            for _ in range(2):
                self.assertEqual(self.client.post(path, raw, content_type='application/json', HTTP_X_HUB_SIGNATURE_256=signature).status_code, 200)
            graph.assert_not_called()
        self.assertEqual(Submission.objects.get().state, 'RECEIVED')
        self.assertFalse(Lead.objects.exists())
        with patch('intake.meta.graph', side_effect=self.graph), patch('intake.tasks.graph', side_effect=self.graph):
            self.run_processor()
        lead = Lead.objects.get()
        self.assertEqual(lead.status, 'FRESH')
        self.assertIsNone(lead.assigned_so_id)
        self.assertEqual(Submission.objects.get().campaign_name, 'Test campaign')
        with patch('intake.meta.graph') as graph:
            self.run_processor()
            graph.assert_not_called()
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(self.client.get('/api/leads/?page=1&status=FRESH').status_code, 200)

    def test_idle_processor_and_old_scheduler_never_poll_meta(self):
        with patch('intake.meta.graph') as graph:
            self.run_processor()
            sweep_receipts.run()
            reconcile_forms.run()
            reconcile_form.run(self.form.pk)
            graph.assert_not_called()
        health = self.client.get('/api/intake/connections/health/').data
        self.assertEqual(health['execution_mode'], 'database')
        self.assertIn('processor', health['heartbeats'])
        self.assertNotIn('test-token', str(health))
        self.broker.assert_not_called()

    def test_fetch_clicks_coalesce_and_non_admins_cannot_fetch(self):
        first = self.client.post(self.path)
        second = self.client.post(self.path)
        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.data, second.data)
        self.assertEqual(first.data['fetch_status'], 'queued')
        self.assertEqual(IntakeAudit.objects.filter(action='meta_fetch_requested').count(), 1)
        for role in ('CEO', 'SO', 'META_UPLOADER'):
            user = User.objects.create_user(email=f'{role}@example.com', password='test', role=role)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.post(self.path).status_code, 403)

    def test_fetch_rejects_disabled_paused_website_and_missing_credentials(self):
        for field, value in [('enabled', False), ('paused_reason', 'meta_access_required'), ('origin', 'WEBSITE')]:
            original = getattr(self.connection, field)
            setattr(self.connection, field, value)
            self.connection.save()
            self.assertEqual(self.client.post(self.path).status_code, 409)
            setattr(self.connection, field, original)
            self.connection.save()
        with override_settings(INTAKE_SECRETS={}):
            self.assertEqual(self.client.post(self.path).status_code, 409)
        with override_settings(INTAKE_EXECUTION_MODE='celery'):
            self.assertEqual(self.client.post(self.path).status_code, 409)
            with self.assertRaises(CommandError):
                self.run_processor()
        with override_settings(INTAKE_ENABLED=False):
            self.assertEqual(self.client.post(self.path).status_code, 409)

    def test_interrupted_fetch_resumes_page_and_repeated_ids_stay_unique(self):
        self.client.post(self.path)
        with patch('intake.meta.graph', return_value=self.page('222', cursor='page-two')), patch('intake.processor.process_submission.run', side_effect=ProcessingDeadline):
            self.assertIn('Time budget reached', self.run_processor())
        self.form.refresh_from_db()
        end = self.form.reconcile_end
        self.assertEqual(self.form.reconcile_cursor, 'page-two')
        self.assertIsNone(self.form.checkpoint)
        self.assertEqual(self.form.fetch_status, 'queued')
        calls = []
        def graph(connection, path, params):
            if path.endswith('/leads'):
                calls.append(dict(params))
                return self.page('222', '333')
            return self.graph(connection, path, params)
        with patch('intake.meta.graph', side_effect=graph), patch('intake.tasks.graph', side_effect=self.graph):
            self.run_processor()
        self.form.refresh_from_db()
        self.assertEqual(calls[0]['after'], 'page-two')
        self.assertEqual(self.form.checkpoint, end)
        self.assertEqual(self.form.fetch_status, 'completed')
        self.assertEqual(Lead.objects.count(), 2)
        self.assertEqual(Submission.objects.count(), 2)

    def test_interrupted_page_rolls_back_receipts_and_cursor_together(self):
        self.client.post(self.path)
        def interrupted(*args, **kwargs):
            accept(*args, **kwargs)
            raise ProcessingDeadline()
        with patch('intake.meta.graph', return_value=self.page('222', cursor='next')), patch('intake.processor.accept', side_effect=interrupted):
            with self.assertRaises(ProcessingDeadline):
                fetch_page(self.form.pk)
        self.form.refresh_from_db()
        self.assertFalse(Submission.objects.exists())
        self.assertEqual(self.form.reconcile_cursor, '')
        self.assertIsNone(self.form.checkpoint)
        self.assertIsNone(self.form.reconcile_lease_until)

    def test_fetch_failure_is_redacted_and_retry_keeps_fixed_window(self):
        self.client.post(self.path)
        with patch('intake.meta.graph', return_value=self.page('222', cursor='page-two')):
            fetch_page(self.form.pk)
        self.form.refresh_from_db()
        original_end = self.form.reconcile_end
        with patch('intake.meta.graph', side_effect=RuntimeError('secret customer payload')):
            fetch_page(self.form.pk)
        self.form.refresh_from_db()
        self.assertEqual(self.form.fetch_status, 'error')
        self.assertEqual(self.form.reconcile_error, 'reconciliation_temporarily_unavailable')
        self.assertIsNone(self.form.checkpoint)
        self.assertEqual(self.form.reconcile_cursor, 'page-two')
        self.client.post(self.path)
        with patch('intake.meta.graph', return_value=self.page()) as graph:
            fetch_page(self.form.pk)
            self.assertEqual(graph.call_args.args[2]['after'], 'page-two')
            self.form.refresh_from_db()
            self.assertEqual(self.form.checkpoint, original_end)
            self.assertEqual(self.form.fetch_status, 'completed')  # Retry retains the original fixed window.
            fetch_page(self.form.pk)
        self.form.refresh_from_db()
        self.assertEqual(self.form.fetch_status, 'completed')

    def test_token_failure_pauses_connection_and_receipts_remain_durable(self):
        self.receipt()
        self.client.post(self.path)
        with patch('intake.meta.graph', side_effect=MetaFailure('meta_access_required', pause=True)):
            self.run_processor()
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.paused_reason, 'meta_access_required')
        self.assertEqual(Submission.objects.get().state, 'RECEIVED')
        self.assertEqual(self.client.post(self.path).status_code, 409)
        self.assertFalse(Lead.objects.exists())

    def test_upload_is_queued_even_with_eager_true_and_runs_when_intake_disabled(self):
        content = b'name,phone,email,source,enquiry date,city,pincode\nCustomer,9876543210,,META,,,\n'
        with override_settings(INTAKE_ENABLED=False), patch('uploads.views.upload_bytes'), self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/uploads/', {'file': SimpleUploadedFile('test.csv', content, content_type='text/csv')})
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['processing_mode'], 'database')
        batch = UploadBatch.objects.get()
        self.assertEqual(batch.status, 'PARSING')
        self.assertFalse(batch.rows.exists())
        with override_settings(INTAKE_ENABLED=False), patch('uploads.tasks.download_bytes', return_value=content), patch('uploads.tasks.delete_paths'):
            self.run_processor()
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'READY')
        self.assertEqual(batch.total_rows, 1)
        self.assertEqual(self.client.post(f'/api/uploads/{batch.pk}/commit/').status_code, 200)
        self.assertEqual(Lead.objects.count(), 1)

    def test_active_processor_is_not_replaced_and_expired_lease_recovers(self):
        old = timezone.now() - timedelta(minutes=1)
        token = uuid.uuid4()
        heartbeat = Heartbeat.objects.create(name='processor', seen_at=old, lease_until=timezone.now() + timedelta(minutes=1), lease_token=token)
        self.assertIn('Another processor', self.run_processor())
        heartbeat.refresh_from_db()
        self.assertEqual(heartbeat.seen_at, old)
        self.assertEqual(heartbeat.lease_token, token)
        heartbeat.lease_until = old
        heartbeat.save()
        self.run_processor()
        heartbeat.refresh_from_db()
        self.assertGreater(heartbeat.seen_at, old)
        self.assertIsNone(heartbeat.lease_token)

    def test_real_deadline_leaves_inflight_receipt_retryable(self):
        receipt = self.receipt()
        with patch('intake.tasks.fetch_lead', side_effect=lambda _: signal.pause()):
            self.assertIn('Time budget reached', self.run_processor(max_seconds=1))
        receipt.refresh_from_db()
        self.assertEqual(receipt.state, 'PROCESSING')
        self.assertEqual(receipt.errors, {})
        Submission.objects.filter(pk=receipt.pk).update(lease_until=timezone.now() - timedelta(seconds=1))
        with patch('intake.meta.graph', side_effect=self.graph), patch('intake.tasks.graph', side_effect=self.graph):
            self.run_processor()
        self.assertEqual(Lead.objects.count(), 1)

    def test_mapping_errors_still_go_to_review(self):
        self.receipt()
        MappingVersion.objects.create(form=self.form, version=1, rules={'required': ['email']})
        # Mapping versions are snapshotted when the receipt is accepted.
        Submission.objects.update(mapping_version=self.form.mappings.get())
        with patch('intake.meta.graph', side_effect=self.graph):
            self.run_processor()
        receipt = Submission.objects.get()
        self.assertEqual(receipt.state, 'NEEDS_REVIEW')
        self.assertIn('email', receipt.errors)
        self.assertFalse(Lead.objects.exists())

    def test_automatic_catchup_incremental_overlap_and_webhook_identity(self):
        from datetime import datetime
        boundary = datetime.fromisoformat('2026-08-29T00:00:00+05:30')
        Connection.objects.filter(pk=self.connection.pk).update(activated_at=boundary)
        IntakeForm.objects.filter(pk=self.form.pk).update(activated_at=boundary)
        self.receipt()  # Existing webhook delivery, before the first automatic scan.
        calls = []
        def graph(connection, path, params):
            if path.endswith('/leads'):
                calls.append(params)
                return self.page('222', '333')
            return self.graph(connection, path, params)
        with patch('intake.meta.graph', side_effect=graph), patch('intake.tasks.graph', side_effect=self.graph):
            out = self.run_processor(automatic_meta=True)
            self.form.refresh_from_db()
            checkpoint = self.form.checkpoint
            self.assertEqual(json.loads(calls[0]['filtering'])[0]['value'], int(boundary.timestamp()) - 1)
            self.assertEqual(Lead.objects.count(), 2)
            self.assertEqual(Submission.objects.count(), 2)
            self.assertIn('scanned=2', out)
            self.run_processor(automatic_meta=True)
            self.assertEqual(len(calls), 1)
            IntakeForm.objects.filter(pk=self.form.pk).update(last_reconciled_at=timezone.now() - timedelta(minutes=31))
            self.run_processor(automatic_meta=True)
            self.assertEqual(json.loads(calls[1]['filtering'])[0]['value'], int((checkpoint - timedelta(minutes=30)).timestamp()) - 1)
            self.assertEqual(Lead.objects.count(), 2)
        self.assertFalse(IntakeAudit.objects.filter(action='meta_fetch_requested').exists())
        self.assertFalse(Lead.objects.exclude(status='FRESH', assigned_so=None, assigned_ps=None).exists())
        for private in ('test-token', 'Test customer', '9876543'):
            self.assertNotIn(private, out)

    def test_automatic_scan_skips_disabled_paused_and_future_forms(self):
        for changes in ({'enabled': False}, {'activated_at': timezone.now() + timedelta(days=1)}):
            IntakeForm.objects.filter(pk=self.form.pk).update(**changes)
            with patch('intake.meta.graph') as graph:
                self.run_processor(automatic_meta=True)
                graph.assert_not_called()
        IntakeForm.objects.filter(pk=self.form.pk).update(enabled=True, activated_at=self.connection.activated_at)
        for changes in ({'enabled': False}, {'enabled': True, 'paused_reason': 'meta_access_required'}):
            Connection.objects.filter(pk=self.connection.pk).update(**changes)
            with patch('intake.meta.graph') as graph:
                self.run_processor(automatic_meta=True)
                graph.assert_not_called()

    def test_automatic_failures_retry_once_per_run_and_expired_cursor_restarts_window(self):
        for failure in (MetaFailure('meta_temporarily_unavailable'), TimeoutError('private-token'), MetaFailure('meta_request_rejected', permanent=True)):
            with self.subTest(code=str(type(failure))):
                IntakeForm.objects.filter(pk=self.form.pk).update(fetch_requested_at=timezone.now(), reconcile_cursor='expired')
                with patch('intake.meta.graph', side_effect=failure) as graph:
                    out = self.run_processor(automatic_meta=True)
                self.assertEqual(graph.call_count, 1)
                self.assertIn('scan_failures=1', out)
                self.assertNotIn('private-token', out)
                self.form.refresh_from_db()
                end = self.form.reconcile_end
                self.assertIsNotNone(self.form.fetch_requested_at)
                with patch('intake.meta.graph', return_value=self.page()) as graph:
                    self.run_processor(automatic_meta=True)
                self.assertEqual(graph.call_count, 1)
                if isinstance(failure, MetaFailure) and failure.permanent:
                    self.assertNotIn('after', graph.call_args.args[2])
                self.form.refresh_from_db()
                self.assertEqual(self.form.checkpoint, end)
                self.assertEqual(self.form.reconcile_error, '')

    def test_automatic_import_preserves_existing_leads_reviews_and_audit(self):
        from leads.models import FollowUp, LeadAudit
        existing = Lead.objects.create(name='Existing owner', phone='9876543222', status='QUALIFIED', assigned_so=self.admin, duplicate_flag=True)
        followup = FollowUp.objects.create(lead=existing, so=self.admin, scheduled_for=timezone.now() + timedelta(days=1))
        audit = LeadAudit.objects.create(lead=existing, event='baseline', after={'kept': True})
        before = Lead.objects.filter(pk=existing.pk).values().get()
        review = self.receipt('555')
        Submission.objects.filter(pk=review.pk).update(state='NEEDS_REVIEW', review_reason='validation', errors={'phone': 'Invalid phone.'})
        def graph(connection, path, params):
            if path.endswith('/leads'):
                return self.page('222', '333', '444', '555')
            value = self.graph(connection, path, params)
            if path == '333':
                value['field_data'][1]['values'] = ['invalid phone']
            return value
        with patch('intake.meta.graph', side_effect=graph), patch('intake.tasks.graph', side_effect=self.graph):
            self.run_processor(automatic_meta=True)
        self.assertEqual(Lead.objects.filter(pk=existing.pk).values().get(), before)
        self.assertTrue(FollowUp.objects.filter(pk=followup.pk, notified_at=None).exists())
        self.assertTrue(LeadAudit.objects.filter(pk=audit.pk, after={'kept': True}).exists())
        self.assertEqual(Submission.objects.get(external_id='222').review_reason, 'existing_lead')
        self.assertEqual(Submission.objects.get(external_id='333').review_reason, 'validation')
        review.refresh_from_db()
        self.assertEqual(review.errors, {'phone': 'Invalid phone.'})
        self.assertEqual(review.attempts, 0)
        self.assertEqual(Lead.objects.count(), 2)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=False)
    def test_reminders_deduplicate_and_paused_meta_does_not_block_uploads(self):
        from feedback.models import FeedbackTask
        from leads.models import FollowUp, LeadAudit
        from notifications.models import Notification
        caller = User.objects.create_user(email='caller@example.com', password='test', role='FEEDBACK', location='Kochi')
        lead = Lead.objects.create(name='Follow up', phone='9876543210', branch='Kochi', assigned_so=self.admin)
        due = timezone.now() - timedelta(minutes=1)
        followup = FollowUp.objects.create(lead=lead, so=self.admin, scheduled_for=due)
        audit = LeadAudit.objects.create(lead=lead, event='baseline')
        task = FeedbackTask.objects.create(lead=lead, source_audit=audit, kind='TDF', branch='Kochi', assigned_to=caller,
                                           occurred_at=due, original_due_at=due, next_call_at=due)
        Connection.objects.filter(pk=self.connection.pk).update(paused_reason='meta_access_required')
        batch = UploadBatch.objects.create(filename='test.csv', storage_path='test.csv', uploaded_by=self.admin)
        content = b'name,phone,email,source,enquiry date,city,pincode\nCustomer,9876543210,,META,,,\n'
        with patch('uploads.tasks.download_bytes', return_value=content), patch('uploads.tasks.delete_paths'), patch('intake.meta.graph') as graph:
            self.run_processor(automatic_meta=True, reminders=True)
            count = Notification.objects.count()
            self.assertGreater(count, 0)
            self.run_processor(automatic_meta=True, reminders=True)
            self.assertEqual(Notification.objects.count(), count)
            graph.assert_not_called()
        self.assertTrue(Notification.objects.filter(feedback_task=task, kind='FEEDBACK_DUE').exists())
        followup.refresh_from_db()
        self.assertIsNotNone(followup.notified_at)
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'READY')
        self.assertEqual(batch.rows.get().resolution, 'PENDING')  # Duplicate still requires review.

    def test_success_health_does_not_advance_on_crash_and_scan_warning_is_separate(self):
        self.run_processor()
        success = Heartbeat.objects.get(name='processor_success').seen_at
        with patch('notifications.tasks.create_due_follow_up_notifications.run', side_effect=RuntimeError('customer secret')):
            with self.assertRaisesMessage(CommandError, 'processor_failed') as failure:
                self.run_processor(reminders=True)
        self.assertNotIn('customer secret', str(failure.exception))
        self.assertEqual(Heartbeat.objects.get(name='processor_success').seen_at, success)
        health = self.client.get('/api/intake/connections/health/').data
        self.assertFalse(health['processor_delayed'])
        self.assertTrue(health['connections'][0]['forms'][0]['scan_delayed'])
        self.assertGreater(health['last_processor_attempt_at'], success)
        Heartbeat.objects.filter(name='processor_success').update(seen_at=timezone.now() - timedelta(minutes=16))
        IntakeForm.objects.filter(pk=self.form.pk).update(last_reconciled_at=timezone.now())
        health = self.client.get('/api/intake/connections/health/').data
        self.assertTrue(health['processor_delayed'])
        self.assertFalse(health['connections'][0]['forms'][0]['scan_delayed'])

    def test_retention_runs_once_per_hour(self):
        with patch('intake.processor.purge_expired_answers.run') as purge:
            self.run_processor()
            self.run_processor()
            self.assertEqual(purge.call_count, 1)
            Heartbeat.objects.filter(name='retention').update(seen_at=timezone.now() - timedelta(hours=2))
            self.run_processor()
            self.assertEqual(purge.call_count, 2)
