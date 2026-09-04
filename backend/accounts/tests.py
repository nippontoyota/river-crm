from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from complaints.models import Complaint, ComplaintNote
from leads.models import CallLog, FollowUp, Lead, LeadAudit, LeadQualification, SystemConfig
from notifications.models import Notification
from notifications.tasks import create_due_follow_up_notifications
from uploads.models import UploadBatch, UploadRow

from .models import User, UserLifecycleEvent


class ResetProductionDataTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("admin@river.test", "unchanged-password")
        self.worker = User.objects.create_user(email="worker@example.com", password="password", role=User.Role.CRE)
        UserLifecycleEvent.objects.create(user=self.worker, actor=self.admin, action=UserLifecycleEvent.Action.DISABLED)
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
        for model in (UserLifecycleEvent, ComplaintNote, Notification, UploadRow, LeadQualification, CallLog, FollowUp, LeadAudit, Complaint, UploadBatch, Lead, SystemConfig, Group):
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


class UserOffboardingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("admin@example.com", "password", role=User.Role.ADMIN)
        self.worker = User.objects.create_user("worker@example.com", "password", role=User.Role.CRE, first_name="Former", last_name="Employee")
        self.replacement = User.objects.create_user("replacement@example.com", "password", role=User.Role.CRE)
        self.client.force_authenticate(self.admin)

    def impact(self):
        response = self.client.get(f"/api/auth/users/{self.worker.id}/offboarding-impact/")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_disable_routes_actionable_work_and_preserves_closed_history(self):
        ps = User.objects.create_user("ps@example.com", "password", role=User.Role.SALES_OFFICER)
        fresh = Lead.objects.create(name="Fresh", phone="7000000001", assigned_so=self.worker, assigned_ps=ps)
        closed = Lead.objects.create(name="Won", phone="7000000002", assigned_so=self.worker, status=Lead.Status.WON)
        followup = FollowUp.objects.create(lead=fresh, so=self.worker, scheduled_for=timezone.now())
        ps_followup = FollowUp.objects.create(lead=fresh, so=ps, scheduled_for=timezone.now())
        notification = Notification.objects.create(user=self.worker, lead=fresh, kind=Notification.Kind.ASSIGNMENT, message="Old")
        complaint = Complaint.objects.create(
            customer_name="Customer", customer_phone="7000000003", category=Complaint.Category.OTHER,
            subject="Open", description="Open", logged_by=self.worker, assigned_to=self.worker,
        )
        impact = self.impact()

        response = self.client.post(f"/api/auth/users/{self.worker.id}/disable/", {
            "impact_version": impact["version"],
            "routes": [{"status": Lead.Status.FRESH, "destination": "DISTRIBUTE", "recipient_ids": [self.replacement.id]}],
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.worker.refresh_from_db(); fresh.refresh_from_db(); closed.refresh_from_db(); followup.refresh_from_db(); ps_followup.refresh_from_db(); complaint.refresh_from_db()
        self.assertFalse(self.worker.is_active)
        self.assertEqual(fresh.assigned_so, self.replacement)
        self.assertEqual(fresh.status, Lead.Status.FRESH)
        self.assertFalse(fresh.needs_cre_reassignment)
        self.assertEqual(closed.assigned_so, self.worker)
        self.assertEqual(followup.so, self.replacement)
        self.assertTrue(followup.reminder_held)
        self.assertEqual(ps_followup.so, ps)
        self.assertFalse(ps_followup.reminder_held)
        self.assertIsNone(complaint.assigned_to)
        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())
        self.assertTrue(complaint.notes.filter(author=self.admin).exists())
        self.assertTrue(UserLifecycleEvent.objects.filter(user=self.worker, action=UserLifecycleEvent.Action.DISABLED).exists())

    def test_pool_then_bulk_reassign_and_approve_reminder(self):
        lead = Lead.objects.create(name="Pool", phone="7000000004", assigned_so=self.worker, status=Lead.Status.PENDING)
        followup = FollowUp.objects.create(lead=lead, so=self.worker, scheduled_for=timezone.now())
        impact = self.impact()
        disabled = self.client.post(f"/api/auth/users/{self.worker.id}/disable/", {
            "impact_version": impact["version"],
            "routes": [{"status": Lead.Status.PENDING, "destination": "POOL", "recipient_ids": []}],
        }, format="json")
        self.assertEqual(disabled.status_code, 200)
        lead.refresh_from_db(); followup.refresh_from_db()
        self.assertIsNone(lead.assigned_so)
        self.assertTrue(lead.needs_cre_reassignment)
        self.assertTrue(followup.reminder_held)
        create_due_follow_up_notifications()
        self.assertFalse(Notification.objects.filter(lead=lead, kind=Notification.Kind.OVERDUE).exists())

        assigned = self.client.post("/api/leads/bulk-reassign/", {"role": "CRE", "lead_ids": [lead.id], "recipient_ids": [self.replacement.id]}, format="json")
        self.assertEqual(assigned.status_code, 200)
        lead.refresh_from_db(); followup.refresh_from_db()
        self.assertEqual(lead.assigned_so, self.replacement)
        self.assertFalse(lead.needs_cre_reassignment)
        self.assertEqual(followup.so, self.replacement)
        self.assertTrue(followup.reminder_held)

        reviewed = self.client.patch(f"/api/follow-ups/{followup.id}/review/", {"action": "APPROVE"}, format="json")
        self.assertEqual(reviewed.status_code, 200)
        followup.refresh_from_db()
        self.assertFalse(followup.reminder_held)
        self.assertIsNone(followup.notified_at)
        create_due_follow_up_notifications()
        self.assertTrue(Notification.objects.filter(user=self.replacement, lead=lead, kind=Notification.Kind.OVERDUE).exists())

    def test_stale_preview_rejects_without_partial_changes(self):
        lead = Lead.objects.create(name="Changed", phone="7000000005", assigned_so=self.worker)
        impact = self.impact()
        lead.status = Lead.Status.PENDING
        lead.save(update_fields=["status", "updated_at"])

        response = self.client.post(f"/api/auth/users/{self.worker.id}/disable/", {
            "impact_version": impact["version"],
            "routes": [{"status": Lead.Status.FRESH, "destination": "POOL", "recipient_ids": []}],
        }, format="json")

        self.assertEqual(response.status_code, 409)
        self.worker.refresh_from_db(); lead.refresh_from_db()
        self.assertTrue(self.worker.is_active)
        self.assertEqual(lead.assigned_so, self.worker)

    def test_departing_employee_cannot_be_selected_as_their_own_replacement(self):
        lead = Lead.objects.create(name="Self route", phone="7000000008", assigned_so=self.worker)
        impact = self.impact()

        response = self.client.post(f"/api/auth/users/{self.worker.id}/disable/", {
            "impact_version": impact["version"],
            "routes": [{"status": Lead.Status.FRESH, "destination": "DISTRIBUTE", "recipient_ids": [self.worker.id]}],
        }, format="json")

        self.assertEqual(response.status_code, 409)
        self.worker.refresh_from_db(); lead.refresh_from_db()
        self.assertTrue(self.worker.is_active)
        self.assertEqual(lead.assigned_so, self.worker)

    def test_permanent_delete_scrubs_credentials_and_allows_email_reuse(self):
        original_email = self.worker.email
        impact = self.impact()
        response = self.client.post(f"/api/auth/users/{self.worker.id}/permanent-delete/", {
            "impact_version": impact["version"], "routes": [], "reason": "Employment ended",
        }, format="json")

        self.assertEqual(response.status_code, 200)
        self.worker.refresh_from_db()
        self.assertIsNotNone(self.worker.deleted_at)
        self.assertFalse(self.worker.is_active)
        self.assertFalse(self.worker.has_usable_password())
        self.assertNotEqual(self.worker.email, original_email)
        self.assertEqual(self.worker.get_full_name(), "Former Employee")
        User.objects.create_user(original_email, "new-password", role=User.Role.CRE)
        self.assertEqual(UserLifecycleEvent.objects.get(user=self.worker).reason, "Employment ended")
        listed_ids = [item["id"] for item in self.client.get("/api/auth/users/").data["results"]]
        self.assertNotIn(self.worker.id, listed_ids)
        history = self.client.get(f"/api/auth/users/{self.worker.id}/lifecycle-history/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.data["lifecycle_status"], "DELETED")
        self.assertEqual(history.data["account_history"][0]["reason"], "Employment ended")

    def test_ps_distribution_is_branch_safe_and_unmatched_leads_stay_pooled(self):
        ps = User.objects.create_user("ps@example.com", "password", role=User.Role.SALES_OFFICER, location="Kochi")
        kochi = User.objects.create_user("kochi@example.com", "password", role=User.Role.SALES_OFFICER, location="Kochi")
        other = User.objects.create_user("other@example.com", "password", role=User.Role.SALES_OFFICER, location="Thrissur")
        matched = Lead.objects.create(name="Matched", phone="7000000006", assigned_ps=ps, branch="Kochi", status=Lead.Status.PENDING)
        missing_branch = Lead.objects.create(name="Missing", phone="7000000007", assigned_ps=ps, status=Lead.Status.PENDING)
        impact = self.client.get(f"/api/auth/users/{ps.id}/offboarding-impact/").data

        response = self.client.post(f"/api/auth/users/{ps.id}/disable/", {
            "impact_version": impact["version"],
            "routes": [{"status": Lead.Status.PENDING, "destination": "DISTRIBUTE", "recipient_ids": [kochi.id, other.id]}],
        }, format="json")

        self.assertEqual(response.status_code, 200)
        matched.refresh_from_db(); missing_branch.refresh_from_db()
        self.assertEqual(matched.assigned_ps, kochi)
        self.assertFalse(matched.needs_so_reassignment)
        self.assertIsNone(missing_branch.assigned_ps)
        self.assertTrue(missing_branch.needs_so_reassignment)

    def test_delete_requires_reason(self):
        impact = self.impact()
        response = self.client.post(f"/api/auth/users/{self.worker.id}/permanent-delete/", {"impact_version": impact["version"], "routes": []}, format="json")
        self.assertEqual(response.status_code, 400)
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.is_active)
