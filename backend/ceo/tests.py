from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.core.cache import caches
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from accounts.models import User
from complaints.models import Complaint
from leads.models import CallLog, FollowUp, Lead, LeadAudit, SystemConfig
from .models import FinancialEntry, Milestone, OperationEvent, SaleAccount, SalesTarget
from .tracking import milestone


class CEOTests(TestCase):
    def setUp(self):
        caches["default"].clear()
        self.enterContext(patch("rest_framework.views.APIView.throttle_classes", []))
        self.client = APIClient()
        self.admin = User.objects.create_user(email="ceo-admin@example.com", role="ADMIN")
        self.ceo = User.objects.create_user(email="ceo@example.com", role="CEO")
        self.so = User.objects.create_user(email="ceo-so@example.com", role="SO", location="Kochi")
        self.cre = User.objects.create_user(email="ceo-ce@example.com", role="CRE", location="Kochi")
        self.reception = User.objects.create_user(email="ceo-reception@example.com", role="RECEPTIONIST", location="Kochi")
        self.manager = User.objects.create_user(email="ceo-manager@example.com", role="SALES_MANAGER", location="Kochi")
        SystemConfig.objects.update_or_create(pk=1, defaults={"lists": {"branches": ["Kochi", "Thrissur"], "models": ["Indie"], "sources": ["WALKIN"]}})
        self.lead = Lead.objects.create(name="CEO test", phone="9876543210", source="WALKIN", branch=" Kochi ", rto="KL-07", model_interest="Indie", enquiry_date=timezone.localdate(), assigned_ps=self.so, assigned_so=self.cre, status="QUALIFIED")
        LeadAudit.objects.create(lead=self.lead, actor=self.reception, event="created")
        self.auth(self.ceo)

    def auth(self, user):
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

    def get(self, section, query="range=all"):
        return self.client.get(f"/api/ceo/{section}/?{query}")

    def finance(self, **values):
        return self.client.post("/api/management/finance/", {"lead": self.lead.id, "kind": "PAYMENT", "amount": "100.00", "occurred_on": timezone.localdate().isoformat(), "method": "BANK", "notes": "Recorded for test", "idempotency_key": str(uuid4()), **values}, format="json")

    def test_ceo_read_only_across_business_endpoints(self):
        for method, path, data in [("patch", f"/api/leads/{self.lead.id}/", {"name": "Changed"}),
            ("patch", f"/api/leads/{self.lead.id}/so-update/", {"name": "Changed"}),
            ("post", f"/api/leads/{self.lead.id}/complete-test-drive/", {}),
            ("post", "/api/auth/users/", {}), ("post", "/api/management/targets/", {}),
            ("post", "/api/management/finance/", {}), ("post", "/api/complaints/", {}),
            ("patch", "/api/system-config/", {"lists": {}})]:
            with self.subTest(path=path):
                self.assertEqual(getattr(self.client, method)(path, data, format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/auth/logout/").status_code, 204)
        for role in [self.cre, self.so, self.reception, self.manager]:
            self.auth(role)
            self.assertEqual(self.get("overview").status_code, 403)

    def test_reports_and_drilldowns_reconcile(self):
        for kind in "TBR":
            milestone(self.lead, kind, self.so)
        other = Lead.objects.create(name="Other", phone="9876543211", enquiry_date=timezone.localdate(), branch="Thrissur")
        LeadAudit.objects.create(lead=other, actor=self.admin, event="created")
        response = self.get("overview")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["etbr"], {"E": 2, "T": 1, "B": 1, "R": 1})
        self.assertEqual(sum(row["E"] for row in response.data["branches"]), 2)
        for section in ["branches", "people", "leads", "segments", "finance", "complaints", "options"]:
            result = self.get(section)
            self.assertEqual(result.status_code, 200, (section, getattr(result, "data", None)))
        for kind in "ETBR":
            self.assertEqual(self.get("leads", f"range=all&branch=kochi&metric={kind}").data["count"], 1)
        self.assertEqual(self.get("overview", "range=all&branch=kochi").data["etbr"]["E"], 1)
        self.assertEqual(self.get("overview", "range=all&branch=kochi&branch=thrissur").data["etbr"]["E"], 2)

    def test_milestones_survive_followups_reassignment_and_cancellation(self):
        self.auth(self.so)
        base = {"call_status": "Connected", "remarks": "Customer agreed"}
        result = self.client.patch(f"/api/leads/{self.lead.id}/so-update/", {**base, "call_outcome": "Booking Done", "follow_up_at": (timezone.now() + timedelta(days=1)).isoformat()}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        old = Milestone.objects.get(lead=self.lead, kind="B")
        result = self.client.patch(f"/api/leads/{self.lead.id}/so-update/", {**base, "call_outcome": "Not Interested"}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(Milestone.objects.filter(lead=self.lead, kind="B").count(), 1)
        self.assertEqual(OperationEvent.objects.filter(lead=self.lead, kind="booking_cancelled").count(), 1)
        self.assertEqual(OperationEvent.objects.filter(lead=self.lead, kind="followup_resolved").count(), 1)
        replacement = User.objects.create_user(email="replacement-ceo-so@example.com", role="SO", location="Thrissur")
        Lead.objects.filter(pk=self.lead.pk).update(assigned_ps=replacement, branch="Thrissur")
        old.refresh_from_db()
        self.assertEqual((old.branch, old.so_id), ("kochi", self.so.pk))
        self.auth(self.ceo)
        self.assertEqual(self.get("overview", f"range=all&employee={self.so.pk}").data["etbr"]["B"], 1)

    def test_cohort_rates_do_not_assume_skipped_stages(self):
        milestone(self.lead, "R", self.so)
        result = self.get("overview").data
        self.assertEqual(result["conversions"]["E_R"], 100)
        self.assertIsNone(result["conversions"]["B_R"])
        self.assertIsNone(result["conversions"]["T_B"])

    def test_history_pagination_has_no_thirty_event_cap(self):
        for number in range(40):
            LeadAudit.objects.create(lead=self.lead, actor=self.admin, event="details_updated", after={"campaign": str(number)})
        first = self.get(f"leads/{self.lead.pk}/history", "page_size=25&order=oldest")
        second = self.get(f"leads/{self.lead.pk}/history", "page_size=25&page=2&order=oldest")
        self.assertEqual(first.data["count"], 41)
        self.assertEqual(len(second.data["results"]), 16)
        self.assertEqual(first.data["results"][0]["kind"], "created")

    def test_bulk_assignments_and_calls_are_tracked(self):
        LeadAudit.objects.bulk_create([LeadAudit(lead=self.lead, actor=self.admin, event="assigned_ps", after={"assigned_ps": self.so.id})])
        CallLog.objects.create(lead=self.lead, so=self.cre, call_status="Not Connected", outcome="RNR", status="PENDING")
        self.assertTrue(OperationEvent.objects.filter(kind="assigned_ps").exists())
        people = self.get("people").data["results"]
        row = next(row for row in people if row["id"] == self.cre.id)
        self.assertEqual((row["calls"], row["connected"]), (1, 0))
        self.assertFalse(any(row["id"] in [self.admin.id, self.ceo.id] for row in people))

    def test_money_payments_refunds_reversals_and_idempotency(self):
        self.auth(self.admin)
        value = self.finance(kind="VALUATION", agreed_amount="1000.00", retail_amount="1000.00", confirmed_on=timezone.localdate().isoformat())
        self.assertEqual(value.status_code, 200, value.data)
        key = str(uuid4())
        payment = self.finance(amount="600.00", idempotency_key=key)
        self.assertEqual(payment.status_code, 200, payment.data)
        replay = self.finance(amount="600.00", idempotency_key=key)
        self.assertEqual(replay.data["id"], payment.data["id"])
        self.assertEqual(self.finance(amount="700.00", idempotency_key=key).status_code, 400)
        refund = self.finance(kind="REFUND", amount="200.00")
        self.assertEqual(refund.status_code, 200, refund.data)
        self.assertEqual(self.finance(kind="REFUND", amount="401.00").status_code, 400)
        reversed_refund = self.finance(kind="REVERSAL", reverses=refund.data["id"])
        self.assertEqual(reversed_refund.status_code, 200, reversed_refund.data)
        self.assertEqual(self.finance(kind="REVERSAL", reverses=refund.data["id"]).status_code, 400)
        self.lead.status, self.lead.sales_outcome = "WON", "RETAILED"
        self.lead.save()
        milestone(self.lead, "R", self.so)
        self.auth(self.ceo)
        summary = self.get("finance").data["summary"]
        self.assertEqual(Decimal(str(summary["net_collections"])), Decimal("600"))
        self.assertEqual(Decimal(str(summary["outstanding"])), Decimal("400"))
        self.assertEqual(Decimal(str(summary["retail_value"])), Decimal("1000"))
        self.assertEqual(self.get(f"leads/{self.lead.pk}").status_code, 200)

    def test_targets_and_revisions(self):
        self.auth(self.admin)
        data = {"month": timezone.localdate().replace(day=1).isoformat(), "branch": "KOCHI", "so": None,
                "enquiries": 100, "test_drives": 50, "bookings": 30, "retails": 20, "retail_value": "100000.00"}
        response = self.client.post("/api/management/targets/", data, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.post("/api/management/targets/", {**data, "so": self.so.pk, "retails": 21}, format="json").status_code, 200)
        self.auth(self.ceo)
        target = self.get("overview", "range=mtd&branch=kochi").data["targets"]
        self.assertTrue(target["available"])
        self.assertEqual(target["allocation_gap"]["retails"], -1)
        self.assertFalse(self.get("overview", "range=today").data["targets"]["available"])
        self.assertEqual(self.get(f"targets/{response.data['id']}/history").data["count"], 1)

    def test_invalid_filters_and_csv_formula_safety(self):
        self.assertEqual(self.get("overview", "range=custom&date_from=no&date_to=2026-01-01").status_code, 400)
        self.assertEqual(self.get("overview", "range=custom&date_from=2026-02-30&date_to=2026-03-01").status_code, 400)
        self.assertEqual(self.get("overview", "metric=ET").status_code, 400)
        Lead.objects.filter(pk=self.lead.pk).update(name="=HYPERLINK(1)")
        response = self.get("export/leads")
        self.assertEqual(response.status_code, 200)
        csv_text = b"".join(response.streaming_content).decode()
        self.assertIn("'=HYPERLINK(1)", csv_text)
        self.assertIn("Asia/Kolkata", csv_text)

    def test_backdated_refund_cannot_precede_available_payments(self):
        self.auth(self.admin)
        payment = self.finance(amount="500.00")
        self.assertEqual(payment.status_code, 200)
        response = self.finance(kind="REFUND", amount="100.00", occurred_on=(timezone.localdate() - timedelta(days=1)).isoformat())
        self.assertEqual(response.status_code, 400, response.data)
        self.assertEqual(FinancialEntry.objects.count(), 1)

    def test_age_bands_and_history_exports_reconcile(self):
        Lead.objects.filter(pk=self.lead.pk).update(enquiry_date=timezone.localdate() - timedelta(days=10))
        summary = self.get("overview").data
        self.assertEqual(summary["ageing"]["8_14"], 1)
        self.assertEqual(sum(summary["ageing"].values()), summary["current"]["active"])
        self.assertEqual(self.get("leads", "range=today&scope=workload&age=8_14").data["count"], 1)
        CallLog.objects.create(lead=self.lead, so=self.so, call_status="Connected", remarks="Unique call history marker")
        export = self.get("export/history", f"lead={self.lead.pk}&kind=call&order=oldest")
        content = b"".join(export.streaming_content).decode()
        self.assertIn("Unique call history marker", content)
        self.assertNotIn('"source":', content)
        self.assertEqual(self.get(f"leads/{self.lead.pk}/history", "kind=call").data["count"], 1)

    def test_legacy_backfill_never_infers_historical_owners_or_skipped_milestones(self):
        from django.db import connection
        from importlib import import_module
        legacy = Lead.objects.create(name="Legacy retail", phone="9876543299", branch="Kochi", assigned_ps=self.so,
            status="WON", sales_outcome="RETAILED", enquiry_date=timezone.localdate())
        # Historical model instances bypass the runtime audit signal, as during migrations.
        from django.db.migrations.executor import MigrationExecutor
        state = MigrationExecutor(connection).loader.project_state([("ceo", "0001_initial")]).apps
        audit_model = state.get_model("leads", "LeadAudit")
        audit_model.objects.create(lead_id=legacy.pk, actor_id=self.so.pk, event="so_updated", before={"status": "QUALIFIED"}, after={"status": "WON"})
        module = import_module("ceo.migrations.0002_backfill_verified_history")
        from types import SimpleNamespace
        module.backfill(state, SimpleNamespace(connection=connection))
        self.assertEqual(set(legacy.milestones.values_list("kind", flat=True)), {"E", "R"})
        retail = legacy.milestones.get(kind="R")
        self.assertEqual(retail.branch, "")
        self.assertIsNone(retail.so_id)
        self.assertIsNotNone(retail.occurred_at)
        module.backfill(state, SimpleNamespace(connection=connection))
        self.assertEqual(legacy.milestones.count(), 2)

    def test_people_query_count_does_not_grow_per_employee(self):
        from django.db import connection
        from django.http import QueryDict
        from django.test.utils import CaptureQueriesContext
        from .filters import ReportFilters
        from .reporting import people_rows
        filters = ReportFilters(QueryDict("range=all"))
        with CaptureQueriesContext(connection) as small:
            people_rows(filters, [self.so])
        people = [self.so] + [User.objects.create_user(email=f"ceo-extra-{i}@example.com", role="SO") for i in range(30)]
        with CaptureQueriesContext(connection) as large:
            people_rows(filters, people)
        self.assertLessEqual(len(large), len(small) + 1)

    def test_manager_and_receptionist_results_use_their_respective_scopes(self):
        milestone(self.lead, "T", self.so)
        rows = self.get("people").data["results"]
        manager = next(row for row in rows if row["id"] == self.manager.id)
        intake = next(row for row in rows if row["id"] == self.reception.id)
        self.assertEqual((manager["performance_scope"], manager["assigned"], manager["T"]), ("branch", 1, 1))
        self.assertEqual((intake["performance_scope"], intake["captured"], intake["T"]), ("captured", 1, 1))
