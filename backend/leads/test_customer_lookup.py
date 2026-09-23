from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from .models import CallLog, Lead, LeadQualification, SystemConfig


class CustomerLookupTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ce = User.objects.create_user(email="ce@example.com", role="CRE", first_name="Current CE")
        cls.other_ce = User.objects.create_user(email="other@example.com", role="CRE", first_name="Other CE")
        cls.ps = User.objects.create_user(email="ps@example.com", role="SO", first_name="Saved PS", phone="9000000001", location="Kochi")
        cls.manager = User.objects.create_user(email="manager@example.com", role="SALES_MANAGER", first_name="Manager", phone="9000000002", location=" koCHI ")
        cls.lead = Lead.objects.create(name="Customer", phone="9876543210", assigned_so=cls.ce, assigned_ps=cls.ps, branch="Kochi", enquiry_date=timezone.localdate())
        cls.other = Lead.objects.create(name="Other enquiry", phone=cls.lead.phone, assigned_so=cls.other_ce, assigned_ps=cls.ps, branch="Central", enquiry_date=timezone.localdate() - timedelta(days=1))
        SystemConfig.objects.create(id=1, lists={"branches": ["Kochi", "Central"], "models": ["Indie"], "colorVariants": ["Blue"]})

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.ce)

    def lookup(self, phone="9876543210", **params):
        return self.client.get("/api/leads/customer-lookup/", {"phone": phone, **params})

    def detail(self):
        response = self.client.get(f"/api/leads/{self.lead.id}/")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def test_normalized_exact_search_ignores_queue_filters_and_deleted_leads(self):
        Lead.objects.create(name="Deleted enquiry", phone=self.lead.phone, deleted_at=timezone.now())
        Lead.objects.create(name="Different phone", phone="9876543211")
        for phone in ["9876543210", "+91 (98765) 43210", "09876543210", "98765-43210"]:
            with self.subTest(phone=phone):
                response = self.lookup(phone, branch="Absent", q="No customer", status="WON", date_from="2099-01-01", unassigned="true")
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(response.data["count"], 2)
                self.assertEqual([row["id"] for row in response.data["results"]], [self.lead.id, self.other.id])
        self.assertEqual(self.lookup("9000000000").data["count"], 0)

    def test_missing_partial_and_invalid_numbers_are_validation_errors(self):
        self.assertEqual(self.client.get("/api/leads/customer-lookup/").status_code, 400)
        for phone in ["", "98765", "98765432100", "letters9876543210", "+449876543210", "9876543210 ext 1"]:
            with self.subTest(phone=phone):
                response = self.lookup(phone)
                self.assertEqual(response.status_code, 400)
                self.assertIn("phone", response.data)

    def test_only_active_admin_and_ce_can_lookup(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.lookup().status_code, 401)
        for role in User.Role.values:
            user = User.objects.create_user(email=f"role-{role}@example.com", role=role)
            self.client.force_authenticate(user)
            with self.subTest(role=role):
                self.assertEqual(self.lookup().status_code, 200 if role in {"CRE", "ADMIN"} else 403)
            if role in {"CRE", "ADMIN"}:
                for active, deleted in [(False, None), (True, timezone.now())]:
                    user.is_active, user.deleted_at = active, deleted
                    user.save(update_fields=["is_active", "deleted_at"])
                    self.assertEqual(self.lookup().status_code, 403)

    def test_team_response_is_limited_and_full_access_does_not_expand(self):
        LeadQualification.objects.create(lead=self.other, notes="Private qualification")
        CallLog.objects.create(lead=self.other, so=self.other_ce, status="FRESH", remarks="Private call")
        rows = self.lookup().data["results"]
        allowed = {"id", "name", "phone", "enquiry_date", "status", "branch", "assigned_ce", "needs_cre_reassignment", "ownership", "can_open"}
        for row in rows:
            self.assertEqual(set(row), allowed)
            self.assertEqual(set(row["ownership"]), {"assigned_ps", "needs_so_reassignment", "branch", "manager_branch", "managers"})
            self.assertEqual(set(row["ownership"]["assigned_ps"]), {"id", "name", "phone", "branch", "lifecycle_status"})
        self.assertTrue(rows[0]["can_open"])
        self.assertFalse(rows[1]["can_open"])
        self.assertEqual(rows[1]["assigned_ce"]["name"], "Other CE")
        self.assertEqual(self.client.get(f"/api/leads/{self.other.id}/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/leads/{self.other.id}/", {"name": "Changed"}, format="json").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/leads/{self.other.id}/so-update/", {"remarks": "Changed"}, format="json").status_code, 404)
        self.assertEqual(self.client.post(f"/api/leads/{self.other.id}/log-call/", {"status": "PENDING"}, format="json").status_code, 404)
        self.assertEqual([row["id"] for row in self.client.get("/api/leads/").data["results"]], [self.lead.id])
        self.assertEqual(self.client.post("/api/leads/customer-lookup/", {"phone": self.lead.phone}).status_code, 405)

    def test_duplicate_pagination_and_constant_query_counts(self):
        Lead.objects.bulk_create([Lead(name=f"Enquiry {i}", phone=self.lead.phone, assigned_so=self.ce, assigned_ps=self.ps, branch="Kochi") for i in range(51)])
        with self.assertNumQueries(3):
            first = self.lookup()
        with self.assertNumQueries(3):
            second = self.lookup(page=2)
        self.assertEqual(first.data["count"], 53)
        self.assertEqual(len(first.data["results"]), 50)
        self.assertIsNotNone(first.data["next"])
        self.assertIsNone(second.data["next"])
        self.assertEqual(len({row["id"] for row in first.data["results"] + second.data["results"]}), 53)
        with self.assertNumQueries(2):
            dashboard = self.client.get("/api/leads/my-dashboard/?section=all")
        self.assertEqual(len(dashboard.data["results"]), 52)
        self.assertTrue(all(row["assigned_ps_name"] == "Saved PS" for row in dashboard.data["results"]))

    def test_manager_branch_precedence_fallback_and_multiple_active_contacts(self):
        second = User.objects.create_user(email="manager2@example.com", role="SALES_MANAGER", location="KOCHI")
        User.objects.create_user(email="disabled@example.com", role="SALES_MANAGER", location="Kochi", is_active=False)
        User.objects.create_user(email="deleted@example.com", role="SALES_MANAGER", location="Kochi", deleted_at=timezone.now())
        User.objects.create_user(email="no-branch@example.com", role="SALES_MANAGER", location="")
        expected = {self.manager.id, second.id}
        ownership = self.detail()["ownership"]
        self.assertEqual({manager["id"] for manager in ownership["managers"]}, expected)
        self.assertEqual(next(manager["phone"] for manager in ownership["managers"] if manager["id"] == second.id), "")
        self.assertEqual(self.lookup().data["results"][0]["ownership"], ownership)
        self.assertEqual(self.lookup().data["results"][1]["ownership"]["managers"], [])  # Central must not fall back to Kochi.
        Lead.objects.filter(pk=self.lead.pk).update(branch=" ")
        self.assertEqual({manager["id"] for manager in self.detail()["ownership"]["managers"]}, expected)
        Lead.objects.filter(pk=self.lead.pk).update(assigned_ps=None)
        self.assertEqual(self.detail()["ownership"]["managers"], [])

    def test_qualification_later_status_changes_and_reassignment_use_saved_owner(self):
        Lead.objects.filter(pk=self.lead.pk).update(assigned_ps=None)
        response = self.client.patch(f"/api/leads/{self.lead.id}/so-update/", {"call_outcome": "QUALIFIED", "city": "Kochi", "branch": "Kochi", "ps_officer_id": self.ps.id, "remarks": "Customer qualified", "qualification": {"variant": "Blue"}}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["ownership"]["assigned_ps"]["id"], self.ps.id)
        replacement = User.objects.create_user(email="replacement@example.com", role="SO", first_name="New PS", location="Central", phone="9000000003")
        for lead_status in ["QUALIFIED", "WALKIN", "WON", "LOST"]:
            Lead.objects.filter(pk=self.lead.pk).update(status=lead_status, test_drive_completed_at=timezone.now())
            for section in ["all", "test_drive_completed", {"QUALIFIED": "qualified", "WALKIN": "walkin", "WON": "won", "LOST": "lost"}[lead_status]]:
                row = self.client.get("/api/leads/my-dashboard/", {"section": section}).data["results"][0]
                self.assertEqual(row["assigned_ps"], self.ps.id)
                self.assertEqual(row["assigned_ps_status"], "ACTIVE")
                self.assertEqual(row["branch"], "Kochi")
        Lead.objects.filter(pk=self.lead.pk).update(assigned_ps=replacement)
        self.assertEqual(self.detail()["ownership"]["assigned_ps"]["name"], "New PS")
        self.assertEqual(self.lookup().data["results"][0]["ownership"]["assigned_ps"]["phone"], replacement.phone)
        Lead.objects.filter(pk=self.lead.pk).update(assigned_so=self.other_ce)
        self.assertFalse(self.lookup().data["results"][0]["can_open"])
        self.assertEqual(self.client.get(f"/api/leads/{self.lead.id}/").status_code, 404)

    def test_unassigned_reassignment_inactive_deleted_and_missing_phones(self):
        for active, deleted, expected in [(False, None, "DISABLED"), (True, timezone.now(), "DELETED"), (True, None, "ACTIVE")]:
            User.objects.filter(pk=self.ps.pk).update(is_active=active, deleted_at=deleted, phone="")
            ownership = self.detail()["ownership"]
            self.assertEqual(ownership["assigned_ps"]["lifecycle_status"], expected)
            self.assertEqual(ownership["assigned_ps"]["phone"], "")
            row = self.client.get("/api/leads/my-dashboard/?section=all").data["results"][0]
            self.assertEqual(row["assigned_ps_status"], expected)
        for needs in [False, True]:
            Lead.objects.filter(pk=self.lead.pk).update(assigned_ps=None, needs_so_reassignment=needs)
            ownership = self.detail()["ownership"]
            self.assertIsNone(ownership["assigned_ps"])
            self.assertEqual(ownership["needs_so_reassignment"], needs)
            row = self.client.get("/api/leads/my-dashboard/?section=all").data["results"][0]
            self.assertIsNone(row["assigned_ps_status"])
            self.assertEqual(row["needs_so_reassignment"], needs)
