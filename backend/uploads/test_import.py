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
from intake.models import Connection, IntakeForm, MappingVersion, Submission
from intake.mapping import map_entries
from leads.models import Lead, LeadAudit, SystemConfig
from leads.rtos import KERALA_RTO_CHOICES, normalize_rto
from .models import UploadBatch


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
        SystemConfig.objects.update_or_create(pk=1, defaults={'lists': {
            'sources': ['WEBSITE', 'META'], 'models': ['River Indie'], 'branches': ['Kochi'],
            'activities': ['Campaign'], 'subActivities': {'Campaign': ['Launch']},
        }})
        publisher = patch('uploads.views.publish', side_effect=lambda task, *args: task.run(*args))
        publisher.start()
        self.addCleanup(publisher.stop)

    def upload(self, rows, headers=('name', 'phone', 'source', 'rto'), extension='csv', mapping=None):
        if extension == 'xlsx':
            workbook = Workbook()
            workbook.active.append(list(headers))
            for row in rows:
                workbook.active.append(list(row))
            output = io.BytesIO()
            workbook.save(output)
            content = output.getvalue()
        else:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(headers)
            writer.writerows(rows)
            content = output.getvalue().encode('utf-8-sig')
        payload = {'file': SimpleUploadedFile(f'leads.{extension}', content)}
        if mapping:
            payload['mapping_version'] = mapping.pk
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post('/api/uploads/', payload, format='multipart')
        self.assertEqual(response.status_code, 202, response.data)
        batch = UploadBatch.objects.get(pk=response.data['id'])
        self.assertEqual(batch.status, 'READY', batch.error_message)
        return batch

    def commit(self, batch):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(f'/api/uploads/{batch.pk}/commit/', {}, format='json')

    def choose(self, row, resolution):
        response = self.client.post(f'/api/uploads/{row.batch_id}/resolve-duplicates/', {'rows': [{'id': row.pk, 'resolution': resolution}]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)

    def correct(self, row, **corrections):
        response = self.client.post(f'/api/uploads/{row.batch_id}/correct-row/', {'row_id': row.pk, 'corrections': corrections}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        row.refresh_from_db()
        return response.data

    def pending(self, phone='9876543210'):
        connection = Connection.objects.create(name='Website', origin='WEBSITE', source='WEBSITE', secret_ref='test')
        form = IntakeForm.objects.create(connection=connection, name='Enquiry', external_id='test')
        return Submission.objects.create(connection=connection, form=form, identity='test', external_id='test', source='WEBSITE', normalized_phone=phone, state='NEEDS_REVIEW')

    def test_csv_and_xlsx_ingest_every_customer_field_and_rto(self):
        headers = ['name', 'phone', 'email', 'model_interest', 'city', 'RTO Code', 'profession', 'branch', 'enquiry_date', 'campaign', 'source_label', 'activity', 'sub_activity', 'source']
        for number, extension in enumerate(['csv', 'xlsx']):
            with self.subTest(extension=extension):
                phone = f'987654321{number}'
                batch = self.upload([['Customer', int(phone), 'customer@example.com', 'River Indie', 'Kochi', 'kl 7' if extension == 'csv' else 'Ernakulamm', 'Engineer', 'Kochi', timezone.localdate(), 'Launch campaign', 'Website form', 'Campaign', 'Launch', 'website']], headers, extension)
                row = batch.rows.get()
                self.assertEqual(row.data['rto'], 'KL-07')
                self.assertEqual(row.validation_errors, {})
                self.assertIsNotNone(batch.original_deleted_at)
                review = self.client.get(f'/api/uploads/{batch.pk}/?include_rows=true')
                self.assertEqual(review.data['rows'][0]['data']['rto'], 'KL-07')
                result = self.commit(batch)
                self.assertEqual(result.data, {'created': 1, 'overwritten': 0, 'skipped': 0})
                lead = Lead.objects.get(phone=phone)
                expected = {**row.data, 'phone': phone}
                expected['enquiry_date'] = timezone.localdate()
                for field, value in expected.items():
                    self.assertEqual(getattr(lead, field), value, field)
                self.assertEqual((lead.status, lead.assigned_so_id, lead.assigned_ps_id, lead.generated_by_id), ('FRESH', None, None, None))
                self.assertTrue(LeadAudit.objects.filter(lead=lead, event='imported').exists())
                self.assertTrue(Milestone.objects.filter(lead=lead, kind='E', rto='KL-07').exists())
                self.assertTrue(OperationEvent.objects.filter(lead=lead, snapshot__rto='KL-07').exists())
                self.assertEqual(batch.rows.get().answers, [])
                self.assertTrue(self.commit(batch).data['already_committed'])

    def test_legacy_file_without_rto_still_imports(self):
        batch = self.upload([['Legacy', '9876543210', 'website']], ('name', 'phone', 'source'))
        self.assertEqual(self.commit(batch).data['created'], 1)
        self.assertEqual(Lead.objects.get().rto, '')

    def test_equivalent_rto_columns_agree_and_conflicting_columns_need_review(self):
        entries = [{'id': f'column:{index}', 'label': label, 'value': value} for index, (label, value) in enumerate([
            ('name', 'Customer'), ('phone', '9876543210'), ('source', 'website'), ('RTO', 'kl05'), ('RTO Code', 'Kottayam'),
        ])]
        result = map_entries(entries, excel=True)
        self.assertEqual(result['errors'], {})
        self.assertEqual(result['values']['rto'], 'KL-05')
        entries[-1]['value'] = 'Kollam'
        self.assertIn('rto', map_entries(entries, excel=True)['errors'])

    def test_invalid_rto_corrected_with_approved_code(self):
        batch = self.upload([['Customer', '9876543210', 'website', 'TN-01']])
        row = batch.rows.get()
        self.assertIn('rto', row.validation_errors)
        data = self.correct(row, rto='kl07')
        self.assertEqual(data['data']['rto'], 'KL-07')
        self.assertEqual(data['validation_errors'], {})
        self.assertEqual(self.commit(batch).data['created'], 1)
        self.assertEqual(Lead.objects.get().rto, 'KL-07')

    def test_invalid_rows_skipped_and_empty_rows_ignored(self):
        batch = self.upload([['Bad RTO', '9876543210', 'website', 'KL-99'], ['Bad phone', '123', 'website', 'KL-07'], ['', '', '', ''], ['Valid', '9876543211', 'website', 'KL-08']])
        self.assertEqual(batch.total_rows, 3)
        self.assertEqual(batch.parsed_ok, 1)
        self.assertEqual(self.commit(batch).data, {'created': 1, 'overwritten': 0, 'skipped': 2})
        self.assertEqual(Lead.objects.get().rto, 'KL-08')

    def test_normalized_crm_and_file_duplicates_are_skipped(self):
        existing = Lead.objects.create(name='Existing', phone='9876543210', rto='KL-08')
        batch = self.upload([['CRM duplicate', '+91 98765-43210', 'website', 'KL-07'], ['First', '9876543211', 'website', 'KL-07'], ['File duplicate', '09876543211', 'meta', 'KL-08']])
        self.assertEqual(list(batch.rows.order_by('row_number').values_list('resolution', flat=True)), ['SKIP', 'IMPORT', 'SKIP'])
        self.assertEqual(self.commit(batch).data, {'created': 1, 'overwritten': 0, 'skipped': 2})
        existing.refresh_from_db()
        self.assertEqual((existing.name, existing.rto), ('Existing', 'KL-08'))

    def test_pending_intake_duplicate_is_visible_and_skipped(self):
        self.pending()
        batch = self.upload([['Pending duplicate', '9876543210', 'website', 'KL-07']])
        review = self.client.get(f'/api/uploads/{batch.pk}/?include_rows=true').data
        self.assertEqual(review['intake_duplicates_found'], 1)
        self.assertEqual(review['rows'][0]['duplicate_type'], 'INTAKE')
        self.assertEqual(self.commit(batch).data, {'created': 0, 'overwritten': 0, 'skipped': 1})

    def test_explicit_separate_import_flags_crm_file_and_intake_duplicates(self):
        Lead.objects.create(name='Existing', phone='9876543210', rto='KL-08')
        self.pending('9876543211')
        batch = self.upload([['CRM', '9876543210', 'website', 'KL-07'], ['Intake', '9876543211', 'website', 'KL-07'], ['First', '9876543212', 'website', 'KL-07'], ['File', '9876543212', 'website', 'KL-08']])
        for row in batch.rows.filter(resolution='SKIP'):
            self.choose(row, 'IMPORT')
        self.assertEqual(self.commit(batch).data, {'created': 4, 'overwritten': 0, 'skipped': 0})
        self.assertEqual(Lead.objects.filter(duplicate_flag=True).count(), 3)

    def test_overwrite_updates_rto_preserves_ownership_and_legacy_blank_rto(self):
        lead = Lead.objects.create(name='Existing', phone='9876543210', rto='KL-08', assigned_so=self.admin, status='QUALIFIED')
        for rto, expected in [('KL-07', 'KL-07'), ('', 'KL-07')]:
            batch = self.upload([['Updated', lead.phone, 'website', rto]])
            self.choose(batch.rows.get(), 'OVERWRITE')
            self.assertEqual(self.commit(batch).data['overwritten'], 1)
            lead.refresh_from_db()
            self.assertEqual((lead.name, lead.rto, lead.status, lead.assigned_so_id), ('Updated', expected, 'QUALIFIED', self.admin.pk))
        self.assertEqual(Lead.objects.count(), 1)

    def test_correction_reclassifies_new_and_old_file_duplicate_phones(self):
        lead = Lead.objects.create(name='CRM target', phone='9876543210', rto='KL-08')
        batch = self.upload([['First', '9876543211', 'website', 'KL-07'], ['Second', '9876543211', 'website', 'KL-08']])
        first, second = batch.rows.order_by('row_number')
        self.choose(first, 'IMPORT')
        self.correct(first, phone=lead.phone)
        second.refresh_from_db()
        self.assertEqual(first.duplicate_of_id, lead.pk)
        self.assertEqual(first.resolution, 'SKIP')
        self.assertFalse(first.resolution_explicit)
        self.assertEqual(second.resolution, 'IMPORT')
        self.assertEqual(self.commit(batch).data, {'created': 1, 'overwritten': 0, 'skipped': 1})

    def test_rto_correction_keeps_reviewed_overwrite_target(self):
        lead = Lead.objects.create(name='Existing', phone='9876543210', rto='KL-08')
        batch = self.upload([['Updated', lead.phone, 'website', 'KL-07']])
        row = batch.rows.get()
        self.choose(row, 'OVERWRITE')
        self.correct(row, rto='KL-09')
        self.assertEqual((row.resolution, row.duplicate_of_id), ('OVERWRITE', lead.pk))
        self.assertEqual(self.commit(batch).data['overwritten'], 1)
        lead.refresh_from_db()
        self.assertEqual(lead.rto, 'KL-09')

    def test_new_crm_or_intake_match_at_commit_is_skipped(self):
        first = self.upload([['CRM race', '9876543210', 'website', 'KL-07']])
        second = self.upload([['Intake race', '9876543211', 'website', 'KL-07']])
        Lead.objects.create(name='Created meanwhile', phone='9876543210')
        self.pending('9876543211')
        for batch in [first, second]:
            self.assertEqual(self.commit(batch).data['skipped'], 1)
        self.assertEqual(Lead.objects.count(), 1)

    def test_deleted_lead_does_not_block_import(self):
        Lead.objects.create(name='Deleted', phone='9876543210', deleted_at=timezone.now())
        batch = self.upload([['New', '9876543210', 'website', 'KL-07']])
        self.assertEqual(self.commit(batch).data['created'], 1)
        self.assertFalse(Lead.objects.get(deleted_at__isnull=True).duplicate_flag)

    def test_changed_overwrite_target_rolls_back_entire_commit(self):
        lead = Lead.objects.create(name='Existing', phone='9876543210', rto='KL-08')
        batch = self.upload([['New', '9876543211', 'website', 'KL-07'], ['Overwrite', lead.phone, 'website', 'KL-07']])
        self.choose(batch.rows.get(duplicate_of=lead), 'OVERWRITE')
        Lead.objects.filter(pk=lead.pk).update(phone='9876543212')
        self.assertEqual(self.commit(batch).status_code, 400)
        self.assertEqual(Lead.objects.count(), 1)
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'READY')

    def test_pending_resolution_blocks_commit_and_invalid_overwrite_rejected(self):
        batch = self.upload([['New', '9876543210', 'website', 'KL-07']])
        row = batch.rows.get()
        self.choose(row, 'PENDING')
        self.assertEqual(self.commit(batch).status_code, 400)
        response = self.client.post(f'/api/uploads/{batch.pk}/resolve-duplicates/', {'rows': [{'id': row.pk, 'resolution': 'OVERWRITE'}]}, format='json')
        self.assertEqual(response.status_code, 400)
        self.choose(row, 'SKIP')
        self.assertEqual(self.commit(batch).data['skipped'], 1)

    def test_invalid_duplicate_decisions_return_validation_errors(self):
        batch = self.upload([['New', '9876543210', 'website', 'KL-07']])
        for rows in [[], [{'id': 'bad', 'resolution': 'SKIP'}], [{'id': batch.rows.get().pk, 'resolution': 'WRONG'}], [{'id': 999999, 'resolution': 'SKIP'}]]:
            with self.subTest(rows=rows):
                response = self.client.post(f'/api/uploads/{batch.pk}/resolve-duplicates/', {'rows': rows}, format='json')
                self.assertEqual(response.status_code, 400)

    def test_custom_mapping_and_reparse_retain_rto_after_file_deletion(self):
        headers = ('name', 'phone', 'source', 'Registration Office')
        batch = self.upload([['Mapped', '9876543210', 'website', 'Ernakulam']], headers)
        self.assertEqual(batch.rows.get().data['rto'], '')
        mapping = MappingVersion.objects.create(template_name='RTO import', version=1, created_by=self.admin, rules={'fields': {'column:4': 'rto'}, 'value_aliases': {'rto': {'Ernakulam': 'KL-07'}}})
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f'/api/uploads/{batch.pk}/reparse/', {'mapping_version': mapping.pk}, format='json')
        self.assertEqual(response.status_code, 202)
        self.assertEqual(batch.rows.get().data['rto'], 'KL-07')
        self.assertEqual(self.commit(batch).data['created'], 1)
        self.assertEqual(Lead.objects.get().rto, 'KL-07')

    def test_ownership_columns_ignored_and_source_revalidated_at_commit(self):
        batch = self.upload([['New', '9876543210', 'website', 'KL-07', self.admin.pk, 'WON']], ('name', 'phone', 'source', 'rto', 'assigned_so', 'status'))
        row = batch.rows.get()
        self.assertEqual(set(row.ignored_labels), {'assigned_so', 'status'})
        SystemConfig.objects.filter(pk=1).update(lists={'sources': ['META']})
        self.assertEqual(self.commit(batch).data['skipped'], 1)
        self.assertFalse(Lead.objects.exists())

    def test_non_admin_cannot_use_bulk_actions(self):
        batch = self.upload([['New', '9876543210', 'website', 'KL-07']])
        for role in ['CEO', 'CRE', 'SO', 'SALES_MANAGER', 'RECEPTIONIST']:
            user = User.objects.create_user(email=f'{role}@example.com', role=role)
            self.client.force_authenticate(user)
            for path, method in [('', 'post'), (f'{batch.pk}/', 'get'), (f'{batch.pk}/commit/', 'post'), (f'{batch.pk}/correct-row/', 'post'), (f'{batch.pk}/resolve-duplicates/', 'post'), (f'{batch.pk}/reparse/', 'post')]:
                with self.subTest(role=role, path=path):
                    self.assertEqual(getattr(self.client, method)(f'/api/uploads/{path}').status_code, 403)

    def test_imported_rto_visible_to_admin_assigned_staff_manager_and_ceo(self):
        batch = self.upload([['Visible', '9876543210', 'website', 'KL-07']])
        self.commit(batch)
        lead = Lead.objects.get()
        cre = User.objects.create_user(email='ce@example.com', role='CRE', location='Kochi')
        so = User.objects.create_user(email='so@example.com', role='SO', location='Kochi')
        manager = User.objects.create_user(email='manager@example.com', role='SALES_MANAGER', location='Kochi')
        ceo = User.objects.create_user(email='ceo@example.com', role='CEO')
        Lead.objects.filter(pk=lead.pk).update(assigned_so=cre, assigned_ps=so, branch='Kochi')
        for user in [self.admin, cre, so, manager]:
            self.client.force_authenticate(user)
            response = self.client.get(f'/api/leads/{lead.pk}/')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['rto'], 'KL-07')
        self.client.force_authenticate(ceo)
        response = self.client.get(f'/api/ceo/leads/{lead.pk}/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['rto'], 'KL-07')
