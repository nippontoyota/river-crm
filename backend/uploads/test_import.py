"""Bulk import regression coverage, using real CSV/XLSX files and local storage."""
import csv
import io
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from openpyxl import Workbook
from rest_framework.test import APIClient

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
        self.assertEqual(HEADINGS, ('name', 'phone', 'email', 'source', 'enquiry date'))
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

    def test_bad_headings_report_missing_unknown_repeated_and_blank_columns(self):
        cases = [
            (HEADINGS[:-1], 'Missing headings: enquiry date'),
            (('Customer Name', *HEADINGS[1:]), 'Unrecognized headings: Customer Name'),
            (('phone', *HEADINGS[1:]), 'Repeated headings: phone'),
            (('', *HEADINGS[1:]), 'Blank headings in columns: 1'),
            ((*HEADINGS, 'assigned_so'), 'Unrecognized headings: assigned_so'),
            ((*HEADINGS, 'campaign', 'model', 'city', 'RTO'), 'Unrecognized headings: campaign, model, city, RTO'),
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
        self.assertIn('Row 2 has 2 cells; expected 5', batch.error_message)

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

    def test_source_is_revalidated_before_import_and_deleted_leads_do_not_block(self):
        Lead.objects.create(name='Deleted', phone='9876543210', deleted_at=timezone.now())
        batch = self.upload([self.customer()])
        self.assertEqual(batch.rows.get().resolution, 'IMPORT')
        SystemConfig.objects.filter(pk=1).update(lists={'sources': ['META'], 'models': ['River Indie']})
        self.assertEqual(self.commit(batch).status_code, 400)
        self.assertEqual(Lead.objects.filter(deleted_at__isnull=True).count(), 0)
