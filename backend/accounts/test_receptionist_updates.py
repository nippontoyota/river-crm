from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from ceo.models import Milestone
from leads.models import Lead, LeadAudit, SystemConfig


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], CACHE_TTL_SECONDS=0)
class ReceptionistUpdatesTests(TestCase):
    def setUp(self):
        clock = patch("django.utils.timezone.now", return_value=datetime(2026, 11, 2, 0, 0, tzinfo=dt_timezone.utc))
        clock.start()
        self.addCleanup(clock.stop)
        self.client = APIClient()
        self.front = User.objects.create_user("front@example.invalid", role="RECEPTIONIST", location="Kochi")
        self.other = User.objects.create_user("other-front@example.invalid", role="RECEPTIONIST", location="Kochi")
        self.so = User.objects.create_user("so@example.invalid", role="SO", first_name="Same", location="Kochi")
        self.other_so = User.objects.create_user("other-so@example.invalid", role="SO", first_name="Same", location="Kochi")
        self.admin = User.objects.create_user("admin@example.invalid", role="ADMIN")
        self.manager = User.objects.create_user("manager@example.invalid", role="SALES_MANAGER", location="Kochi")
        self.ceo = User.objects.create_user("ceo@example.invalid", role="CEO")
        SystemConfig.objects.create(id=1, lists={"branches": ["Kochi"], "models": ["Indie"]})
        self.client.force_authenticate(self.front)
        self.payload = {"name": "New customer", "phone": "9876543210", "rto": "KL-07", "source": "WALKIN",
                        "model_interest": "Indie", "qualification_input": {"variant": "No Preference"}, "ps_officer_id": self.so.pk}

    def capture(self, **fields):
        payload = {**self.payload, "phone": str(9876543210 + Lead.objects.count()), **fields}
        response = self.client.post("/api/leads/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return Lead.objects.get(pk=response.data["id"])

    def test_capture_defaults_omitted_and_null_dates_and_preserves_explicit_dates(self):
        today = timezone.localdate()
        for fields, expected in (({}, today), ({"enquiry_date": None}, today), ({"enquiry_date": "2026-10-31"}, today.replace(month=10, day=31))):
            lead = self.capture(**fields)
            self.assertEqual(lead.enquiry_date, expected)
            self.assertEqual(Milestone.objects.get(lead=lead, kind="E").occurred_on, expected)

    def test_capture_uses_india_date_and_rejects_invalid_or_future_dates(self):
        with patch("django.utils.timezone.now", return_value=datetime(2026, 11, 1, 18, 30, tzinfo=dt_timezone.utc)):
            self.assertEqual(self.capture().enquiry_date.isoformat(), "2026-11-02")
        for date in ("2026-11-03", "2026-02-30", "invalid", ""):
            response = self.client.post("/api/leads/", {**self.payload, "phone": "9876543220", "enquiry_date": date}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn("enquiry_date", response.data)
        self.assertEqual(Lead.objects.count(), 1)

    def test_capture_appears_in_details_and_manager_admin_ceo_reports(self):
        lead = self.capture()
        query = "?range=custom&date_from=2026-11-02&date_to=2026-11-02&source=WALKIN"
        for actor, endpoint in ((self.manager, "sales-manager"), (self.admin, "admin")):
            self.client.force_authenticate(actor)
            response = self.client.get(f"/api/analytics/{endpoint}/{query}")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data["summary"]["etbr_enquired"], 1)
        self.client.force_authenticate(self.so)
        self.assertEqual(self.client.get(f"/api/leads/{lead.pk}/").data["enquiry_date"], "2026-11-02")
        self.client.force_authenticate(self.ceo)
        response = self.client.get("/api/ceo/leads/" + query)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)

    def test_edit_cannot_clear_date_but_can_correct_it_and_sync_milestone(self):
        lead = self.capture()
        for actor, suffix in ((self.admin, ""), (self.admin, "so-update/"), (self.so, "so-update/")):
            self.client.force_authenticate(actor)
            path = f"/api/leads/{lead.pk}/{suffix}"
            for invalid in (None, "2026-11-03"):
                response = self.client.patch(path, {"enquiry_date": invalid}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
            response = self.client.patch(path, {"enquiry_date": "2026-11-01"}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(Milestone.objects.get(lead=lead, kind="E").occurred_on.isoformat(), "2026-11-01")

    def test_old_blank_records_are_not_automatically_changed(self):
        legacy = Lead.objects.create(name="Legacy", phone="9876543200", source="WALKIN", branch="Kochi", generated_by=self.front, assigned_ps=self.so)
        LeadAudit.objects.create(lead=legacy, actor=self.front, event="created")
        self.capture()
        self.client.get("/api/analytics/receptionist/")
        self.client.force_authenticate(self.admin)
        self.assertIsNone(self.client.get(f"/api/leads/{legacy.pk}/").data["enquiry_date"])
        response = self.client.patch(f"/api/leads/{legacy.pk}/", {"name": "Corrected name", "enquiry_date": None}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        legacy.refresh_from_db()
        self.assertIsNone(legacy.enquiry_date)
        self.assertIsNone(Milestone.objects.get(lead=legacy, kind="E").occurred_on)

    def captured_at(self, stamp, **fields):
        actor = fields.pop("actor", self.front)
        lead = Lead.objects.create(name="Fixture", phone="9876543201", source=fields.pop("source", "WALKIN"),
                                   branch=fields.pop("branch", "Kochi"), assigned_ps=fields.pop("assigned_ps", self.so), **fields)
        audit = LeadAudit.objects.create(lead=lead, actor=actor, event="created")
        LeadAudit.objects.filter(pk=audit.pk).update(created_at=datetime.fromisoformat(stamp))
        return lead

    def test_monthly_counts_use_capture_dates_current_owners_and_branch_scope(self):
        self.captured_at("2026-11-01T18:30:00+00:00")  # Nov 2 in IST: today.
        older = self.captured_at("2026-10-31T18:30:00+00:00", assigned_ps=self.other_so)  # Nov 1 in IST.
        self.captured_at("2026-11-01T18:29:59+00:00", assigned_ps=None)
        self.captured_at("2026-10-31T18:29:59+00:00")  # Previous month.
        self.captured_at("2026-11-02T00:00:00+00:00", actor=self.other)
        self.captured_at("2026-11-02T00:00:00+00:00", branch="Thrissur")
        self.captured_at("2026-11-02T00:00:00+00:00", source="META")
        self.captured_at("2026-11-02T00:00:00+00:00", deleted_at=timezone.now())
        self.captured_at("2026-11-03T00:00:00+00:00")  # Future audit is excluded.
        # Multiple audit rows do not multiply a captured lead.
        LeadAudit.objects.create(lead=older, actor=self.front, event="assigned_ps")
        response = self.client.get("/api/analytics/receptionist/")
        self.assertEqual(response.status_code, 200, response.data)
        rows = {row["so_id"]: row for row in response.data["so_breakdown"]}
        self.assertEqual(response.data["summary"]["total"], 1)
        self.assertEqual({key: (row["count"], row["month_count"]) for key, row in rows.items()},
                         {self.so.pk: (1, 1), self.other_so.pk: (0, 1), None: (0, 1)})
        self.assertEqual(rows[self.so.pk]["name"], rows[self.other_so.pk]["name"])
        older.assigned_ps = self.so
        older.save(update_fields=["assigned_ps"])
        rows = {row["so_id"]: row for row in self.client.get("/api/analytics/receptionist/").data["so_breakdown"]}
        self.assertEqual((rows[self.so.pk]["count"], rows[self.so.pk]["month_count"]), (1, 2))
        self.assertNotIn(self.other_so.pk, rows)

    def test_month_rollover_and_missing_branch(self):
        self.captured_at("2026-10-31T18:30:00+00:00")
        with patch("django.utils.timezone.now", return_value=datetime(2026, 11, 30, 18, 30, tzinfo=dt_timezone.utc)):
            self.assertEqual(self.client.get("/api/analytics/receptionist/").data["so_breakdown"], [])
        self.front.location = ""
        self.front.save(update_fields=["location"])
        self.assertEqual(self.client.get("/api/analytics/receptionist/").data["so_breakdown"], [])
