"""Bulk import regression coverage, using real CSV/XLSX files and local storage."""
import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import caches
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from ceo.models import Milestone, OperationEvent
from intake.models import Connection, IntakeForm, Submission
from leads.models import Lead, LeadAudit, SystemConfig
from leads.rtos import KERALA_RTO_CHOICES, normalize_rto
from .models import UploadBatch
from .tasks import HEADINGS, COLUMNS


class RtoNormalizationTests(SimpleTestCase):
    def test_all_configured_names_codes_and_display_labels(self):
        for code, name in KERALA_RTO_CHOICES:
            for value in [code, code.lower().replace('-', ''), name, name.upper(), f'{code} - {name}', f'{name} ({code})']:
                with self.subTest(value=value):
                    self.assertEqual(normalize_rto(value), code)

    def test_common_formatting_and_unambiguous_spelling_variations(self):
        cases = {
            ' kl05 ': 'KL-05', 'KL 5': 'KL-05', 'K.L.05': 'KL-05', 'KL-005': 'KL-05',
            '05': 'KL-05', 'Kottayam RTO': 'KL-05', 'RTO: Kottayam': 'KL-05',
            'Regional Transport Office - Kottayam': 'KL-05', 'Kottaym': 'KL-05',
            'Ernakulamm': 'KL-07', 'Kozhikode': 'KL-11', 'Thiruvananthapuram': 'KL-01',
            'Kanjirapally': 'KL-34', 'North Parur': 'KL-42', 'Thalasserri': 'KL-58',
            'Sub Regional Transport Office, Aluva': 'KL-41',
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_rto(value), expected)

    def test_conflicting_ambiguous_and_unknown_values_need_review(self):
        for value in ['KL-99', 'TN-05', 'KL05 Kollam', 'KL-99 Kottayam', 'KL-05 / KL-07', 'Kott', 'Paravur', 'unknown', 'RTO', 'KL-505', 'Kottayam / Kollam']:
            with self.subTest(value=value):
                self.assertIsNone(normalize_rto(value))
        self.assertEqual(normalize_rto(''), '')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'], SUPABASE_URL='', SUPABASE_SECRET_KEY='')
class BulkImportTests(TestCase):
    def setUp(self):
        caches['default'].clear()
        self.addCleanup(caches['default'].clear)
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        storage = self.settings(BASE_DIR=Path(directory.name))
        storage.enable()
        self.addCleanup(storage.disable)
        self.admin = User.objects.create_user(email='bulk-admin@example.com', role='ADMIN')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        SystemConfig.objects.update_or_create(pk=1, defaults={'lists': {'sources': ['WEBSITE', 'META'], 'models': ['River Indie'], 'branches': ['Kochi']}})
        publisher = patch('uploads.views.publish', side_effect=lambda task, *args: task.run(*args))
        publisher.start()
        self.addCleanup(publisher.stop)

    def customer(self, **values):
        return {'name': 'Customer', 'phone': '9876543210', 'source': 'website', **values}

    def upload(self, rows, headers=HEADINGS, extension='csv', expected='READY'):
        values = [[row.get(field, '') for field in COLUMNS] if isinstance(row, dict) else row for row in rows]
        if extension == 'xlsx':
            workbook = Workbook()
            workbook.active.append(list(headers))
            for row in values:
                workbook.active.append(list(row))
            output = io.BytesIO()
            workbook.save(output)
            content = output.getvalue()
        else:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(values)
            content = output.getvalue().encode('utf-8-sig')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/uploads/', {'file': SimpleUploadedFile(f'leads.{extension}', content)}, format='multipart')
        self.assertEqual(response.status_code, 202, response.data)
        batch = UploadBatch.objects.get(pk=response.data['id'])
        self.assertEqual(batch.status, expected, batch.error_message)
        return batch

    def commit(self, batch):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f'/api/uploads/{batch.pk}/commit/', {}, format='json')

    def choose(self, row, decision):
        response = self.client.post(f'/api/uploads/{row.batch_id}/resolve-duplicates/', {'rows': [{'id': row.pk, 'resolution': decision}]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        row.refresh_from_db()

    def pending(self, phone):
        connection = Connection.objects.create(name='Website', origin='WEBSITE', source='WEBSITE', secret_ref='test')
        form = IntakeForm.objects.create(connection=connection, name='Enquiry', external_id=phone)
        return Submission.objects.create(connection=connection, form=form, identity=phone, external_id=phone, source='WEBSITE', normalized_phone=phone, state='NEEDS_REVIEW')

    def test_sample_csv_and_xlsx_import_customer_fields(self):
        self.assertEqual(HEADINGS, ('name', 'phone', 'email', 'source', 'enquiry date', 'city', 'pincode'))
        SystemConfig.objects.filter(pk=1).update(lists={'sources': ['WEBSITE', 'META']})
        for index, extension in enumerate(['csv', 'xlsx']):
            with self.subTest(extension=extension):
                enquiry_date = timezone.localdate()
                batch = self.upload([self.customer(phone=f'987654321{index}', email='rider@example.com', enquiry_date=enquiry_date.strftime('%d/%m/%Y') if extension == 'csv' else enquiry_date)], extension=extension)
                row = batch.rows.get()
                self.assertEqual(row.validation_errors, {})
                self.assertIsNotNone(batch.original_deleted_at)
                self.assertEqual(row.answers, [])
                self.assertEqual(self.commit(batch).data, {'created': 1, 'overwritten': 0, 'skipped': 0})
                lead = Lead.objects.get(phone=row.normalized_phone)
                self.assertEqual((lead.status, lead.assigned_so_id, lead.assigned_ps_id), ('FRESH', None, None))
                self.assertEqual(lead.enquiry_date, timezone.localdate())
                self.assertEqual((lead.name, lead.email, lead.source), ('Customer', 'rider@example.com', 'WEBSITE'))
                self.assertEqual((lead.campaign, lead.model_interest, lead.city, lead.rto), ('', '', '', ''))
                self.assertTrue(LeadAudit.objects.filter(lead=lead, event='imported').exists())
                self.assertTrue(Milestone.objects.filter(lead=lead, kind='E', rto='').exists())
                self.assertTrue(OperationEvent.objects.filter(lead=lead, snapshot__rto='').exists())
                self.assertTrue(self.commit(batch).data['already_committed'])

    def test_both_bulk_roles_save_city_and_pincode_in_csv_and_xlsx(self):
        ce = User.objects.create_user(email='location-ce@example.com', role='CRE')
        ceo = User.objects.create_user(email='location-ceo@example.com', role='CEO')
        uploader = User.objects.create_user(email='location-uploader@example.com', role='META_UPLOADER')
        for index, user in enumerate([self.admin, uploader]):
            for offset, extension in enumerate(['csv', 'xlsx']):
                with self.subTest(role=user.role, extension=extension):
                    self.client.force_authenticate(user)
                    batch = self.upload([self.customer(phone=f'98765432{index}{offset}', city='  Kochi / കൊച്ചി  ', pincode=682001 if extension == 'xlsx' else ' 682001 ')], extension=extension)
                    row = batch.rows.get()
                    self.assertEqual((row.data['city'], row.data['pincode']), ('Kochi / കൊച്ചി', '682001'))
                    self.assertEqual(self.commit(batch).data['created'], 1)
                    lead = Lead.objects.get(phone=row.normalized_phone)
                    self.assertEqual((lead.city, lead.pincode), ('Kochi / കൊച്ചി', '682001'))
                    self.client.force_authenticate(self.admin)
                    pool = self.client.get(f'/api/leads/?unassigned=true&q={lead.phone}').data['results'][0]
                    self.assertEqual((pool['city'], pool['pincode']), (lead.city, lead.pincode))
                    self.client.post(f'/api/leads/{lead.pk}/assign/', {'sales_officer_id': ce.pk}, format='json')
                    for reader, path in [(ce, f'/api/leads/{lead.pk}/'), (ceo, f'/api/ceo/leads/{lead.pk}/')]:
                        self.client.force_authenticate(reader)
                        detail = self.client.get(path)
                        self.assertEqual(detail.status_code, 200)
                        self.assertEqual((detail.data['city'], detail.data['pincode']), (lead.city, lead.pincode))

    def test_bulk_location_validation_blocks_all_rows_until_corrected(self):
        for role in ['ADMIN', 'META_UPLOADER']:
            user = User.objects.create_user(email=f'location-validation-{role}@example.com', role=role)
            self.client.force_authenticate(user)
            for extension in ['csv', 'xlsx']:
                for values, field in [({'city': 'x' * 101}, 'city'), *[({'pincode': value}, 'pincode') for value in ['12345', '1234567', '012345', '682 001', 'ABC123', '６８２００１', '-682001', '682001.5']]]:
                    with self.subTest(role=role, extension=extension, values=values):
                        batch = self.upload([self.customer(**values), self.customer(phone='9876543211', city='Kochi', pincode='682001')], extension=extension)
                        self.assertIn(field, batch.rows.get(row_number=2).validation_errors)
                        self.assertEqual(self.commit(batch).status_code, 400)
                        self.assertFalse(Lead.objects.exists())
        blank = self.upload([self.customer(city='', pincode='')])
        self.assertEqual(self.commit(blank).data['created'], 1)
        self.assertEqual(Lead.objects.get().pincode, '')

    def test_duplicate_location_updates_preserve_blank_values_and_revalidate(self):
        lead = Lead.objects.create(name='Existing', phone='9876543210', city='Kochi', pincode='682001', assigned_so=self.admin, status='QUALIFIED')
        self.sign_in_uploader()
        batch = self.upload([self.customer(city='Kottayam', pincode='686001')])
        self.choose(batch.rows.get(), 'APPROVE')
        self.assertEqual(self.commit(batch).data['overwritten'], 1)
        lead.refresh_from_db()
        self.assertEqual((lead.city, lead.pincode, lead.assigned_so_id, lead.status), ('Kottayam', '686001', self.admin.pk, 'QUALIFIED'))
        audit = lead.audit_events.get(event='import_overwrite')
        self.assertEqual((audit.before['pincode'], audit.after['pincode']), ('682001', '686001'))
        blank = self.upload([self.customer(city='', pincode='')])
        self.choose(blank.rows.get(), 'APPROVE')
        self.commit(blank)
        lead.refresh_from_db()
        self.assertEqual((lead.city, lead.pincode), ('Kottayam', '686001'))
        invalid = self.upload([self.customer(phone='9876543211', pincode='682001')])
        row = invalid.rows.get()
        row.data['pincode'] = 'bad'
        row.save(update_fields=['data'])
        self.assertEqual(self.commit(invalid).status_code, 400)
        self.assertEqual(Lead.objects.count(), 1)

    def test_lead_api_validates_pincode_for_manual_updates_too(self):
        lead = Lead.objects.create(name='Existing', phone='9876543210')
        for path in [f'/api/leads/{lead.pk}/', f'/api/leads/{lead.pk}/so-update/']:
            invalid = self.client.patch(path, {'pincode': 'bad'}, format='json')
            self.assertEqual(invalid.status_code, 400, invalid.data)
            self.assertIn('pincode', invalid.data)
            valid = self.client.patch(path, {'pincode': '682001'}, format='json')
            self.assertEqual(valid.status_code, 200, valid.data)
            self.assertEqual(valid.data['pincode'], '682001')

    def test_bad_headings_report_missing_unknown_repeated_and_blank_columns(self):
        cases = [
            (HEADINGS[:4] + HEADINGS[5:], 'Missing headings: enquiry date'),
            (HEADINGS[:5], 'Missing headings: city, pincode'),
            (('Customer Name', *HEADINGS[1:]), 'Unrecognized headings: Customer Name'),
            (('phone', *HEADINGS[1:]), 'Repeated headings: phone'),
            (('', *HEADINGS[1:]), 'Blank headings in columns: 1'),
            ((*HEADINGS, 'assigned_so'), 'Unrecognized headings: assigned_so'),
            ((*HEADINGS, 'campaign', 'model', 'RTO'), 'Unrecognized headings: campaign, model, RTO'),
        ]
        for extension in ['csv', 'xlsx']:
            for headings, message in cases:
                with self.subTest(extension=extension, headings=headings):
                    batch = self.upload([self.customer()], headers=headings, extension=extension, expected='FAILED')
                    self.assertIn(message, batch.error_message)
                    self.assertEqual(batch.rows.count(), 0)
                    self.assertEqual(self.commit(batch).status_code, 400)

    def test_empty_file_and_wrong_cell_count_report_reasons(self):
        batch = self.upload([], expected='FAILED')
        self.assertIn('no leads', batch.error_message)
        batch = self.upload([['Name', '9876543210']], expected='FAILED')
        self.assertIn('Row 2 has 2 cells; expected 7', batch.error_message)

    def test_invalid_rows_block_import_until_fixed_offline(self):
        batch = self.upload([self.customer(phone='123', enquiry_date='invalid'), self.customer(phone='9876543211')])
        self.assertIn('phone', batch.rows.get(row_number=2).validation_errors)
        self.assertIn('enquiry_date', batch.rows.get(row_number=2).validation_errors)
        self.assertEqual(self.commit(batch).status_code, 400)
        self.assertFalse(Lead.objects.exists())
        fixed = self.upload([self.customer(), self.customer(phone='9876543211')])
        self.assertEqual(self.commit(fixed).data['created'], 2)

    def test_crm_duplicate_requires_admin_approval_and_updates_same_lead(self):
        lead = Lead.objects.create(name='Existing', phone='9876543210', rto='KL-08', assigned_so=self.admin, status='QUALIFIED', profession='Engineer', branch='Kochi', email='old@example.com', model_interest='River Indie', campaign='Launch', city='Kochi')
        batch = self.upload([self.customer(name='Updated', phone='+91 98765-43210')])
        row = batch.rows.get()
        self.assertEqual(row.resolution, 'PENDING')
        self.assertEqual(self.commit(batch).status_code, 409)
        self.choose(row, 'APPROVE')
        self.assertEqual(row.resolution, 'OVERWRITE')
        self.assertEqual(self.commit(batch).data, {'created': 0, 'overwritten': 1, 'skipped': 0})
        lead.refresh_from_db()
        self.assertEqual((lead.name, lead.status, lead.assigned_so_id, lead.rto, lead.profession, lead.email, lead.branch), ('Updated', 'QUALIFIED', self.admin.pk, 'KL-08', 'Engineer', 'old@example.com', 'Kochi'))
        self.assertEqual((lead.model_interest, lead.campaign, lead.city), ('River Indie', 'Launch', 'Kochi'))
        self.assertEqual(Lead.objects.count(), 1)

    def test_file_duplicates_choose_exactly_one_row_per_normalized_phone(self):
        batch = self.upload([self.customer(name='First'), self.customer(name='Chosen', phone='09876543210'), self.customer(name='Other', phone='9876543211')])
        rows = list(batch.rows.order_by('row_number'))
        self.assertEqual([r.resolution for r in rows], ['PENDING', 'PENDING', 'IMPORT'])
        review = self.client.get(f'/api/uploads/{batch.pk}/?include_rows=true').data
        self.assertEqual(review['file_duplicates_found'], 2)
        self.assertEqual(review['rows'][0]['file_rows'], [2, 3])
        self.choose(rows[1], 'APPROVE')
        rows[0].refresh_from_db()
        self.assertEqual(rows[0].resolution, 'SKIP')
        self.assertEqual(self.commit(batch).data, {'created': 2, 'overwritten': 0, 'skipped': 1})
        self.assertEqual(Lead.objects.get(phone='9876543210').name, 'Chosen')

    def test_repeated_crm_duplicates_and_rejection_keep_phone_unique(self):
        lead = Lead.objects.create(name='Existing', phone='9876543210')
        batch = self.upload([self.customer(name='First'), self.customer(name='Chosen')])
        self.choose(batch.rows.get(row_number=3), 'APPROVE')
        self.assertEqual(self.commit(batch).data, {'created': 0, 'overwritten': 1, 'skipped': 1})
        lead.refresh_from_db()
        self.assertEqual(lead.name, 'Chosen')
        rejected = self.upload([self.customer(name='Rejected')])
        self.choose(rejected.rows.get(), 'SKIP')
        self.assertEqual(self.commit(rejected).data['skipped'], 1)
        lead.refresh_from_db()
        self.assertEqual(lead.name, 'Chosen')
        self.assertEqual(Lead.objects.count(), 1)

    def test_pending_intake_requires_review(self):
        self.pending('9876543210')
        batch = self.upload([self.customer()])
        self.assertEqual(batch.rows.get().data['_duplicate_type'], 'INTAKE')
        self.assertEqual(self.commit(batch).status_code, 409)
        self.choose(batch.rows.get(), 'APPROVE')
        self.assertEqual(self.commit(batch).data['created'], 1)

    def test_new_match_at_commit_returns_to_review_without_partial_import(self):
        batch = self.upload([self.customer(), self.customer(phone='9876543211')])
        Lead.objects.create(name='Added meanwhile', phone='9876543211')
        self.assertEqual(self.commit(batch).status_code, 409)
        self.assertEqual(Lead.objects.count(), 1)
        row = batch.rows.get(normalized_phone='9876543211')
        self.assertEqual(row.resolution, 'PENDING')
        self.choose(row, 'SKIP')
        self.assertEqual(self.commit(batch).data, {'created': 1, 'overwritten': 0, 'skipped': 1})

    def test_changed_overwrite_target_requires_review(self):
        lead = Lead.objects.create(name='Existing', phone='9876543210')
        batch = self.upload([self.customer()])
        self.choose(batch.rows.get(), 'APPROVE')
        lead.phone = '9876543211'
        lead.save()
        self.assertEqual(self.commit(batch).status_code, 409)
        self.assertEqual(Lead.objects.count(), 1)

    def test_invalid_or_multiple_approvals_are_rejected(self):
        batch = self.upload([self.customer(), self.customer(name='Repeat')])
        ids = list(batch.rows.values_list('pk', flat=True))
        for decisions in [[], [{'id': ids[0], 'resolution': 'IMPORT'}], [{'id': ids[0], 'resolution': 'OVERWRITE'}], [{'id': 999999, 'resolution': 'APPROVE'}], [{'id': pk, 'resolution': 'APPROVE'} for pk in ids]]:
            self.assertEqual(self.client.post(f'/api/uploads/{batch.pk}/resolve-duplicates/', {'rows': decisions}, format='json').status_code, 400)
        self.assertTrue(all(row.resolution == 'PENDING' for row in batch.rows.all()))

    def test_removed_mapping_and_row_edit_endpoints(self):
        batch = self.upload([self.customer()])
        for action in ['reparse', 'correct-row']:
            self.assertEqual(self.client.post(f'/api/uploads/{batch.pk}/{action}/', {}, format='json').status_code, 404)
        response = self.client.post('/api/uploads/', {'file': SimpleUploadedFile('test.csv', b'test'), 'mapping_version': '1'}, format='multipart')
        self.assertEqual(response.status_code, 400)

    def test_non_admin_cannot_upload_review_or_import(self):
        batch = self.upload([self.customer()])
        for role in ['CEO', 'CRE', 'SO', 'SALES_MANAGER', 'RECEPTIONIST', 'SERVICE']:
            self.client.force_authenticate(User.objects.create_user(email=f'{role}@example.com', role=role))
            for path, method in [('', 'post'), (f'{batch.pk}/', 'get'), (f'{batch.pk}/commit/', 'post'), (f'{batch.pk}/resolve-duplicates/', 'post')]:
                self.assertEqual(getattr(self.client, method)(f'/api/uploads/{path}').status_code, 403)

    def sign_in_uploader(self):
        user = User.objects.create_user(email='meta-uploader@example.com', password='Upload123!', role=User.Role.META_UPLOADER)
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        return user

    def test_meta_uploader_fixed_format_review_and_import(self):
        uploader = self.sign_in_uploader()
        self.assertEqual(self.client.get('/api/auth/me/').data['user']['role'], 'META_UPLOADER')
        invalid = self.upload([self.customer(source='meta')], headers=('customer', *HEADINGS[1:]), expected='FAILED')
        self.assertEqual(self.commit(invalid).status_code, 400)
        for extension in ['csv', 'xlsx']:
            batch = self.upload([self.customer(source='meta'), self.customer(source='meta', name='Chosen')], extension=extension)
            self.assertEqual(batch.uploaded_by, uploader)
            self.assertEqual(self.client.get(f'/api/uploads/{batch.pk}/?include_rows=true').status_code, 200)
            self.assertEqual(self.commit(batch).status_code, 409)
            self.choose(batch.rows.get(row_number=3), 'APPROVE')
            self.assertEqual(self.commit(batch).status_code, 200)
        lead = Lead.objects.get(phone='9876543210')
        self.assertEqual((lead.name, lead.source, lead.status, lead.assigned_so_id, lead.assigned_ps_id), ('Chosen', 'META', 'FRESH', None, None))
        self.assertTrue(LeadAudit.objects.filter(lead=lead, actor=uploader, event='imported').exists())
        self.assertTrue(LeadAudit.objects.filter(lead=lead, actor=uploader, event='import_overwrite').exists())

    def test_meta_uploader_cannot_access_other_uploads_or_crm(self):
        admin_batch = self.upload([self.customer()])
        other = User.objects.create_user(email='other-uploader@example.com', role=User.Role.META_UPLOADER)
        other_batch = UploadBatch.objects.create(filename='other.csv', storage_path='other.csv', uploaded_by=other)
        self.sign_in_uploader()
        for batch in [admin_batch, other_batch]:
            for suffix, method in [('', 'get'), ('commit/', 'post'), ('resolve-duplicates/', 'post')]:
                self.assertEqual(getattr(self.client, method)(f'/api/uploads/{batch.pk}/{suffix}').status_code, 404)
        for path in ['/api/leads/', '/api/auth/users/', '/api/auth/sales-officers/', '/api/system-config/', '/api/notifications/', '/api/feedback/', '/api/vehicles/', '/api/service-requests/', '/api/complaints/', '/api/intake/submissions/', '/api/analytics/admin/', '/api/analytics/me/', '/api/ceo/feedback/']:
            for method in ['get', 'post', 'patch', 'delete']:
                with self.subTest(path=path, method=method):
                    # Test real JWT authentication, including views with custom permissions.
                    response = getattr(self.client, method)(path)
                    self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post('/api/auth/logout/').status_code, 204)

    def test_admin_can_manage_meta_uploader_and_preserve_upload_history(self):
        created = self.client.post('/api/auth/users/', {'first_name': 'Meta', 'email': 'new-uploader@example.com', 'password': 'Upload123!', 'role': 'META_UPLOADER'}, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        user = User.objects.get(pk=created.data['id'])
        batch = UploadBatch.objects.create(filename='test.csv', storage_path='test.csv', uploaded_by=user)
        token = str(RefreshToken.for_user(user).access_token)
        for action in ['disable', 'enable', 'permanent-delete']:
            impact = self.client.get(f'/api/auth/users/{user.pk}/offboarding-impact/')
            self.assertEqual(impact.status_code, 200)
            response = self.client.post(f'/api/auth/users/{user.pk}/{action}/', {'impact_version': impact.data['version'], 'routes': [], 'reason': 'Account no longer needed'}, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            if action != 'enable':
                blocked = APIClient()
                blocked.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
                self.assertEqual(blocked.get('/api/auth/me/').status_code, 401)
        batch.refresh_from_db()
        self.assertEqual(batch.uploaded_by_id, user.pk)
        self.assertEqual(self.client.get(f'/api/auth/users/{user.pk}/lifecycle-history/').status_code, 200)

    def test_upload_summary_is_persistent_scoped_and_counts_only_committed_rows(self):
        admin_batch = self.upload([self.customer(phone='9876543299')])
        self.commit(admin_batch)
        uploader = self.sign_in_uploader()
        empty = self.client.get('/api/uploads/summary/')
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.data['totals']['total_uploads'], 0)
        batch = self.upload([self.customer(), self.customer(name='Duplicate'), self.customer(phone='9876543299')])
        pending = self.client.get('/api/uploads/summary/').data
        self.assertEqual(pending['totals']['imported_leads'], 0)
        self.assertEqual(pending['totals']['awaiting_import'], 1)
        self.choose(batch.rows.get(row_number=2), 'APPROVE')
        self.choose(batch.rows.get(row_number=4), 'APPROVE')
        self.commit(batch)
        self.commit(batch)  # Retries must not inflate analytics.
        failed = self.upload([], expected='FAILED')
        awaiting = self.upload([self.customer(phone='9876543288')])
        # A fresh session must return the same durable totals.
        self.client = APIClient()
        self.client.force_authenticate(uploader)
        summary = self.client.get('/api/uploads/summary/').data
        self.assertEqual(summary['totals'], {'total_uploads': 3, 'awaiting_import': 1, 'failed_uploads': 1, 'imported_leads': 1, 'updated_leads': 1, 'skipped_rows': 1})
        self.assertEqual({item['id'] for item in summary['recent']}, {batch.pk, failed.pk, awaiting.pk})
        committed = next(item for item in summary['recent'] if item['id'] == batch.pk)
        self.assertEqual((committed['imported_leads'], committed['updated_leads'], committed['skipped']), (1, 1, 1))
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get('/api/uploads/summary/').data['totals']['imported_leads'], 2)
        self.client.force_authenticate(User.objects.create_user(email='ce-summary@example.com', role='CRE'))
        self.assertEqual(self.client.get('/api/uploads/summary/').status_code, 403)

    @override_settings(CACHE_TTL_SECONDS=300)
    def test_uploader_import_reaches_admin_reports_ceo_and_assigned_ce(self):
        caches['analytics'].clear()
        self.addCleanup(caches['analytics'].clear)
        ce = User.objects.create_user(email='ce-sync@example.com', role='CRE')
        ceo = User.objects.create_user(email='ceo-sync@example.com', role='CEO')
        before = self.client.get('/api/analytics/admin/')
        self.assertEqual(before.data['summary']['total_assigned'], 0)
        self.assertEqual(self.client.get('/api/analytics/admin/')['X-Cache'], 'HIT')
        self.client.force_authenticate(ceo)
        self.assertEqual(self.client.get('/api/ceo/overview/?range=all').data['etbr']['E'], 0)
        self.assertEqual(self.client.get('/api/ceo/overview/?range=all')['X-Cache'], 'HIT')
        self.sign_in_uploader()
        batch = self.upload([self.customer(source='meta')])
        self.assertEqual(self.commit(batch).data['created'], 1)
        lead = Lead.objects.get(phone='9876543210')
        self.client.credentials()
        self.client.force_authenticate(self.admin)
        for path in ['/api/leads/', '/api/leads/?unassigned=true']:
            response = self.client.get(path)
            self.assertEqual([item['id'] for item in response.data['results']], [lead.pk])
        after = self.client.get('/api/analytics/admin/')
        self.assertEqual(after['X-Cache'], 'MISS')
        self.assertEqual(after.data['summary']['total_assigned'], 1)
        self.assertEqual(after.data['source'][0]['source'], 'META')
        self.client.force_authenticate(ceo)
        report = self.client.get('/api/ceo/overview/?range=all')
        self.assertEqual(report['X-Cache'], 'MISS')
        self.assertEqual(report.data['etbr']['E'], 1)
        self.assertEqual(self.client.get('/api/ceo/leads/?range=all').data['results'][0]['id'], lead.pk)
        self.client.force_authenticate(ce)
        self.assertEqual(self.client.get('/api/leads/').data['count'], 0)
        self.client.force_authenticate(self.admin)
        response = self.client.post(f'/api/leads/{lead.pk}/assign/', {'sales_officer_id': ce.pk}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.client.force_authenticate(ce)
        self.assertEqual(self.client.get('/api/leads/').data['results'][0]['id'], lead.pk)
        self.assertEqual(self.client.get('/api/analytics/me/?range=all').data['summary']['total'], 1)
        self.assertTrue(OperationEvent.objects.filter(lead=lead, kind='imported').exists())
        self.assertEqual(Lead.objects.filter(phone=lead.phone).count(), 1)

    def test_rejecting_every_duplicate_finishes_upload_without_adding_leads(self):
        self.sign_in_uploader()
        batch = self.upload([self.customer(), self.customer(name='Duplicate')])
        for row in batch.rows.all():
            self.choose(row, 'SKIP')
        self.assertEqual(self.commit(batch).data, {'created': 0, 'overwritten': 0, 'skipped': 2})
        totals = self.client.get('/api/uploads/summary/').data['totals']
        self.assertEqual((totals['awaiting_import'], totals['imported_leads'], totals['skipped_rows']), (0, 0, 2))
        self.assertFalse(Lead.objects.exists())

    def test_source_is_revalidated_before_import_and_deleted_leads_do_not_block(self):
        Lead.objects.create(name='Deleted', phone='9876543210', deleted_at=timezone.now())
        batch = self.upload([self.customer()])
        self.assertEqual(batch.rows.get().resolution, 'IMPORT')
        SystemConfig.objects.filter(pk=1).update(lists={'sources': ['META'], 'models': ['River Indie']})
        self.assertEqual(self.commit(batch).status_code, 400)
        self.assertEqual(Lead.objects.filter(deleted_at__isnull=True).count(), 0)
