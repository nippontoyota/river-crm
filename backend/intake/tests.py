import hashlib
import hmac
import io
import json
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import Lead, LeadAudit, SystemConfig
from uploads.models import UploadBatch
from uploads.tasks import parse_upload_batch, read_rows
from .mapping import map_entries, normalize_phone, sanitize_entries, validate_rules
from .meta import MetaFailure, graph
from .models import Connection, IntakeForm, MappingVersion, Submission
from .services import accept
from .tasks import process_submission, purge_expired_answers, reconcile_form, sweep_receipts


def entries(**values):
    return [{'id': key, 'label': key, 'value': value} for key, value in values.items()]


@override_settings(INTAKE_ENABLED=True, CELERY_TASK_ALWAYS_EAGER=False, INTAKE_SECRETS={'site': {'active': 'active-secret', 'retiring': 'old-secret'}, 'meta': {'access_token': 'meta-token'}}, META_APP_SECRET='app-secret', META_VERIFY_TOKEN='verify', META_GRAPH_VERSION='v99.0', PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class IntakeTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='intake-admin@example.com', password='password', role='ADMIN')
        SystemConfig.objects.update_or_create(pk=1, defaults={'lists': {'sources': ['WEBSITE', 'META'], 'models': ['River Indie'], 'activities': ['Campaign'], 'subActivities': {'Campaign': ['Launch']}, 'branches': ['Kochi']}})
        self.connection = Connection.objects.create(name='Website', origin='WEBSITE', source='WEBSITE', secret_ref='site', enabled=True, activated_at=timezone.now() - timedelta(days=2))
        self.form = IntakeForm.objects.create(connection=self.connection, name='Enquiry', external_id='enquiry', enabled=True, activated_at=self.connection.activated_at)
        self.client = APIClient()
        self.publish = patch('intake.services.publish', return_value=False)
        self.publish.start()
        self.addCleanup(self.publish.stop)

    def post(self, payload=None, token='active-secret'):
        return self.client.post('/api/integrations/website/leads/', payload or {'submission_id': 'one', 'form_id': 'enquiry', 'fields': {'Full Name': 'Customer', 'Ph No:': '+91 98765-43210'}}, format='json', HTTP_AUTHORIZATION='Bearer ' + token)

    def receipt(self, external='one', values=None):
        with transaction.atomic():
            receipt, _ = accept(self.form, external, entries=entries(**(values or {'name': 'Customer', 'phone': '9876543210'})), submitted_at=timezone.now())
        return receipt

    def process(self, receipt):
        process_submission.run(str(receipt.pk))
        receipt.refresh_from_db()
        return receipt

    def admin_action(self, receipt, action, **kwargs):
        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f'/api/intake/submissions/{receipt.pk}/resolve/', {'action': action, **kwargs}, format='json')

    def meta_form(self):
        connection = Connection.objects.create(name='Meta', origin='META', source='META', secret_ref='meta', enabled=True, activated_at=self.connection.activated_at)
        return IntakeForm.objects.create(connection=connection, name='Selected form', external_id='123', page_id='456', enabled=True, activated_at=connection.activated_at)

    def test_phone_aliases_and_formatting(self):
        for alias in ['Phone', 'Ph No:', 'Phone Number', 'phone_number', 'Mobile', 'Mobile No', 'Contact Number', 'Phone Nnumber']:
            for phone in ['9876543210', '+91 98765-43210', '09876543210', '(98765) 43210', '919876543210']:
                with self.subTest(alias=alias, phone=phone):
                    result = map_entries(entries(Name='Customer', **{alias: phone}))
                    self.assertEqual(result['values']['phone'], '9876543210')
                    self.assertEqual(result['errors'], {})
        for phone in ['1239876543210', '449876543210', 'abcd9876543210', '987654321', '९८७६५४३२१०', '98765/43210']:
            self.assertEqual(normalize_phone(phone), '')

    def test_normalization_compatibility_and_unknown_optional(self):
        result = map_entries(entries(**{' CUSTOMER_name!! ': 'Customer', 'PHONE_NUMBER': '9876543210', 'Location': 'Kochi', 'Date': 'bad', 'Contact': 'bad', 'Question': 'Optional'}))
        self.assertEqual(result['errors'], {})
        self.assertEqual(result['values']['city'], '')
        self.assertIsNone(result['values']['enquiry_date'])
        excel = map_entries(entries(name='Customer', phone='9876543210', source='website', location='Kochi', date='bad'), excel=True)
        self.assertIn('enquiry_date', excel['errors'])
        self.assertEqual(excel['values']['city'], 'Kochi')

    def test_saved_mapping_split_names_ignore_aliases_and_defaults(self):
        rules = {'fields': {'Given': 'first_name', 'Family': 'last_name', 'Contact': 'phone', 'Town answer': 'city', 'Private': 'ignore'}, 'defaults': {'activity': 'Campaign', 'sub_activity': 'Launch'}, 'value_aliases': {'model_interest': {'Ad label': 'River Indie'}}}
        values = entries(Given='First', Family='Last', Contact='9876543210', **{'Town answer': 'Kochi', 'Private': 'private-value', 'Model': 'Ad label'})
        result = map_entries(values, rules)
        self.assertEqual(result['values']['name'], 'First Last')
        self.assertEqual(result['values']['model_interest'], 'River Indie')
        self.assertEqual(result['errors'], {})
        retained, ignored = sanitize_entries(values, rules)
        self.assertNotIn('private-value', json.dumps(retained))
        self.assertIn('Private', ignored)
        self.assertEqual(map_entries(values + entries(Name='Full Customer'), rules)['values']['name'], 'Full Customer')

    def test_conflicts_equivalence_blank_primary_and_required(self):
        data = entries(Name='Customer', Mobile='9876543210', Phone='+91 9876543210')
        self.assertEqual(map_entries(data)['errors'], {})
        data[-1]['value'] = '9876543211'
        self.assertIn('phone', map_entries(data)['errors'])
        rules = {'primary': {'phone': 'Mobile'}}
        self.assertEqual(map_entries(data, rules)['values']['phone'], '9876543210')
        data[1]['value'] = ''
        self.assertIn('phone', map_entries(data, rules)['errors'])
        self.assertIn('city', map_entries(entries(name='Customer', phone='9876543210'), {'required': ['city']})['errors'])

    def test_optional_dates_lengths_choices_and_empty_lists(self):
        base = {'name': 'Customer', 'phone': '9876543210'}
        for key, value in {'email': 'bad', 'model_interest': 'Unknown', 'city': 'x' * 101, 'name': 'x' * 161, 'rto': 'TN-01', 'profession': 'x' * 101, 'enquiry_date': '31/02/2026', 'activity': 'Wrong', 'sub_activity': 'Wrong', 'branch': 'Wrong'}.items():
            with self.subTest(key=key):
                self.assertIn(key, map_entries(entries(**{**base, key: value}))['errors'])
        self.assertIn('enquiry_date', map_entries(entries(**base, enquiry_date=(timezone.localdate() + timedelta(days=1)).isoformat()))['errors'])
        for value in ['2025-01-02', '02/01/2025', '02-01-2025']:
            self.assertEqual(map_entries(entries(**base, enquiry_date=value))['values']['enquiry_date'], '2025-01-02')
        SystemConfig.objects.filter(pk=1).update(lists={})
        self.assertIn('Configuration required', map_entries(entries(**base, model_interest='River Indie'))['errors']['model_interest'])
        self.assertEqual(map_entries(entries(**base, email=None, city=None))['errors'], {})

    def test_forbidden_answers_removed_and_rules_cannot_set_ownership(self):
        receipt = self.receipt(values={'name': 'Customer', 'phone': '9876543210', 'assigned_so': 'sensitive-owner', 'status': 'WON', 'generated_by': 'sensitive-generator', 'metadata': 'sensitive-metadata', 'source': 'injected-source'})
        self.assertNotIn('sensitive', json.dumps(receipt.answers))
        self.assertNotIn('injected-source', json.dumps(receipt.answers))
        self.process(receipt)
        lead = receipt.lead
        self.assertEqual((lead.status, lead.source, lead.assigned_so_id, lead.assigned_ps_id, lead.generated_by_id), ('FRESH', 'WEBSITE', None, None, None))
        self.assertFalse(lead.needs_cre_reassignment or lead.needs_so_reassignment or lead.flagged_to_manager)
        for rules in [{'fields': {'X': 'assigned_so'}}, {'defaults': {'status': 'WON'}}, {'value_aliases': {'phone': []}}]:
            with self.assertRaises(ValidationError):
                validate_rules(rules)

    def test_website_replay_conflict_and_ignored_fingerprint(self):
        MappingVersion.objects.create(form=self.form, version=1, created_by=self.admin, rules={'fields': {'Private': 'ignore'}})
        payload = {'submission_id': 'same', 'form_id': 'enquiry', 'fields': {'Name': 'Customer', 'Mobile': '9876543210', 'Private': 'secret-answer'}}
        response = self.post(payload)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data, self.post(payload, token='old-secret').data)
        self.assertNotIn('secret-answer', json.dumps(Submission.objects.get().answers))
        payload['fields']['Private'] = 'changed'
        self.assertEqual(self.post(payload).status_code, 409)
        self.assertEqual(Submission.objects.count(), 1)

    def test_website_auth_malformed_inactive_and_limits(self):
        self.assertEqual(self.post(token='wrong').status_code, 401)
        self.assertEqual(self.post({'submission_id': 'one', 'form_id': 'unknown', 'fields': {}}).status_code, 403)
        for body in [{'submission_id': 'one', 'form_id': 'enquiry', 'fields': {}, 'owner': 1}, {'submission_id': 'one', 'form_id': 'enquiry', 'fields': {'Object': {'private': 1}}}, {'submission_id': 'one', 'form_id': 'enquiry', 'fields': {}, 'attribution': {'url': 'https://example.com'}}, {'submission_id': 'one', 'form_id': 'enquiry', 'fields': {str(i): '' for i in range(101)}}]:
            self.assertEqual(self.post(body).status_code, 400)
        self.assertEqual(self.post({'submission_id': 'one', 'form_id': 'enquiry', 'fields': {'Huge': 'x' * 65536}}).status_code, 413)
        self.connection.enabled = False; self.connection.save()
        self.assertEqual(self.post().status_code, 403)
        self.assertFalse(Submission.objects.exists())

    def test_duplicate_json_keys_preserved(self):
        raw = '{"submission_id":"one","form_id":"enquiry","fields":{"Name":"Customer","Phone":"9876543210","Phone":"9876543211"}}'
        response = self.client.post('/api/integrations/website/leads/', raw, content_type='application/json', HTTP_AUTHORIZATION='Bearer active-secret')
        self.assertEqual(response.status_code, 202)
        receipt = self.process(Submission.objects.get())
        self.assertEqual(receipt.state, 'NEEDS_REVIEW')
        self.assertEqual(len(receipt.answers), 3)

    @override_settings(INTAKE_RATE_PER_MINUTE=2)
    def test_rate_limit_is_database_backed(self):
        self.assertEqual(self.post().status_code, 202)
        self.assertEqual(self.post().status_code, 202)
        self.assertEqual(self.post().status_code, 429)
        self.connection.refresh_from_db()
        self.assertEqual(self.connection.rate_count, 2)

    def test_customer_errors_are_durable_despite_broker_failure(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.post({'submission_id': 'invalid', 'form_id': 'enquiry', 'fields': {'Name': 'Customer', 'Phone': 'bad'}})
        self.assertEqual(response.status_code, 202)
        receipt = self.process(Submission.objects.get())
        self.assertEqual(receipt.state, 'NEEDS_REVIEW')
        self.assertEqual(self.admin_action(receipt, 'correct', corrections={'phone': '9876543210'}).status_code, 200)
        receipt.refresh_from_db()
        self.assertEqual(receipt.state, 'IMPORTED')
        self.assertEqual(receipt.answers, [])

    def test_database_failure_is_retryable(self):
        with patch('intake.views.accept', side_effect=DatabaseError('private database detail')):
            response = self.post()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private', str(response.data))
        self.assertFalse(Submission.objects.exists())

    def test_link_and_separate_preserve_existing_lead(self):
        existing = Lead.objects.create(name='Existing', phone='9876543210', status='QUALIFIED', assigned_so=self.admin)
        receipt = self.process(self.receipt())
        self.assertEqual(receipt.review_reason, 'existing_lead')
        self.assertEqual(self.admin_action(receipt, 'link', lead_id=existing.pk).status_code, 200)
        existing.refresh_from_db()
        self.assertEqual((existing.name, existing.status, existing.assigned_so_id), ('Existing', 'QUALIFIED', self.admin.pk))
        separate = self.process(self.receipt('two'))
        self.admin_action(separate, 'create_separately'); self.admin_action(separate, 'create_separately')
        separate.refresh_from_db()
        self.assertTrue(separate.lead.duplicate_flag)
        self.assertIsNone(separate.lead.assigned_so_id)
        self.assertEqual(Lead.objects.count(), 2)
        self.assertTrue(LeadAudit.objects.filter(lead=existing, event='intake_linked').exists())

    def test_pending_receipts_wait_for_earliest(self):
        first = self.receipt('first', {'name': 'Customer', 'phone': '9876543210', 'email': 'bad'})
        second = self.process(self.receipt('second'))
        self.assertEqual(second.blocked_by_id, first.pk)
        self.admin_action(first, 'dismiss')
        second.refresh_from_db()
        self.assertEqual(second.state, 'RECEIVED')
        self.assertEqual(self.process(second).state, 'IMPORTED')

    def test_mapping_snapshot_and_explicit_reprocess(self):
        first = MappingVersion.objects.create(form=self.form, version=1, created_by=self.admin, rules={'fields': {'Contact': 'phone'}})
        receipt = self.receipt(values={'name': 'Customer', 'Contact': 'bad', 'Mobile': '9876543210'})
        second = MappingVersion.objects.create(form=self.form, version=2, created_by=self.admin, rules={'fields': {'Contact': 'ignore'}})
        self.assertEqual(self.process(receipt).state, 'NEEDS_REVIEW')
        self.assertEqual(receipt.mapping_version_id, first.pk)
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/intake/mappings/{second.pk}/reprocess/', {'receipt_ids': [str(receipt.pk)]}, format='json')
        self.assertEqual(response.data['queued'], 1)
        self.assertEqual(self.process(receipt).state, 'IMPORTED')
        with self.assertRaises(DjangoValidationError):
            second.save()

    def test_non_admin_denied_and_credentials_not_serialized(self):
        user = User.objects.create_user(email='cre@example.com', password='password', role='CRE')
        self.client.force_authenticate(user)
        receipt = self.receipt()
        for path, method in [('connections/', 'get'), ('connections/health/', 'get'), ('forms/', 'get'), ('mappings/', 'get'), ('mappings/preview/', 'post'), ('submissions/', 'get'), (f'submissions/{receipt.pk}/', 'get'), (f'submissions/{receipt.pk}/resolve/', 'post')]:
            self.assertEqual(getattr(self.client, method)('/api/intake/' + path).status_code, 403)
        self.client.force_authenticate(self.admin)
        response = self.client.get('/api/intake/connections/health/')
        for secret in ['active-secret', 'old-secret', 'secret_ref', 'meta-token']:
            self.assertNotIn(secret, json.dumps(response.data, default=str))

    def test_expired_answers_never_refetch_and_allow_corrected_input(self):
        receipt = self.receipt(values={'name': 'Customer', 'phone': '9876543210', 'email': 'bad'})
        Submission.objects.filter(pk=receipt.pk).update(received_at=timezone.now() - timedelta(days=31))
        purge_expired_answers.run(); receipt.refresh_from_db()
        self.assertTrue(receipt.answers_expired)
        self.assertEqual(receipt.answers, []); self.assertEqual(receipt.mapped_values, {})
        self.assertEqual(self.admin_action(receipt, 'retry').status_code, 400)
        with patch('intake.tasks.fetch_lead') as fetch:
            process_submission.run(str(receipt.pk)); fetch.assert_not_called()
        self.assertEqual(self.admin_action(receipt, 'correct', corrections={'name': 'Corrected', 'phone': '9876543210'}).status_code, 200)
        receipt.refresh_from_db(); self.assertEqual(receipt.state, 'IMPORTED')

    def test_expired_lease_recovery_and_redacted_diagnostics(self):
        receipt = self.receipt()
        Submission.objects.filter(pk=receipt.pk).update(state='PROCESSING', lease_until=timezone.now() - timedelta(minutes=1), lease_token=uuid.uuid4())
        with patch('intake.tasks.publish') as publish:
            sweep_receipts.run(); publish.assert_any_call(process_submission, str(receipt.pk))
        with patch('intake.tasks.process_locked', side_effect=RuntimeError('sensitive-customer-and-secret')):
            self.process(receipt)
        self.assertNotIn('sensitive', str(receipt.errors)); self.assertEqual(receipt.state, 'RECEIVED')
        self.assertGreater(receipt.next_attempt_at, timezone.now())
        Submission.objects.filter(pk=receipt.pk).update(attempts=10, next_attempt_at=timezone.now())
        self.assertEqual(self.process(receipt).state, 'FAILED')

    def test_meta_signature_mixed_batches_and_unknown_forms(self):
        self.meta_form()
        self.assertEqual(self.client.get('/api/integrations/meta/webhook/', {'hub.mode': 'subscribe', 'hub.verify_token': 'verify', 'hub.challenge': 'challenge'}).content, b'challenge')
        event = {'object': 'page', 'entry': [{'id': '456', 'changes': [{'field': 'feed', 'value': {'private': 'never-retained'}}, {'field': 'leadgen', 'value': {'form_id': '999', 'leadgen_id': '111'}}, {'field': 'leadgen', 'value': {'form_id': '123', 'leadgen_id': '222'}}, {'field': 'leadgen', 'value': {'form_id': '123', 'leadgen_id': '333'}}]}]}
        raw = json.dumps(event).encode(); path = '/api/integrations/meta/webhook/'
        self.assertEqual(self.client.post(path, raw, content_type='application/json').status_code, 403)
        signature = 'sha256=' + hmac.new(b'app-secret', raw, hashlib.sha256).hexdigest()
        for _ in range(2):
            self.assertEqual(self.client.post(path, raw, content_type='application/json', HTTP_X_HUB_SIGNATURE_256=signature).status_code, 200)
        self.assertEqual(Submission.objects.count(), 2)
        self.assertEqual(list(Submission.objects.values_list('answers', flat=True)), [[], []])

    def test_meta_fetch_activation_and_permission_pause(self):
        form = self.meta_form()
        with transaction.atomic():
            receipt, _ = accept(form, '222')
        payload = {'id': '222', 'form_id': '123', 'created_time': timezone.now().isoformat(), 'field_data': [{'name': 'full_name', 'values': ['Customer']}, {'name': 'phone_number', 'values': ['9876543210']}]}
        with patch('intake.meta.graph', side_effect=[{'page': {'id': '456'}}, payload]):
            self.assertEqual(self.process(receipt).state, 'IMPORTED')
        with transaction.atomic():
            old, _ = accept(form, '333')
        payload.update(id='333', created_time=(form.activated_at - timedelta(seconds=1)).isoformat())
        with patch('intake.meta.graph', side_effect=[{'page': {'id': '456'}}, payload]):
            self.assertEqual(self.process(old).state, 'DISMISSED')
        with transaction.atomic():
            denied, _ = accept(form, '444')
        with patch('intake.meta.graph', side_effect=MetaFailure('meta_access_required', pause=True)):
            self.process(denied)
        form.connection.refresh_from_db(); self.assertEqual(form.connection.paused_reason, 'meta_access_required')

    def test_meta_pagination_checkpoint_and_failed_recovery(self):
        form = self.meta_form(); submitted = timezone.now() - timedelta(minutes=1)
        pages = [{'data': [{'id': '222', 'created_time': submitted.isoformat()}], 'paging': {'next': 'https://untrusted.example/token', 'cursors': {'after': 'next'}}}, {'data': [{'id': '333', 'created_time': submitted.isoformat()}]}]
        with patch('intake.meta.graph', side_effect=pages) as call:
            reconcile_form.run(form.pk)
        self.assertEqual(call.call_args.args[2]['after'], 'next')
        form.refresh_from_db(); self.assertIsNotNone(form.checkpoint)
        checkpoint = form.checkpoint; self.assertEqual(Submission.objects.count(), 2)
        with patch('intake.meta.graph', side_effect=MetaFailure('meta_temporarily_unavailable')):
            reconcile_form.run(form.pk)
        form.refresh_from_db(); self.assertEqual(form.checkpoint, checkpoint)
        self.assertEqual(form.reconcile_error, 'meta_temporarily_unavailable')
        with patch('intake.meta.graph', return_value={'data': []}):
            reconcile_form.run(form.pk)
        form.refresh_from_db(); self.assertEqual(form.reconcile_error, '')

    def test_meta_transport_throttle_and_access_errors_redacted(self):
        from urllib.error import HTTPError
        form = self.meta_form()
        for http_status, code, pause in [(429, 4, False), (400, 190, True), (403, 200, True)]:
            error = HTTPError('https://graph.facebook.com/private', http_status, 'secret', {}, io.BytesIO(json.dumps({'error': {'code': code, 'message': 'private value'}}).encode()))
            with patch('intake.meta.build_opener') as opener:
                opener.return_value.open.side_effect = error
                with self.assertRaises(MetaFailure) as raised:
                    graph(form.connection, '123', {})
            self.assertEqual(raised.exception.pause, pause); self.assertNotIn('private', str(raised.exception))

    def test_excel_duplicate_headers_missing_required_dates_and_commit_revalidation(self):
        content = b'Name,Phone,Phone,source,date\nCustomer,9876543210,9876543211,website,bad\nOnly name,,,website,\n,,,,\n'
        batch = UploadBatch.objects.create(filename='test.csv', storage_path='imports/test.csv', uploaded_by=self.admin)
        with patch('uploads.tasks.download_bytes', return_value=content):
            parse_upload_batch.run(batch.pk)
        self.assertEqual(batch.rows.count(), 2); self.assertEqual(len(batch.rows.first().answers), 5)
        self.assertIn('phone', batch.rows.first().validation_errors); self.assertIn('enquiry_date', batch.rows.first().validation_errors)
        from openpyxl import Workbook
        workbook = Workbook(); workbook.active.append(['Name', 'Phone', 'source', 'date'])
        workbook.active.append(['Customer', '9876543210', 'website', timezone.localdate()])
        output = io.BytesIO(); workbook.save(output)
        self.assertEqual(map_entries(next(read_rows('test.xlsx', output.getvalue())), excel=True)['errors'], {})
        self.client.force_authenticate(self.admin); row = batch.rows.first()
        response = self.client.post(f'/api/uploads/{batch.pk}/correct-row/', {'row_id': row.pk, 'corrections': {'phone': '9876543210', 'enquiry_date': None}}, format='json')
        self.assertEqual(response.status_code, 200)
        Lead.objects.create(name='Created meanwhile', phone='9876543210')
        self.assertEqual(self.client.post(f'/api/uploads/{batch.pk}/commit/').data['created'], 0)
        self.assertEqual(self.client.post(f'/api/uploads/{batch.pk}/commit/').data['created'], 0)
        self.assertEqual(self.client.post(f'/api/uploads/{batch.pk}/reparse/', {}, format='json').status_code, 400)

    def test_excel_retention_after_file_removed_and_manual_pending_guard(self):
        batch = UploadBatch.objects.create(filename='test.csv', storage_path='imports/test.csv', uploaded_by=self.admin)
        with patch('uploads.tasks.download_bytes', return_value=b'Name,Phone,source\nCustomer,bad,website\n'):
            parse_upload_batch.run(batch.pk)
        UploadBatch.objects.filter(pk=batch.pk).update(created_at=timezone.now() - timedelta(days=31), original_deleted_at=timezone.now())
        purge_expired_answers.run(); self.assertTrue(batch.rows.get().answers_expired)
        receipt = self.receipt(); self.client.force_authenticate(self.admin)
        response = self.client.post('/api/leads/', {'name': 'Manual', 'phone': '9876543210', 'source': 'WEBSITE'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.process(receipt).state, 'IMPORTED')

    def test_form_create_without_meta_page_and_disabled_processing(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post('/api/intake/forms/', {'connection': self.connection.pk, 'name': 'Website form', 'external_id': 'new-form'}, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        receipt = self.receipt()
        self.connection.enabled = False; self.connection.save()
        response = self.admin_action(receipt, 'correct', corrections={'name': 'Corrected'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Lead.objects.exists())
        self.assertEqual(self.admin_action(receipt, 'create_separately').status_code, 400)

    def test_publication_exception_is_swallowed(self):
        from intake.services import publish
        with patch('intake.tasks.process_submission.apply_async', side_effect=RuntimeError('private broker detail')):
            self.assertFalse(publish(process_submission, str(uuid.uuid4())))

    def test_meta_form_mismatch_and_expired_meta_never_refetch(self):
        form = self.meta_form()
        with transaction.atomic():
            receipt, _ = accept(form, '222')
        with patch('intake.meta.graph', return_value={'page': {'id': '999'}}):
            self.process(receipt)
        form.connection.refresh_from_db()
        self.assertEqual(form.connection.paused_reason, 'meta_form_ownership_mismatch')
        Submission.objects.filter(pk=receipt.pk).update(received_at=timezone.now() - timedelta(days=31))
        purge_expired_answers.run()
        with patch('intake.tasks.fetch_lead') as fetch:
            process_submission.run(str(receipt.pk)); fetch.assert_not_called()
