from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import CallLog, FollowUp, Lead, LeadAudit, LeadQualification


class EtbrTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(email="etbr-admin@example.com", role=User.Role.ADMIN)
        self.so = User.objects.create_user(email="etbr-so@example.com", role=User.Role.SALES_OFFICER, location="Kochi")
        self.cre = User.objects.create_user(email="etbr-cre@example.com", role=User.Role.CRE)
        self.manager = User.objects.create_user(email="etbr-manager@example.com", role=User.Role.SALES_MANAGER, location="Kochi")
        self.receptionist = User.objects.create_user(email="etbr-front@example.com", role=User.Role.RECEPTIONIST, location="Kochi")
        self.lead = Lead.objects.create(name="ETBR enquiry", phone="9876543210", branch="Kochi", enquiry_date=timezone.localdate(), assigned_ps=self.so, assigned_so=self.cre, source=Lead.Source.WALKIN, status=Lead.Status.QUALIFIED)
        LeadQualification.objects.create(lead=self.lead, test_drive="Requested")
        CallLog.objects.create(lead=self.lead, so=self.so, status=Lead.Status.PENDING, outcome="Need Test Drive")
        FollowUp.objects.create(lead=self.lead, so=self.so, scheduled_for=timezone.now() + timedelta(days=1))
        LeadAudit.objects.create(lead=self.lead, actor=self.receptionist, event="created")

    def test_completion_is_owned_idempotent_and_does_not_change_pipeline(self):
        path = f"/api/leads/{self.lead.id}/complete-test-drive/"
        for user in (self.cre, self.receptionist, self.manager):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.post(path).status_code, 403)
        unrelated = User.objects.create_user(email="etbr-other@example.com", role=User.Role.SALES_OFFICER)
        self.client.force_authenticate(unrelated)
        self.assertEqual(self.client.post(path).status_code, 404)
        self.client.force_authenticate(self.so)
        response = self.client.post(path)
        self.assertEqual(response.status_code, 200, response.data)
        completed_at = response.data["test_drive_completed_at"]
        self.assertEqual(self.client.post(path).data["test_drive_completed_at"], completed_at)
        self.assertEqual(LeadAudit.objects.filter(lead=self.lead, event="test_drive_completed").count(), 1)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, Lead.Status.QUALIFIED)
        self.assertEqual(self.lead.sales_outcome, Lead.SalesOutcome.PENDING)
        self.assertEqual(self.lead.qualification.test_drive, "Requested")
        self.assertEqual(self.lead.follow_ups.filter(resolved_at__isnull=True).count(), 1)
        self.assertEqual(self.lead.call_logs.count(), 1)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.post(path).status_code, 200)

    def test_etbr_across_roles_preserves_existing_counts_and_scopes(self):
        self.client.force_authenticate(self.so)
        requested = self.client.get("/api/analytics/me/?range=today").data["summary"]
        self.assertEqual(requested["etbr_test_drive_completed"], 0)
        self.client.post(f"/api/leads/{self.lead.id}/complete-test-drive/")
        self.lead.sales_outcome = Lead.SalesOutcome.RETAILED
        self.lead.status = Lead.Status.WON
        self.lead.save(update_fields=["sales_outcome", "status"])
        # Multiple joined records must not duplicate the enquiry.
        CallLog.objects.create(lead=self.lead, so=self.so, status=Lead.Status.WON, outcome="Retail Done")
        Lead.objects.create(name="Outside branch", phone="9876543211", branch="Thrissur", enquiry_date=timezone.localdate(), test_drive_completed_at=timezone.now())
        Lead.objects.create(name="Deleted", phone="9876543212", branch="Kochi", enquiry_date=timezone.localdate(), assigned_ps=self.so, deleted_at=timezone.now())
        expected = {"etbr_enquired": 1, "etbr_test_drive_completed": 1, "etbr_booked": 1, "etbr_retailed": 1}
        for user, path in [(self.so, "/api/analytics/me/?range=today"), (self.cre, "/api/analytics/me/?range=today"), (self.so, "/api/leads/my-dashboard/"), (self.manager, "/api/analytics/sales-manager/?range=today"), (self.receptionist, "/api/analytics/receptionist/")]:
            self.client.force_authenticate(user)
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual({key: response.data["summary"][key] for key in expected}, expected)
            if "booked" in response.data["summary"]:
                self.assertEqual(response.data["summary"]["booked"], 0)
        self.client.force_authenticate(self.admin)
        summary = self.client.get("/api/analytics/admin/").data["summary"]
        self.assertEqual(summary["etbr_enquired"], 2)
        self.client.force_authenticate(self.so)
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertEqual(self.client.get(f"/api/analytics/me/?range=custom&date_from={yesterday}&date_to={yesterday}").data["summary"]["etbr_enquired"], 0)

    def test_receptionist_dashboard_excludes_digital_other_staff_and_previous_days(self):
        for name, source, actor, old, deleted in [
            ("Digital", Lead.Source.META, self.receptionist, False, False),
            ("Other staff", Lead.Source.WALKIN, self.cre, False, False),
            ("Yesterday", Lead.Source.WALKIN, self.receptionist, True, False),
            ("Deleted", Lead.Source.WALKIN, self.receptionist, False, True),
        ]:
            lead = Lead.objects.create(name=name, phone="9876543210", source=source, branch="Kochi", assigned_ps=self.so, deleted_at=timezone.now() if deleted else None)
            audit = LeadAudit.objects.create(lead=lead, actor=actor, event="created")
            if old:
                LeadAudit.objects.filter(pk=audit.pk).update(created_at=timezone.now() - timedelta(days=1))
        self.client.force_authenticate(self.receptionist)
        response = self.client.get("/api/analytics/receptionist/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["total"], 1)
        self.assertEqual(response.data["summary"]["walkin"], 1)
        self.assertEqual(response.data["summary"]["digital"], 0)
        self.assertEqual(response.data["summary"]["etbr_enquired"], 1)
        self.assertEqual(sum(row["count"] for row in response.data["so_breakdown"]), 1)
        self.assertTrue(Lead.objects.filter(name="Digital", source=Lead.Source.META).exists())
