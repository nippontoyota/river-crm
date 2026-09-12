"""Run against an isolated PostgreSQL DB; SQLite cannot exercise advisory locks."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import Lead, SystemConfig
from leads.serializers import LeadSerializer
from uploads.models import UploadBatch, UploadRow
from .models import Connection, IntakeForm, Submission
from .services import accept, resolve
from .tasks import process_submission
from .tests import entries


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL advisory and row locks')
@override_settings(INTAKE_ENABLED=True, CELERY_TASK_ALWAYS_EAGER=False, PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class IntakeConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admin = User.objects.create_user(email='concurrent-admin@example.com', password='password', role='ADMIN')
        SystemConfig.objects.update_or_create(pk=1, defaults={'lists': {'sources': ['WEBSITE']}})
        conn = Connection.objects.create(name='Concurrent site', origin='WEBSITE', source='WEBSITE', secret_ref='site', enabled=True, activated_at=timezone.now() - timedelta(days=1))
        self.form = IntakeForm.objects.create(connection=conn, name='Enquiry', external_id='enquiry', enabled=True, activated_at=conn.activated_at)
        self.publisher = patch('intake.services.publish', return_value=False)
        self.publisher.start(); self.addCleanup(self.publisher.stop)

    def race(self, *jobs):
        barrier = Barrier(len(jobs))
        def run(job):
            close_old_connections()
            try:
                barrier.wait(timeout=5)
                return job()
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
            futures = [pool.submit(run, job) for job in jobs]
            return [future.result(timeout=20) for future in futures]

    def accept(self, external='one', phone='9876543210'):
        with transaction.atomic():
            form = IntakeForm.objects.select_related('connection').get(pk=self.form.pk)
            receipt, _ = accept(form, external, entries=entries(name='Concurrent Customer', phone=phone), submitted_at=timezone.now())
            return receipt.pk

    def batch(self, phone='9876543210'):
        batch = UploadBatch.objects.create(filename='concurrent.csv', storage_path='imports/concurrent.csv', uploaded_by=self.admin, status='READY', original_deleted_at=timezone.now())
        UploadRow.objects.create(batch=batch, row_number=2, normalized_phone=phone, data={'name': 'Excel Customer', 'source': 'WEBSITE'})
        return batch

    def commit(self, batch):
        client = APIClient(); client.force_authenticate(self.admin)
        response = client.post(f'/api/uploads/{batch.pk}/commit/')
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_concurrent_same_delivery_and_workers_create_one_lead(self):
        ids = self.race(lambda: self.accept(), lambda: self.accept())
        self.assertEqual(ids[0], ids[1]); self.assertEqual(Submission.objects.count(), 1)
        self.race(lambda: process_submission.run(str(ids[0])), lambda: process_submission.run(str(ids[1])))
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(Submission.objects.get().state, 'IMPORTED')

    def test_distinct_same_phone_receipts_wait_behind_earliest(self):
        ids = self.race(lambda: self.accept('one'), lambda: self.accept('two'))
        self.race(lambda: process_submission.run(str(ids[0])), lambda: process_submission.run(str(ids[1])))
        # Resolving the earliest may requeue the waiter after its first pass.
        for receipt_id in ids:
            process_submission.run(str(receipt_id))
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(Submission.objects.filter(state='IMPORTED').count(), 1)
        self.assertEqual(Submission.objects.filter(state='NEEDS_REVIEW').count(), 1)

    def test_simultaneous_separate_resolutions_create_once(self):
        Lead.objects.create(name='Existing', phone='9876543210')
        receipt_id = self.accept(); process_submission.run(str(receipt_id))
        self.race(lambda: resolve(receipt_id, 'create_separately', self.admin), lambda: resolve(receipt_id, 'create_separately', self.admin))
        self.assertEqual(Lead.objects.count(), 2)
        self.assertEqual(Lead.objects.filter(duplicate_flag=True).count(), 1)

    def test_simultaneous_batch_commits_create_once(self):
        batch = self.batch()
        results = self.race(lambda: self.commit(batch), lambda: self.commit(batch))
        self.assertEqual(sum(result['created'] for result in results), 1)
        self.assertEqual(Lead.objects.count(), 1)

    def test_manual_and_intake_race(self):
        receipt_id = self.accept()
        def manual():
            serializer = LeadSerializer(data={'name': 'Manual Customer', 'phone': '9876543210', 'source': 'WEBSITE'})
            serializer.is_valid(raise_exception=True)
            try:
                serializer.save()
            except ValidationError:
                return 'held_for_intake'
        results = self.race(manual, lambda: process_submission.run(str(receipt_id)))
        self.assertIn('held_for_intake', results)
        self.assertEqual(Lead.objects.count(), 1)

    def test_phone_change_and_intake_race(self):
        lead = Lead.objects.create(name='Existing other phone', phone='9876543211', source='WEBSITE')
        receipt_id = self.accept()
        def change_phone():
            serializer = LeadSerializer(lead, data={'phone': '9876543210'}, partial=True)
            serializer.is_valid(raise_exception=True)
            try:
                serializer.save()
            except ValidationError:
                return 'held_for_intake'
        self.assertIn('held_for_intake', self.race(change_phone, lambda: process_submission.run(str(receipt_id))))
        lead.refresh_from_db(); self.assertEqual(lead.phone, '9876543211')
        self.assertEqual(Lead.objects.filter(phone='9876543210').count(), 1)

    def test_excel_and_intake_race(self):
        receipt_id = self.accept(); batch = self.batch()
        self.race(lambda: self.commit(batch), lambda: process_submission.run(str(receipt_id)))
        self.assertEqual(Lead.objects.count(), 1)
        self.assertEqual(Submission.objects.get(pk=receipt_id).state, 'IMPORTED')

    def test_resolving_earliest_while_later_is_processing_does_not_deadlock(self):
        earliest = self.accept('first'); later = self.accept('second')
        process_submission.run(str(later))
        Submission.objects.filter(pk=later).update(next_attempt_at=timezone.now())
        self.race(lambda: resolve(earliest, 'dismiss', self.admin), lambda: process_submission.run(str(later)))
        Submission.objects.filter(pk=later).update(next_attempt_at=timezone.now())
        process_submission.run(str(later))
        self.assertEqual(Lead.objects.count(), 1)
