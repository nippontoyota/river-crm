from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from complaints.models import Complaint, ComplaintNote
from leads.models import CallLog, FollowUp, Lead, LeadAudit, LeadQualification, SystemConfig
from notifications.models import Notification
from uploads.models import UploadBatch, UploadRow

from .models import User


class ResetProductionDataTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin@river.test", "unchanged-password")
        self.worker = User.objects.create_user(email="worker@example.com", password="password", role=User.Role.CRE)
        self.lead = Lead.objects.create(name="Demo", phone="7000000000", assigned_so=self.worker)
        LeadQualification.objects.create(lead=self.lead, variant="Blue", updated_by=self.worker)
        CallLog.objects.create(lead=self.lead, so=self.worker, status=Lead.Status.FRESH)
        FollowUp.objects.create(lead=self.lead, so=self.worker, scheduled_for="2026-09-04T10:00:00Z")
        LeadAudit.objects.create(lead=self.lead, actor=self.worker, event="created")
        Notification.objects.create(user=self.worker, lead=self.lead, kind=Notification.Kind.ASSIGNMENT, message="Assigned")
        complaint = Complaint.objects.create(customer_name="Demo", customer_phone="7000000000", category=Complaint.Category.OTHER, subject="Demo", description="Demo", logged_by=self.worker, related_lead=self.lead)
        ComplaintNote.objects.create(complaint=complaint, author=self.worker, content="Demo")
        batch = UploadBatch.objects.create(filename="demo.xlsx", storage_path="imports/demo.xlsx", uploaded_by=self.admin)
        UploadRow.objects.create(batch=batch, row_number=1, duplicate_of=self.lead)
        SystemConfig.objects.create(id=1, lists={"branches": ["Kochi"], "colorVariants": ["Blue"]})
        self.admin.groups.add(Group.objects.create(name="Demo group"))

    def test_dry_run_changes_nothing(self):
        output = StringIO()

        call_command("reset_production_data", admin_email=self.admin.email, delete_storage=True, stdout=output)

        self.assertIn("Dry run only", output.getvalue())
        self.assertEqual(User.objects.count(), 2)
        self.assertTrue(Lead.objects.exists())
        self.assertTrue(UploadBatch.objects.exists())

    @patch("accounts.management.commands.reset_production_data.delete_paths")
    def test_confirmed_reset_retains_only_admin_and_password(self, delete_mock):
        password_hash = self.admin.password

        call_command("reset_production_data", admin_email=self.admin.email, delete_storage=True, confirm_production_reset=True)

        delete_mock.assert_called_once_with(["imports/demo.xlsx"])
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.password, password_hash)
        self.assertTrue(self.admin.check_password("unchanged-password"))
        self.assertEqual(list(User.objects.values_list("email", flat=True)), ["admin@river.test"])
        for model in (ComplaintNote, Notification, UploadRow, LeadQualification, CallLog, FollowUp, LeadAudit, Complaint, UploadBatch, Lead, SystemConfig, Group):
            self.assertFalse(model.objects.exists(), model._meta.label)

    @patch("accounts.management.commands.reset_production_data.delete_paths", side_effect=RuntimeError("storage unavailable"))
    def test_storage_failure_leaves_database_untouched(self, _delete_mock):
        with self.assertRaisesMessage(RuntimeError, "storage unavailable"):
            call_command("reset_production_data", admin_email=self.admin.email, delete_storage=True, confirm_production_reset=True)

        self.assertEqual(User.objects.count(), 2)
        self.assertTrue(Lead.objects.exists())
        self.assertTrue(UploadBatch.objects.exists())

    def test_rejects_non_superuser_keeper(self):
        with self.assertRaises(CommandError):
            call_command("reset_production_data", admin_email=self.worker.email)
