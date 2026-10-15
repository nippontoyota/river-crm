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

    def assert_balanced(self, data):
        for row in [*data["results"], data["summary"]]:
            self.assertEqual(row["assigned"], sum(row[key] for key in ("untouched", "qualified", "lost", "in_progress")))

    def test_activity_credits_ce_after_sales_and_reassignment(self):
        lead = self.lead()
        for _ in range(2):
            CallLog.objects.create(lead=lead, so=self.ce, status="QUALIFIED", outcome="QUALIFIED")
            LeadAudit.objects.create(lead=lead, actor=self.ce, event="assigned_ps", after={"assigned_ps": self.ps.pk})
        pending = self.lead()
        CallLog.objects.create(lead=pending, so=self.ce, status="PENDING", outcome="RNR")
        CallLog.objects.create(lead=lead, so=self.ps, status="BOOKED", outcome="Booking Done")
        LeadAudit.objects.create(lead=pending, actor=self.admin, event="assigned_ps", after={"assigned_ps": self.ps.pk})
        lead.assigned_ps = self.ps
        lead.status = "BOOKED"
        lead.save()
        data = self.report()
        row = self.row(data)
        self.assertEqual((row["calls"], row["called"], row["qualified"], row["handoffs"]), (3, 2, 1, 1))
        self.assertEqual(row["qualification_rate"], 50)
        self.assertEqual(row["assigned"], 2)
        self.assertEqual(row["in_progress"], 1)
        self.assert_balanced(data)
        self.assertIsNone(self.row(data, self.other)["qualification_rate"])
        self.assertNotIn("booked", row)
        self.assertNotIn("retailed", row)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.report()["results"], data["results"])
        lead.assigned_so = self.other
        lead.save()
        data = self.report()
        self.assertEqual(self.row(data)["qualified"], 0)
        self.assertEqual(self.row(data, self.other)["untouched"], 1)
        self.assert_balanced(data)

    def test_untouched_uses_ce_actions_since_allocation_not_ps_actions(self):
        lead = self.lead(assigned_ps=self.ps)
        CallLog.objects.create(lead=lead, so=self.ce, status="PENDING")
        LeadAudit.objects.create(lead=lead, actor=self.admin, event="assigned_cre", after={"assigned_so": self.ce.pk})
        CallLog.objects.create(lead=lead, so=self.ps, status="PENDING")
        self.assertEqual(self.row(self.report())["untouched"], 1)
        LeadAudit.objects.create(lead=lead, actor=self.ce, event="details_updated")
        data = self.report()
        self.assertEqual(self.row(data)["untouched"], 0)
        self.assertEqual(self.row(data)["in_progress"], 1)
        self.assert_balanced(data)

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
        row = self.row(self.report())
        self.assertEqual((row["overdue"], row["due_today"]), (1, 1))
        self.assertEqual((row["assigned"], row["awaiting_ps"]), (4, 1))
        self.assertEqual(row["followups"], 2)
        for metric in ("followups", "due_today", "overdue", "awaiting_ps"):
            response = self.client.get(f"/api/ceo/leads/?range=all&role=CRE&employee={self.ce.pk}&ce_metric={metric}&refresh=1")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["count"], row[metric])
            self.assertEqual(len({item["id"] for item in response.data["results"]}), row[metric])

    def test_period_branch_employee_and_deleted_lead_filters(self):
        lead = self.lead(enquiry_date=timezone.localdate())
        CallLog.objects.create(lead=lead, so=self.ce, status="PENDING")
        older = self.lead()
        CallLog.objects.create(lead=older, so=self.ce, status="QUALIFIED")
        deleted = self.lead(deleted_at=timezone.now())
        CallLog.objects.create(lead=deleted, so=self.ce, status="QUALIFIED")
        other = self.lead(branch="Aluva", assigned_so=self.other)
        CallLog.objects.create(lead=other, so=self.other, status="QUALIFIED")
        data = self.report(f"range=today&branch=%20KOCHI%20&employee={self.ce.pk}")
        self.assertEqual(len(data["results"]), 1)
        row = self.row(data)
        self.assertEqual((row["assigned"], row["calls"], row["qualified"]), (1, 1, 0))
        row = self.row(self.report("range=all&branch=kochi"))
        self.assertEqual((row["assigned"], row["calls"], row["qualified"], row["qualification_rate"]), (2, 2, 1, 50))
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
            email="deleted-test-ce@example.com", role="CRE", first_name="  TESTce ",
            is_active=False, deleted_at=timezone.now(),
        )
        former = User.objects.create_user(
            email="former-ce@example.com", role="CRE", first_name="Minjumol", last_name="M",
            is_active=False, deleted_at=timezone.now(),
        )
        hidden_ps = User.objects.create_user(
            email="deleted-test-ps@example.com", role="SO", first_name="testso", last_name="testso",
            is_active=False, deleted_at=timezone.now(),
        )

        data = self.report()
        ids = {row["id"] for row in data["results"]}
        self.assertNotIn(hidden.pk, ids)
        self.assertIn(former.pk, ids)
        options = self.client.get("/api/ceo/options/").data
        self.assertNotIn(hidden.pk, {row["id"] for row in options["employees"]})
        self.assertNotIn(hidden_ps.pk, {row["id"] for row in options["employees"]})
        admin = self.client.get("/api/analytics/admin/?refresh=1").data
        self.assertNotIn(hidden.pk, {row["id"] for row in admin["cre"]})
        self.assertNotIn(hidden_ps.pk, {row["id"] for row in admin["officers"]})
        people = self.client.get("/api/ceo/people/?range=all&refresh=1").data
        self.assertTrue({hidden.pk, hidden_ps.pk}.isdisjoint(row["id"] for row in people["results"]))

    def test_latest_ce_result_is_exclusive_and_ignores_ps_outcomes(self):
        untouched = self.lead()
        CallLog.objects.create(lead=untouched, so=self.ps, status="QUALIFIED")
        qualified = self.lead(status="LOST", assigned_ps=self.ps)
        CallLog.objects.create(lead=qualified, so=self.ce, status="QUALIFIED")
        CallLog.objects.create(lead=qualified, so=self.ps, status="LOST")
        lost = self.lead(status="LOST")
        CallLog.objects.create(lead=lost, so=self.ce, status="QUALIFIED")
        CallLog.objects.create(lead=lost, so=self.ce, status="LOST")
        uninterested = self.lead(status="UNQUALIFIED")
        CallLog.objects.create(lead=uninterested, so=self.ce, status="UNQUALIFIED")
        pending = self.lead()
        for _ in range(2):
            CallLog.objects.create(lead=pending, so=self.ce, status="PENDING", outcome="RNR")
        data = self.report()
        row = self.row(data)
        self.assertEqual(tuple(row[key] for key in ("assigned", "untouched", "qualified", "lost", "in_progress")), (5, 1, 1, 2, 1))
        self.assert_balanced(data)

        expected = {
            "assigned": {untouched.pk, qualified.pk, lost.pk, uninterested.pk, pending.pk},
            "untouched": {untouched.pk}, "qualified": {qualified.pk},
            "lost": {lost.pk, uninterested.pk}, "in_progress": {pending.pk},
            "calls": {qualified.pk, lost.pk, uninterested.pk, pending.pk},
        }
        for user in (self.admin, self.ceo):
            self.client.force_authenticate(user)
            for metric, ids in expected.items():
                response = self.client.get(f"/api/ceo/leads/?range=all&role=CRE&ce_metric={metric}&refresh=1")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["count"], len(ids))
                self.assertEqual({lead["id"] for lead in response.data["results"]}, ids)

    def test_ce_audit_outcomes_and_details_updates(self):
        lead = self.lead()
        CallLog.objects.create(lead=lead, so=self.ce, status="PENDING")
        LeadAudit.objects.create(lead=lead, actor=self.ce, event="so_updated", before={"status": "PENDING"}, after={"status": "QUALIFIED"})
        # A details-only CE edit must not copy a later PS outcome into CE results.
        LeadAudit.objects.create(lead=lead, actor=self.ce, event="so_updated", before={"status": "BOOKED"}, after={"status": "BOOKED"})
        self.assertEqual(self.row(self.report())["qualified"], 1)
        LeadAudit.objects.create(lead=lead, actor=self.ce, event="status_changed", after={"status": "LOST"})
        self.assertEqual(self.row(self.report())["lost"], 1)
        CallLog.objects.create(lead=lead, so=self.ce, status="QUALIFIED")
        self.assertEqual(self.row(self.report())["qualified"], 1)
        LeadAudit.objects.create(lead=lead, actor=self.admin, event="assigned_cre", after={"assigned_so": self.ce.pk})
        data = self.report()
        self.assertEqual(self.row(data)["untouched"], 1)
        self.assertEqual(self.row(data)["calls"], 0)
        self.assert_balanced(data)

    def test_drilldown_preserves_filters_pagination_export_and_history_access(self):
        lead = self.lead(name="Matching customer", enquiry_date=timezone.localdate())
        CallLog.objects.create(lead=lead, so=self.ce, status="QUALIFIED", remarks="Customer qualification history")
        self.lead(enquiry_date=timezone.localdate())
        self.lead(assigned_so=self.other, enquiry_date=timezone.localdate())
        self.lead(assigned_so=None, enquiry_date=timezone.localdate())
        self.lead(branch="Aluva", enquiry_date=timezone.localdate())
        self.lead(deleted_at=timezone.now(), enquiry_date=timezone.localdate())
        self.lead()  # Older enquiry excluded by the selected enquiry period.
        hidden = User.objects.create_user("hidden-drilldown@example.com", role="CRE", first_name="testCE", deleted_at=timezone.now(), is_active=False)
        self.lead(assigned_so=hidden, enquiry_date=timezone.localdate())
        query = f"range=today&role=CRE&branch=kochi&employee={self.ce.pk}&ce_metric=assigned&refresh=1"
        for user in (self.admin, self.ceo):
            self.client.force_authenticate(user)
            first = self.client.get(f"/api/ceo/leads/?{query}&page_size=1")
            self.assertEqual(first.status_code, 200)
            self.assertEqual(first.data["count"], 2)
            second = self.client.get(f"/api/ceo/leads/?{query}&page_size=1&page=2")
            self.assertNotEqual(first.data["results"][0]["id"], second.data["results"][0]["id"])
            filtered = self.client.get(f"/api/ceo/leads/?{query}&q=Matching")
            self.assertEqual([row["id"] for row in filtered.data["results"]], [lead.pk])
            total = self.client.get("/api/ceo/leads/?range=today&role=CRE&branch=kochi&ce_metric=assigned&refresh=1")
            self.assertEqual(total.data["count"], 3)
            detail = self.client.get(f"/api/ceo/leads/{lead.pk}/")
            self.assertEqual(detail.status_code, 200)
            history = self.client.get(f"/api/ceo/leads/{lead.pk}/history/?kind=call")
            self.assertEqual(history.status_code, 200)
            self.assertIn("Customer qualification history", str(history.data))
            exported = self.client.get(f"/api/ceo/export/leads/?{query}&q=Matching")
            self.assertEqual(exported.status_code, 200)
            lines = list(csv.reader(io.StringIO(b"".join(exported.streaming_content).decode("utf-8-sig"))))
            rows = [dict(zip(lines[2], values)) for values in lines[3:]]
            self.assertEqual([row["id"] for row in rows], [str(lead.pk)])
        invalid = self.client.get("/api/ceo/leads/?ce_metric=invalid&refresh=1")
        self.assertEqual(invalid.status_code, 400)
        self.client.force_authenticate(self.ce)
        self.assertEqual(self.client.get(f"/api/ceo/leads/?{query}").status_code, 403)
