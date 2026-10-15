import csv
import io
from datetime import timedelta

from django.core.cache import caches
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import CallLog, FollowUp, Lead, LeadAudit


class CEPerformanceTests(TestCase):
    def setUp(self):
        caches["analytics"].clear()
        self.client = APIClient()
        self.admin = User.objects.create_user(email="ce-report-admin@example.com", role="ADMIN")
        self.ceo = User.objects.create_user(email="ce-report-ceo@example.com", role="CEO")
        self.ce = User.objects.create_user(email="ce-report@example.com", role="CRE", location="Kochi")
        self.other = User.objects.create_user(email="other-ce@example.com", role="CRE", location="Aluva")
        self.ps = User.objects.create_user(email="ce-report-ps@example.com", role="SO", location="Kochi")
        self.client.force_authenticate(self.admin)

    def lead(self, **kwargs):
        return Lead.objects.create(**{
            "name": "CE report customer", "phone": "9876501000", "source": "Meta", "branch": "Kochi",
            "assigned_so": self.ce, "assigned_ps": None, "status": "FRESH",
            "enquiry_date": timezone.localdate() - timedelta(days=60), **kwargs,
        })

    def report(self, query="range=all"):
        response = self.client.get(f"/api/ceo/ce-performance/?{query}&refresh=1")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def row(self, data, user=None):
        return next(row for row in data["results"] if row["id"] == (user or self.ce).pk)

    def test_activity_credits_ce_after_sales_and_reassignment(self):
        lead = self.lead()
        for _ in range(2):
            CallLog.objects.create(lead=lead, so=self.ce, status="QUALIFIED", outcome="QUALIFIED")
            LeadAudit.objects.create(lead=lead, actor=self.ce, event="assigned_ps", after={"assigned_ps": self.ps.pk})
        pending = self.lead()
        CallLog.objects.create(lead=pending, so=self.ce, status="PENDING", outcome="RNR")
        CallLog.objects.create(lead=lead, so=self.ps, status="BOOKED", outcome="Booking Done")
        LeadAudit.objects.create(lead=pending, actor=self.admin, event="assigned_ps", after={"assigned_ps": self.ps.pk})
        lead.assigned_so = self.other
        lead.assigned_ps = self.ps
        lead.status = "BOOKED"
        lead.save()
        data = self.report("range=today")
        row = self.row(data)
        self.assertEqual((row["calls"], row["called"], row["qualified"], row["handoffs"]), (3, 2, 1, 1))
        self.assertEqual(row["qualification_rate"], 50)
        self.assertEqual(row["assigned"], 1)
        self.assertEqual(self.row(data, self.other)["assigned"], 1)
        self.assertIsNone(self.row(data, self.other)["qualification_rate"])
        self.assertNotIn("booked", row)
        self.assertNotIn("retailed", row)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.report("range=today")["results"], data["results"])

    def test_untouched_uses_ce_actions_since_allocation_not_ps_actions(self):
        lead = self.lead(assigned_ps=self.ps)
        CallLog.objects.create(lead=lead, so=self.ce, status="PENDING")
        LeadAudit.objects.create(lead=lead, actor=self.admin, event="assigned_cre", after={"assigned_so": self.ce.pk})
        CallLog.objects.create(lead=lead, so=self.ps, status="PENDING")
        self.assertEqual(self.row(self.report())["untouched"], 1)
        LeadAudit.objects.create(lead=lead, actor=self.ce, event="details_updated")
        self.assertEqual(self.row(self.report())["untouched"], 0)

    def test_followups_are_distinct_current_ce_work_only(self):
        past = timezone.now() - timedelta(days=2)
        today = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        overdue = self.lead(assigned_ps=self.ps)
        for _ in range(2):
            FollowUp.objects.create(lead=overdue, so=self.ce, scheduled_for=past)
        FollowUp.objects.create(lead=overdue, so=self.ce, scheduled_for=today)
        excluded = self.lead(assigned_ps=self.ps)
        for values in ({"so": self.ps}, {"so": self.other}, {"reminder_held": True}, {"resolved_at": timezone.now()}, {"origin": "INBOUND"}):
            FollowUp.objects.create(lead=excluded, **{"so": self.ce, "scheduled_for": past, **values})
        closed = self.lead(status="LOST")
        FollowUp.objects.create(lead=closed, so=self.ce, scheduled_for=past)
        future = self.lead()
        FollowUp.objects.create(lead=future, so=self.ce, scheduled_for=timezone.now() + timedelta(days=1))
        row = self.row(self.report("range=today"))
        self.assertEqual((row["overdue"], row["due_today"]), (1, 1))
        self.assertEqual((row["assigned"], row["awaiting_ps"]), (4, 1))

    def test_period_branch_employee_and_deleted_lead_filters(self):
        lead = self.lead()
        old = CallLog.objects.create(lead=lead, so=self.ce, status="QUALIFIED")
        CallLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=5))
        CallLog.objects.create(lead=lead, so=self.ce, status="PENDING")
        deleted = self.lead(deleted_at=timezone.now())
        CallLog.objects.create(lead=deleted, so=self.ce, status="QUALIFIED")
        other = self.lead(branch="Aluva", assigned_so=self.other)
        CallLog.objects.create(lead=other, so=self.other, status="QUALIFIED")
        data = self.report(f"range=today&branch=%20KOCHI%20&employee={self.ce.pk}")
        self.assertEqual(len(data["results"]), 1)
        row = self.row(data)
        self.assertEqual((row["assigned"], row["calls"], row["qualified"]), (1, 1, 0))
        row = self.row(self.report("range=all&branch=kochi"))
        self.assertEqual((row["calls"], row["qualified"], row["qualification_rate"]), (2, 1, 100))
        response = self.client.get("/api/ceo/ce-performance/?range=custom&date_from=bad&refresh=1")
        self.assertEqual(response.status_code, 400)

    def test_permissions_and_export_match_report(self):
        lead = self.lead()
        CallLog.objects.create(lead=lead, so=self.ce, status="QUALIFIED")
        expected = self.row(self.report())
        response = self.client.get("/api/ceo/export/ce-performance/?range=all")
        self.assertEqual(response.status_code, 200)
        lines = list(csv.reader(io.StringIO(b"".join(response.streaming_content).decode("utf-8-sig"))))
        rows = [dict(zip(lines[2], row)) for row in lines[3:]]
        exported = next(row for row in rows if row["id"] == str(self.ce.pk))
        self.assertEqual(int(exported["calls"]), expected["calls"])
        self.assertEqual(float(exported["qualification_rate"]), 100)
        for user in (self.ce, self.ps, User.objects.create_user(email="ce-report-sm@example.com", role="SALES_MANAGER")):
            self.client.force_authenticate(user)
            for path in ("ce-performance", "export/ce-performance"):
                self.assertEqual(self.client.get(f"/api/ceo/{path}/").status_code, 403)

    def test_deleted_test_accounts_are_hidden_but_real_former_staff_remain(self):
        hidden = User.objects.create_user(
            email="deleted-test-ce@example.com", role="CRE", first_name="testCE",
            is_active=False, deleted_at=timezone.now(),
        )
        former = User.objects.create_user(
            email="former-ce@example.com", role="CRE", first_name="Minjumol", last_name="M",
            is_active=False, deleted_at=timezone.now(),
        )

        data = self.report()
        ids = {row["id"] for row in data["results"]}
        self.assertNotIn(hidden.pk, ids)
        self.assertIn(former.pk, ids)
