from datetime import timedelta
from urllib.parse import urlencode

from django.http import QueryDict
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import CallLog, Lead, LeadAudit
from .filters import ReportFilters
from .lead_analysis import classified_leads, lead_analysis


class LeadAnalysisTests(TestCase):
    def setUp(self):
        self.ceo = User.objects.create_user(email="analysis-ceo@example.com", role="CEO")
        self.officer = User.objects.create_user(email="analysis-so@example.com", role="SO", first_name="Officer", location="Kochi")
        self.client = APIClient()
        self.client.force_authenticate(self.ceo)

    def lead(self, **values):
        return Lead.objects.create(name="Customer", phone="9876543210", enquiry_date=timezone.localdate(), branch="Kochi", **values)

    def call(self, lead, outcome, **values):
        return CallLog.objects.create(lead=lead, so=self.officer, status=lead.status, outcome=outcome, **values)

    def get(self, section, **values):
        return self.client.get(f"/api/ceo/{section}/", {"range": "all", "refresh": "1", **values})

    def test_latest_outcome_fallback_and_final_states(self):
        active = self.lead(status="PENDING")
        first = self.call(active, "Line Busy")
        last = self.call(active, "Need time")
        CallLog.objects.filter(pk__in=[first.pk, last.pk]).update(created_at=timezone.now())
        blank = self.lead(status="PENDING")
        self.call(blank, "RNR")
        self.call(blank, "   ")
        incompatible = self.lead(status="QUALIFIED")
        CallLog.objects.create(lead=incompatible, so=self.officer, status="RNR", outcome="RNR")
        legacy = self.lead(status="PENDING")
        self.call(legacy, "Details Received")
        booked = self.lead(status="WALKIN", sales_outcome="BOOKED")
        self.call(booked, "RNR")
        retail = self.lead(status="WON", sales_outcome="RETAILED")
        self.call(retail, "RNR")
        unqualified = self.lead(status="UNQUALIFIED")
        self.call(unqualified, "Casual Enquiry")
        fresh = self.lead()
        actual = dict(classified_leads(Lead.objects.all()).values_list("pk", "analysis_status"))
        self.assertEqual(actual, {active.pk: "Need time", blank.pk: "Pending", incompatible.pk: "Qualified", legacy.pk: "Details Received", booked.pk: "RNR", retail.pk: "Retail Done", unqualified.pk: "Unqualified", fresh.pk: "Fresh"})

    def test_reopen_ignores_old_outcomes_and_loss_reasons(self):
        lead = self.lead(status="PENDING")
        self.call(lead, "Line Busy")
        LeadAudit.objects.create(lead=lead, actor=self.officer, event="reopened")
        self.assertEqual(classified_leads(Lead.objects.all()).get().analysis_status, "Pending")
        self.call(lead, "Need time")
        self.assertEqual(classified_leads(Lead.objects.all()).get().analysis_status, "Need time")
        lead.status, lead.sales_outcome = "LOST", "LOST"
        lead.save()
        self.call(lead, "Dropped")
        LeadAudit.objects.create(lead=lead, actor=self.officer, event="reopened")
        self.assertEqual(classified_leads(Lead.objects.all()).get().loss_reason, "Reason not recorded")

    def test_generic_ce_outcomes_use_stage_labels_not_loss_reasons(self):
        for state, expected in [("PENDING", "Pending"), ("QUALIFIED", "Qualified"), ("SWITCHED_OFF", "Switch Off"), ("LOST", "Lost Lead")]:
            lead = self.lead(status=state)
            self.call(lead, state)
            record = classified_leads(Lead.objects.filter(pk=lead.pk)).get()
            self.assertEqual(record.analysis_status, expected)
            if state == "LOST":
                self.assertEqual(record.loss_reason, "Reason not recorded")

    def test_totals_drilldowns_and_export_reconcile(self):
        for state, outcome, assigned in [("PENDING", "RNR", self.officer), ("PENDING", "Line Busy", self.officer), ("LOST", "Dropped", None), ("LOST", "LOST RNR", self.officer), ("LOST", "", None), ("FRESH", "", None)]:
            lead = self.lead(status=state, assigned_ps=assigned)
            if state != "FRESH":
                self.call(lead, outcome)
        self.lead(deleted_at=timezone.now())
        analysis = self.get("overview").data["lead_analysis"]
        self.assertEqual(analysis["total"], 6)
        self.assertEqual(analysis["lost_total"], 3)
        self.assertEqual(sum(row["count"] for row in analysis["statuses"]), 6)
        self.assertEqual(sum(row["total"] for row in analysis["officers"]), 6)
        self.assertEqual(sum(row["count"] for row in analysis["loss_reasons"]), 3)
        for status in analysis["statuses"]:
            self.assertEqual(self.get("leads", analysis_status=status["key"]).data["count"], status["count"])
        for reason in analysis["loss_reasons"]:
            self.assertEqual(self.get("leads", loss_reason=reason["key"]).data["count"], reason["count"])
        for officer in analysis["officers"]:
            self.assertEqual(self.get("leads", analysis_officer=officer["key"]).data["count"], officer["total"])
            for status in analysis["statuses"]:
                self.assertEqual(self.get("leads", analysis_officer=officer["key"], analysis_status=status["key"]).data["count"], officer["statuses"].get(status["key"], 0))
        response = self.get("export/leads", analysis_status="RNR", analysis_officer=str(self.officer.pk))
        csv = b"".join(response.streaming_content).decode("utf-8-sig")
        self.assertEqual(csv.count("Customer"), 1)
        self.assertIn("analysis_status", csv)
        self.assertIn("RNR", csv)

    def test_date_branch_and_current_owner_filters(self):
        old = self.lead(assigned_ps=self.officer, status="RNR")
        Lead.objects.filter(pk=old.pk).update(enquiry_date=timezone.localdate() - timedelta(days=400))
        lead = self.lead(status="PENDING", assigned_ps=self.officer)
        self.call(lead, "Line Busy")
        self.lead()
        self.assertEqual(self.get("overview", range="mtd").data["lead_analysis"]["total"], 2)
        self.assertEqual(self.get("overview", range="all").data["lead_analysis"]["total"], 3)
        self.assertEqual(self.get("overview", branch="thrissur").data["lead_analysis"]["total"], 0)
        replacement = User.objects.create_user(email="analysis-replacement@example.com", role="SO", first_name="Officer", location="Thrissur", is_active=False)
        lead.assigned_ps = replacement
        lead.save()
        query = {"range": "today", "branch": "kochi", "mode": "period", "analysis_officer": str(replacement.pk)}
        self.assertEqual(self.get("overview", **query).data["lead_analysis"]["total"], 1)
        row = self.get("leads", **query).data["results"][0]
        self.assertEqual((row["id"], row["so_id"], row["analysis_status"]), (lead.pk, replacement.pk, "Line Busy"))
        self.assertEqual(self.get("overview", **{**query, "mode": "cohort"}).data["lead_analysis"]["total"], 1)

    def test_pagination_and_full_lifetime_history(self):
        for _ in range(26):
            self.lead(status="RNR")
        response = self.get("leads", analysis_status="RNR")
        self.assertEqual(response.data["count"], 26)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertEqual(len(self.get("leads", analysis_status="RNR", page=2).data["results"]), 1)
        lead = Lead.objects.first()
        for _ in range(27):
            self.call(lead, "RNR", remarks="Historical call")
        response = self.get(f"leads/{lead.pk}/history", range="today")
        self.assertEqual(response.data["count"], 27)
        self.assertEqual(len(self.get(f"leads/{lead.pk}/history", page=2).data["results"]), 2)

    def test_validation_permissions_and_refresh(self):
        for officer in ["bad", "-1", "0", "1" * 30]:
            self.assertEqual(self.get("leads", analysis_officer=officer).status_code, 400)
        self.assertEqual(self.get("leads", analysis_status="x" * 101).status_code, 400)
        response = self.get("overview")
        self.assertEqual(response["X-Cache"], "BYPASS")
        self.client.force_authenticate(self.officer)
        self.assertEqual(self.get("overview").status_code, 403)
        self.assertEqual(self.get("leads", analysis_status="RNR").status_code, 403)

    def test_grouping_query_count_does_not_grow_with_officers(self):
        self.lead(assigned_ps=self.officer)
        filters = ReportFilters(QueryDict(urlencode({"range": "all"})))
        with self.assertNumQueries(2):
            lead_analysis(filters)
        for number in range(3):
            officer = User.objects.create_user(email=f"analysis-{number}@example.com", role="SO")
            lead = self.lead(assigned_ps=officer, status="PENDING")
            self.call(lead, "Line Busy")
        with self.assertNumQueries(2):
            result = lead_analysis(filters)
        self.assertEqual(len(result["officers"]), 4)
