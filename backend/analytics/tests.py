import time
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import caches
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import CallLog, FollowUp, Lead, LeadQualification

cache = caches["analytics"]


class SalesManagerAnalyticsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(email="admin@example.com", password="password-12345", role=User.Role.ADMIN)
        self.manager = User.objects.create_user(email="manager@example.com", password="password-12345", role=User.Role.SALES_MANAGER, location="Mount Road")
        self.other_manager = User.objects.create_user(email="other-manager@example.com", password="password-12345", role=User.Role.SALES_MANAGER, location="Other")
        self.cre = User.objects.create_user(email="cre@example.com", password="password-12345", role=User.Role.CRE, first_name="Asha")
        self.ps = User.objects.create_user(email="ps@example.com", password="password-12345", role=User.Role.SALES_OFFICER, first_name="Ravi", location="Mount Road")
        today = timezone.localdate()
        self.branch_lead = Lead.objects.create(name="Branch lead", phone="9000000001", branch="Mount Road", enquiry_date=today, assigned_so=self.cre, status=Lead.Status.QUALIFIED, assigned_ps=self.ps)
        self.retailed = Lead.objects.create(name="Retailed lead", phone="9000000002", branch="Mount Road", enquiry_date=today, assigned_so=self.cre, assigned_ps=self.ps, status=Lead.Status.WON, sales_outcome=Lead.SalesOutcome.RETAILED)
        self.other_branch_lead = Lead.objects.create(name="Other lead", phone="9000000003", branch="Other", enquiry_date=today, status=Lead.Status.WON, sales_outcome=Lead.SalesOutcome.RETAILED)
        CallLog.objects.create(lead=self.retailed, so=self.ps, status=Lead.Status.WON, outcome="Retail Done")

    def test_sales_manager_analytics_are_scoped_to_manager_branch(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get("/api/analytics/sales-manager/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["branch"], "Mount Road")
        self.assertEqual(response.data["summary"]["total"], 2)
        self.assertEqual(response.data["summary"]["retailed"], 1)
        self.assertEqual(response.data["summary"]["lead_to_retail_rate"], 50.0)
        self.assertIn("untouched", response.data["summary"]["delta"])
        self.assertNotIn("Other", {row["model"] for row in response.data["models"]})

        today = self.client.get("/api/analytics/sales-manager/?range=today")
        self.assertEqual(today.data["summary"]["delta"], {})

    def test_manager_overview_query_budget_and_partial_sections(self):
        self.client.force_authenticate(self.manager)

        with self.assertNumQueries(6):
            response = self.client.get("/api/analytics/sales-manager/?include=overview,filters")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["cre"], [])
        self.assertEqual(response.data["source"], [])
        self.assertEqual(response.data["filters"]["ps"][0]["id"], self.ps.id)

        cre = self.client.get("/api/analytics/sales-manager/?include=cre")
        self.assertEqual(cre.data["cre"][0]["id"], self.cre.id)
        self.assertEqual(cre.data["ps"], [])

    def test_other_analytics_query_budgets(self):
        self.client.force_authenticate(self.admin)
        with self.assertNumQueries(4):
            admin = self.client.get("/api/analytics/admin/")

        self.client.force_authenticate(self.cre)
        with self.assertNumQueries(4):
            personal = self.client.get("/api/analytics/me/?range=mtd")

        receptionist = User.objects.create_user(email="reception@example.com", password="password-12345", role=User.Role.RECEPTIONIST)
        self.client.force_authenticate(receptionist)
        with self.assertNumQueries(2):
            reception = self.client.get("/api/analytics/receptionist/")

        self.assertEqual(admin.status_code, 200)
        self.assertEqual(personal.status_code, 200)
        self.assertEqual(reception.status_code, 200)
        self.assertEqual(admin["X-Cache"], "BYPASS")
        self.assertEqual(personal["X-Cache"], "BYPASS")
        self.assertEqual(reception["X-Cache"], "BYPASS")

    @override_settings(CACHE_TTL_SECONDS=10)
    def test_analytics_cache_hit_is_identical_and_runs_no_queries(self):
        cache.clear()
        self.client.force_authenticate(self.manager)

        first = self.client.get("/api/analytics/sales-manager/?range=all&include=overview")
        with self.assertNumQueries(0):
            second = self.client.get("/api/analytics/sales-manager/?include=overview&range=all")

        self.assertEqual(first["X-Cache"], "MISS")
        self.assertEqual(second["X-Cache"], "HIT")
        self.assertEqual(first.data, second.data)
        self.assertIn('desc="0 queries"', second["Server-Timing"])

        lead_queue = self.client.get("/api/leads/manager-leads/")
        lead_detail = self.client.get(f"/api/leads/{self.branch_lead.id}/")
        self.assertNotIn("X-Cache", lead_queue)
        self.assertNotIn("X-Cache", lead_detail)

    @override_settings(CACHE_TTL_SECONDS=10)
    def test_cache_isolated_by_user_and_filters(self):
        cache.clear()
        url = "/api/analytics/sales-manager/?range=all&include=source"
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get(url)["X-Cache"], "MISS")
        self.assertEqual(self.client.get(url)["X-Cache"], "HIT")
        self.assertEqual(
            self.client.get("/api/analytics/sales-manager/?range=today&include=source")["X-Cache"],
            "MISS",
        )
        self.assertEqual(
            self.client.get("/api/analytics/sales-manager/?range=all&include=cre")["X-Cache"],
            "MISS",
        )

        self.client.force_authenticate(self.other_manager)
        self.assertEqual(self.client.get(url)["X-Cache"], "MISS")

    @override_settings(CACHE_TTL_SECONDS=10)
    def test_cache_entry_expires_after_ten_seconds(self):
        cache.clear()
        self.client.force_authenticate(self.manager)
        url = "/api/analytics/sales-manager/?range=all&include=source"
        first = self.client.get(url)
        Lead.objects.create(name="New lead", phone="9000000099", branch="Mount Road")
        future = time.time() + 11

        with patch("django.core.cache.backends.locmem.time.time", return_value=future):
            expired = self.client.get(url)

        self.assertEqual(first["X-Cache"], "MISS")
        self.assertEqual(expired["X-Cache"], "MISS")
        self.assertEqual(expired.data["summary"]["total"], first.data["summary"]["total"] + 1)

    @override_settings(CACHE_TTL_SECONDS=10)
    def test_cache_failure_fails_open(self):
        cache.clear()
        self.client.force_authenticate(self.manager)

        with patch("analytics.cache.cache.get", side_effect=ConnectionError):
            response = self.client.get("/api/analytics/sales-manager/?range=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Cache"], "ERROR")
        self.assertEqual(response.data["summary"]["total"], 2)

    @override_settings(CACHE_TTL_SECONDS=10)
    def test_all_analytics_endpoints_are_cached(self):
        cache.clear()
        users_and_urls = [
            (self.admin, "/api/analytics/admin/"),
            (self.cre, "/api/analytics/me/?range=all"),
            (
                User.objects.create_user(
                    email="reception-cache@example.com",
                    password="password-12345",
                    role=User.Role.RECEPTIONIST,
                ),
                "/api/analytics/receptionist/",
            ),
            (self.manager, "/api/analytics/sales-manager/ps-followups/?range=all"),
        ]
        for user, url in users_and_urls:
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(url)["X-Cache"], "MISS")
            self.assertEqual(self.client.get(url)["X-Cache"], "HIT")

    def test_sales_manager_leads_are_scoped_and_read_only(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get("/api/leads/manager-leads/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual({lead["id"] for lead in response.data["results"]}, {self.branch_lead.id, self.retailed.id})

        retailed = self.client.get("/api/leads/manager-leads/?sales_outcome=RETAILED")
        self.assertEqual({lead["id"] for lead in retailed.data["results"]}, {self.retailed.id})

        detail = self.client.get(f"/api/leads/{self.other_branch_lead.id}/")
        self.assertEqual(detail.status_code, 404)

        edit = self.client.patch(f"/api/leads/{self.branch_lead.id}/", {"name": "Changed"}, format="json")
        self.assertEqual(edit.status_code, 403)
        self.branch_lead.refresh_from_db()
        self.assertEqual(self.branch_lead.name, "Branch lead")

    def test_manager_lead_person_drilldowns_combine_with_date_filters(self):
        today = timezone.localdate()
        other_cre = User.objects.create_user(email="other-cre@example.com", password="password-12345", role=User.Role.CRE)
        other_ps = User.objects.create_user(email="other-ps@example.com", password="password-12345", role=User.Role.SALES_OFFICER, location="Mount Road")
        Lead.objects.create(name="Other owners", phone="9000000004", branch="Mount Road", enquiry_date=today, assigned_so=other_cre, assigned_ps=other_ps)
        Lead.objects.create(name="Old owners", phone="9000000005", branch="Mount Road", enquiry_date=today - timedelta(days=45), assigned_so=self.cre, assigned_ps=self.ps)
        self.client.force_authenticate(self.manager)
        dates = f"date_from={today.isoformat()}&date_to={today.isoformat()}"

        cre = self.client.get(f"/api/leads/manager-leads/?cre={self.cre.id}&{dates}")
        ps = self.client.get(f"/api/leads/manager-leads/?ps={self.ps.id}&{dates}")

        expected = {self.branch_lead.id, self.retailed.id}
        self.assertEqual({lead["id"] for lead in cre.data["results"]}, expected)
        self.assertEqual({lead["id"] for lead in ps.data["results"]}, expected)

    def test_manager_lead_flagged_filter_keeps_branch_scope(self):
        self.branch_lead.flagged_to_manager = True
        self.branch_lead.save(update_fields=["flagged_to_manager"])
        self.other_branch_lead.flagged_to_manager = True
        self.other_branch_lead.save(update_fields=["flagged_to_manager"])
        self.client.force_authenticate(self.manager)

        response = self.client.get("/api/leads/manager-leads/?flagged=true")

        self.assertEqual({lead["id"] for lead in response.data["results"]}, {self.branch_lead.id})

    def test_manager_lead_overdue_filter_keeps_branch_scope(self):
        now = timezone.now()
        FollowUp.objects.create(lead=self.branch_lead, so=self.ps, scheduled_for=now - timedelta(hours=1))
        FollowUp.objects.create(lead=self.retailed, so=self.ps, scheduled_for=now - timedelta(hours=2), resolved_at=now)
        FollowUp.objects.create(lead=self.retailed, so=self.ps, scheduled_for=now + timedelta(hours=1))
        FollowUp.objects.create(lead=self.other_branch_lead, so=self.ps, scheduled_for=now - timedelta(hours=1))
        self.client.force_authenticate(self.manager)

        response = self.client.get("/api/leads/manager-leads/?followup=overdue")

        self.assertEqual({lead["id"] for lead in response.data["results"]}, {self.branch_lead.id})

    def test_manager_lead_stale_filter_uses_current_fresh_status_and_branch(self):
        stale_fresh = Lead.objects.create(name="Stale fresh", phone="9000000010", branch="Mount Road", status=Lead.Status.FRESH)
        stale_qualified = Lead.objects.create(name="Stale qualified", phone="9000000011", branch="Mount Road", status=Lead.Status.QUALIFIED)
        other_stale = Lead.objects.create(name="Other stale", phone="9000000012", branch="Other", status=Lead.Status.FRESH)
        Lead.objects.filter(id__in=[stale_fresh.id, stale_qualified.id, other_stale.id]).update(created_at=timezone.now() - timedelta(days=4))
        self.client.force_authenticate(self.manager)

        response = self.client.get("/api/leads/manager-leads/?risk=stale")

        self.assertEqual({lead["id"] for lead in response.data["results"]}, {stale_fresh.id})

    def test_historical_callback_log_does_not_match_current_callback_status(self):
        historical_callback = Lead.objects.create(name="Past callback", phone="9000000013", branch="Mount Road", status=Lead.Status.QUALIFIED)
        current_callback = Lead.objects.create(name="Current callback", phone="9000000014", branch="Mount Road", status=Lead.Status.CALLBACK)
        CallLog.objects.create(lead=historical_callback, so=self.ps, status=Lead.Status.CALLBACK, outcome="Call Me Back")
        self.client.force_authenticate(self.manager)

        response = self.client.get("/api/leads/manager-leads/?status=CALLBACK")

        self.assertEqual({lead["id"] for lead in response.data["results"]}, {current_callback.id})

    def test_manager_lead_lost_status_group_includes_lost_and_unqualified(self):
        lost = Lead.objects.create(name="Lost", phone="9000000015", branch="Mount Road", status=Lead.Status.LOST)
        unqualified = Lead.objects.create(name="Unqualified", phone="9000000016", branch="Mount Road", status=Lead.Status.UNQUALIFIED)
        Lead.objects.create(name="Other lost", phone="9000000017", branch="Other", status=Lead.Status.LOST)
        self.client.force_authenticate(self.manager)

        response = self.client.get("/api/leads/manager-leads/?status_group=lost_or_unqualified")

        self.assertEqual({lead["id"] for lead in response.data["results"]}, {lost.id, unqualified.id})

    def test_ps_followup_analytics_use_scheduled_history_and_test_drive_signals(self):
        today = timezone.localdate()
        unattended = Lead.objects.create(name="Unattended", phone="9000000020", branch="Mount Road", enquiry_date=today, assigned_ps=self.ps, category=Lead.Category.HOT)
        first = Lead.objects.create(name="First follow-up", phone="9000000021", branch="Mount Road", enquiry_date=today, assigned_ps=self.ps, category=Lead.Category.HOT)
        fifth_plus = Lead.objects.create(name="Fifth plus", phone="9000000022", branch="Mount Road", enquiry_date=today, assigned_ps=self.ps, category=Lead.Category.HOT)
        other_branch = Lead.objects.create(name="Hidden", phone="9000000023", branch="Other", enquiry_date=today, assigned_ps=self.ps, category=Lead.Category.HOT)
        now = timezone.now()
        FollowUp.objects.create(lead=first, so=self.ps, scheduled_for=now)
        for index in range(6):
            FollowUp.objects.create(lead=fifth_plus, so=self.ps, scheduled_for=now + timedelta(days=index))
        FollowUp.objects.create(lead=other_branch, so=self.ps, scheduled_for=now)
        LeadQualification.objects.create(lead=first, test_drive="Showroom visit")
        CallLog.objects.create(lead=unattended, so=self.ps, status=Lead.Status.PENDING, outcome="Need Test Drive")
        self.client.force_authenticate(self.manager)

        response = self.client.get("/api/analytics/sales-manager/ps-followups/?range=all&priority=HOT")

        self.assertEqual(response.status_code, 200)
        row = response.data["rows"][0]
        self.assertEqual(row["total_leads"], 3)
        self.assertEqual(row["test_drive"], 2)
        self.assertEqual(row["unattended"], 1)
        self.assertEqual(row["f1"], 1)
        self.assertEqual(row["f5"], 1)

        drilldown = self.client.get(f"/api/analytics/sales-manager/ps-followups/?range=all&priority=HOT&ps={self.ps.id}&bucket=f5")
        self.assertEqual([lead["id"] for lead in drilldown.data["leads"]], [fifth_plus.id])

        exported = self.client.get(f"/api/analytics/sales-manager/export/?section=ps_followups&range=all&priority=HOT&ps={self.ps.id}&bucket=test_drive")
        self.assertEqual(exported.status_code, 200)
        exported_csv = exported.content.decode()
        self.assertIn("First follow-up", exported_csv)
        self.assertIn("Unattended", exported_csv)
        self.assertIn(timezone.localtime(first.created_at).strftime("%d/%m/%Y %H:%M"), exported_csv)

    def test_non_manager_cannot_use_sales_manager_analytics(self):
        self.client.force_authenticate(self.admin)

        response = self.client.get("/api/analytics/sales-manager/")
        followups = self.client.get("/api/analytics/sales-manager/ps-followups/")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(followups.status_code, 403)
