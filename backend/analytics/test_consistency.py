from datetime import timedelta
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.core.cache import caches
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import CallLog, FollowUp, Lead, LeadAudit


@override_settings(CACHE_TTL_SECONDS=60)
class DashboardConsistencyTests(TestCase):
    def setUp(self):
        caches["analytics"].clear()
        self.addCleanup(caches["analytics"].clear)
        self.enterContext(patch("leads.views.LeadViewSet.throttle_classes", []))
        self.client = APIClient()
        self.ps = User.objects.create_user(email="sync-ps@example.com", role="SO", location="Kochi")
        self.other_ps = User.objects.create_user(email="sync-other@example.com", role="SO", location="Other")
        self.manager = User.objects.create_user(email="sync-sm@example.com", role="SALES_MANAGER", location="Kochi")
        self.admin = User.objects.create_user(email="sync-admin@example.com", role="ADMIN")
        self.ceo = User.objects.create_user(email="sync-ceo@example.com", role="CEO")
        self.lead = Lead.objects.create(name="Sync customer", phone="9876500000", status="QUALIFIED", source="WALKIN", branch="Kochi", enquiry_date=timezone.localdate(), assigned_ps=self.ps)
        LeadAudit.objects.create(lead=self.lead, actor=self.ps, event="created")
        self.walkin = Lead.objects.create(name="Unbooked walk-in", phone="9876500001", status="QUALIFIED", source="WALKIN", branch="Kochi", enquiry_date=timezone.localdate(), assigned_ps=self.ps)

    def get(self, user, path):
        self.client.force_authenticate(user)
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def assert_booked(self, expected):
        for user, path in (
            (self.ps, "/api/leads/my-dashboard/?section=booked&range=all"),
            (self.ps, "/api/analytics/me/?range=all"),
            (self.manager, "/api/analytics/sales-manager/?range=all&include=filters,ps,source,lost"),
            (self.admin, "/api/analytics/admin/"),
        ):
            response = self.get(user, path)
            self.assertEqual(response.data["summary"]["booked"], expected, path)
            if "my-dashboard" in path:
                self.assertEqual(len(response.data["results"]), expected)
                self.assertEqual(response.data["summary"]["walkin"], 2)
            if "sales-manager" in path:
                row = next(row for row in response.data["ps"] if row["id"] == self.ps.pk)
                self.assertEqual(row["booked"], expected)
            if "admin" in path:
                row = next(row for row in response.data["officers"] if row["id"] == self.ps.pk)
                self.assertEqual(row["booked"], expected)
        overview = self.get(self.ceo, "/api/ceo/overview/?range=all")
        self.assertEqual(overview.data["current"]["booked"], expected)

    def test_booking_and_loss_refresh_warm_caches_for_all_roles(self):
        self.assert_booked(0)
        self.assert_booked(0)  # Warm caches before a PS writes.
        for outcome, expected in (("Already Booked", 1), ("Not Interested", 0)):
            self.client.force_authenticate(self.ps)
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {
                    "call_status": "Connected", "call_outcome": outcome,
                    "remarks": "Customer confirmed", "follow_up_at": None,
                }, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assert_booked(expected)
            self.assertEqual(self.get(self.other_ps, "/api/leads/my-dashboard/?section=booked").data["summary"]["booked"], 0)
        # Period bookings retain the actual achievement and PS attribution after a loss.
        overview = self.get(self.ceo, "/api/ceo/overview/?range=all")
        self.assertEqual(overview.data["etbr"]["B"], 1)
        self.walkin.refresh_from_db()
        self.assertEqual((self.walkin.source, self.walkin.status, self.walkin.sales_outcome), ("WALKIN", "QUALIFIED", "PENDING"))

    def test_explicit_status_save_and_legacy_repair_keep_reporting_in_step(self):
        self.lead.status = "BOOKED"
        self.lead.save(update_fields=["status"])
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.sales_outcome, "BOOKED")
        # Simulate a legacy row whose status and reporting field disagree.
        Lead.objects.filter(pk=self.lead.pk).update(sales_outcome="PENDING")
        repair = import_module("leads.migrations.0024_sync_explicit_sales_status").sync_sales_status
        for _ in range(2):
            repair(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
        self.assert_booked(1)

    def test_overdue_counts_use_current_owner_and_distinct_open_leads(self):
        past = timezone.now() - timedelta(days=40)
        for _ in range(2):
            FollowUp.objects.create(lead=self.lead, so=self.ps, scheduled_for=past)
        for values in ({"so": self.other_ps}, {"reminder_held": True}, {"resolved_at": timezone.now()}, {"origin": "INBOUND"}):
            FollowUp.objects.create(lead=self.walkin, scheduled_for=past, **{"so": self.ps, **values})
        self.assertEqual(self.get(self.ps, "/api/leads/my-dashboard/?section=missed").data["summary"]["missed"], 1)
        manager = self.get(self.manager, "/api/analytics/sales-manager/?range=mtd&include=filters,ps,source,lost")
        self.assertEqual(manager.data["summary"]["followups_due"], 1)
        self.assertEqual(manager.data["followups"]["overdue"], 1)
        self.assertEqual(self.get(self.manager, "/api/leads/manager-leads/?followup=overdue").data["count"], 1)
        self.assertEqual(self.get(self.ceo, "/api/ceo/overview/?range=all").data["current"]["overdue"], 1)
        drilldown = self.get(self.ceo, "/api/ceo/leads/?range=all&scope=workload&followup=overdue")
        self.assertEqual(drilldown.data["count"], 1)

    def test_manual_refresh_bypasses_personal_and_admin_caches(self):
        for user, path in ((self.ps, "/api/analytics/me/?range=all"), (self.admin, "/api/analytics/admin/?range=all")):
            self.assertEqual(self.get(user, path)["X-Cache"], "MISS")
            self.assertEqual(self.get(user, path)["X-Cache"], "HIT")
            self.assertEqual(self.get(user, path + "&refresh=1")["X-Cache"], "BYPASS")

    def test_untouched_means_no_recorded_action_by_the_current_ps(self):
        ce = User.objects.create_user(email="sync-ce@example.com", role="CRE")
        CallLog.objects.create(lead=self.walkin, so=ce, status="QUALIFIED")
        LeadAudit.objects.create(lead=self.walkin, actor=ce, event="assigned_ps")
        FollowUp.objects.create(lead=self.walkin, so=self.ps, scheduled_for=timezone.now() - timedelta(hours=1))

        def check(expected):
            ps = self.get(self.ps, "/api/leads/my-dashboard/?section=all").data
            manager = self.get(self.manager, "/api/analytics/sales-manager/?range=all&refresh=1").data
            workload = self.get(self.manager, "/api/analytics/sales-manager/ps-followups/?range=all&refresh=1").data
            ceo = self.get(self.ceo, "/api/ceo/overview/?range=all&refresh=1").data
            self.assertEqual(ps["summary"]["untouched"], expected)
            self.assertEqual(manager["summary"]["untouched"], expected)
            self.assertEqual(workload["rows"][0]["unattended"], expected)
            self.assertEqual(ceo["lead_analysis"]["untouched_by_ps"], expected)
            # Touching a lead alone doesn't resolve an outstanding follow-up.
            self.assertEqual(manager["followups"]["overdue"], 1)

        check(1)
        LeadAudit.objects.create(lead=self.walkin, actor=self.other_ps, event="test_drive_completed")
        check(1)
        LeadAudit.objects.create(lead=self.walkin, actor=self.ps, event="test_drive_completed")
        check(0)

    def test_walkin_is_source_only_and_legacy_repair_preserves_history(self):
        self.client.force_authenticate(self.ps)
        rejected = self.client.patch(f"/api/leads/{self.walkin.pk}/so-update/", {"status": "WALKIN"}, format="json")
        self.assertEqual(rejected.status_code, 400)
        legacy_call = CallLog.objects.create(lead=self.walkin, so=self.ps, status="WALKIN")
        Lead.objects.filter(pk=self.walkin.pk).update(status="WALKIN")
        Lead.objects.filter(pk=self.lead.pk).update(status="WALKIN", source="Meta", sales_outcome="BOOKED")
        repair = import_module("leads.migrations.0025_walkin_is_a_source").retire_walkin_status
        for _ in range(2):
            repair(apps, SimpleNamespace(connection=SimpleNamespace(alias="default")))
        self.walkin.refresh_from_db()
        self.lead.refresh_from_db()
        legacy_call.refresh_from_db()
        self.assertEqual((self.walkin.source, self.walkin.status, self.walkin.sales_outcome), ("WALKIN", "QUALIFIED", "PENDING"))
        self.assertEqual((self.lead.source, self.lead.status, self.lead.sales_outcome), ("Meta", "BOOKED", "BOOKED"))
        self.assertEqual(legacy_call.status, "WALKIN")
        source_leads = self.get(self.ps, "/api/leads/my-dashboard/?section=walkin").data
        self.assertEqual([row["id"] for row in source_leads["results"]], [self.walkin.pk])

    def test_ce_and_ps_touches_are_independent_and_reset_after_reallocation(self):
        ce = User.objects.create_user(email="allocated-ce@example.com", role="CRE")
        Lead.objects.filter(pk=self.walkin.pk).update(assigned_so=ce)
        LeadAudit.objects.create(lead=self.walkin, actor=self.admin, event="assigned_cre", after={"assigned_so": ce.pk})
        LeadAudit.objects.create(lead=self.walkin, actor=self.admin, event="assigned_ps", after={"assigned_ps": self.ps.pk})

        def check(ce_untouched, ps_untouched):
            for user, expected in ((ce, ce_untouched), (self.ps, ps_untouched)):
                dashboard = self.get(user, "/api/leads/my-dashboard/?section=all").data
                self.assertEqual(dashboard["summary"]["untouched"], expected, user.role)
                personal = self.get(user, "/api/analytics/me/?range=all&refresh=1").data
                self.assertEqual(personal["summary"]["untouched"], expected, user.role)
            admin = self.get(self.admin, "/api/analytics/admin/?refresh=1").data
            self.assertEqual(next(row for row in admin["cre"] if row["id"] == ce.pk)["untouched"], ce_untouched)
            self.assertEqual(next(row for row in admin["officers"] if row["id"] == self.ps.pk)["untouched"], ps_untouched)
            current = self.get(self.ceo, "/api/ceo/overview/?range=all&refresh=1").data["current"]
            self.assertEqual(current["untouched_by_ce"], ce_untouched)
            self.assertEqual(current["untouched_by_ps"], ps_untouched)
            for role, expected in (("ce", ce_untouched), ("ps", ps_untouched)):
                drilldown = self.get(self.ceo, f"/api/ceo/leads/?range=all&scope=workload&followup=untouched_{role}&refresh=1")
                self.assertEqual(drilldown.data["count"], expected)

        check(1, 1)
        # A shared lead status change by PS must not count as a CE touch.
        Lead.objects.filter(pk=self.walkin.pk).update(status="BOOKED", sales_outcome="BOOKED")
        CallLog.objects.create(lead=self.walkin, so=self.ps, status="BOOKED", outcome="Booking Done")
        check(1, 0)
        ce_list = self.get(ce, "/api/leads/my-dashboard/?section=fresh&subfilter=untouched").data["results"]
        self.assertEqual([row["id"] for row in ce_list], [self.walkin.pk])
        CallLog.objects.create(lead=self.walkin, so=ce, status="BOOKED")
        check(0, 0)
        # Returning a lead to the same PS starts a new allocation. Old calls remain history.
        LeadAudit.objects.create(lead=self.walkin, actor=self.admin, event="assigned_ps", before={"assigned_ps": self.ps.pk}, after={"assigned_ps": self.other_ps.pk})
        LeadAudit.objects.create(lead=self.walkin, actor=self.admin, event="assigned_ps", before={"assigned_ps": self.other_ps.pk}, after={"assigned_ps": self.ps.pk})
        check(0, 1)
        CallLog.objects.create(lead=self.walkin, so=self.ps, status="BOOKED")
        check(0, 0)
        LeadAudit.objects.create(lead=self.walkin, actor=self.admin, event="reassignment_completed", after={"assigned_so": ce.pk})
        check(1, 0)
        CallLog.objects.create(lead=self.walkin, so=ce, status="BOOKED")
        check(0, 0)
