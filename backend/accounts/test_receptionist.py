from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from complaints.models import Complaint
from leads.models import Lead, SystemConfig

from .models import User


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], CACHE_TTL_SECONDS=0)
class ReceptionistBranchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        SystemConfig.objects.create(id=1, lists={"branches": ["Kochi", "Thrissur"]})
        cls.admin = User.objects.create_user("branch-admin@example.com", role="ADMIN")
        cls.receptionist = User.objects.create_user("front@example.com", role="RECEPTIONIST", location="Kochi")
        cls.kochi = User.objects.create_user("kochi-ps@example.com", role="SO", location="Kochi")
        cls.thrissur = User.objects.create_user("thrissur-ps@example.com", role="SO", location="Thrissur")
        cls.unassigned = User.objects.create_user("unassigned-ps@example.com", role="SO")
        cls.disabled = User.objects.create_user("disabled-ps@example.com", role="SO", location="Kochi", is_active=False)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.receptionist)
        self.lead_data = {"name": "Walk-in", "phone": "9876543210", "rto": "KL-07", "source": "WALKIN"}
        self.complaint_data = {
            "customer_name": "Walk-in", "customer_phone": "9876543210", "branch": "Kochi",
            "category": "SERVICE_DELAY", "subtype": "Repair delayed", "subject": "Delayed repair",
            "description": "Repair has been delayed.",
        }

    def test_admin_requires_configured_branch_and_can_edit_existing_receptionists(self):
        self.client.force_authenticate(self.admin)
        payload = {"email": "new-front@example.com", "role": "RECEPTIONIST", "password": "password"}
        for fields in ({}, {"location": ""}, {"location": "   "}, {"location": "Unknown"}):
            response = self.client.post("/api/auth/users/", {**payload, **fields}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn("location", response.data)
        response = self.client.post("/api/auth/users/", {**payload, "location": " kochi "}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["location"], "Kochi")
        url = f'/api/auth/users/{response.data["id"]}/'
        for location in ("", "Unknown"):
            self.assertEqual(self.client.patch(url, {"location": location}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(url, {"location": "Thrissur"}, format="json").data["location"], "Thrissur")
        legacy = User.objects.create_user("legacy-front@example.com", role="RECEPTIONIST")
        response = self.client.patch(f"/api/auth/users/{legacy.pk}/", {"location": "Kochi"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_officer_directory_cannot_be_widened_by_query_or_missing_branch(self):
        for query, expected in (("", [self.kochi.pk]), ("?location=kochi", [self.kochi.pk]), ("?location=Thrissur", [])):
            response = self.client.get("/api/auth/sales-officers/" + query)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([row["id"] for row in response.data["results"]], expected)
        self.receptionist.location = ""
        self.receptionist.save(update_fields=["location"])
        self.assertEqual(self.client.get("/api/auth/sales-officers/").data["count"], 0)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/auth/sales-officers/").data["count"], 3)

    def test_capture_saves_branch_with_or_without_an_assignment(self):
        for fields in ({}, {"ps_officer_id": self.kochi.pk}):
            response = self.client.post("/api/leads/", {**self.lead_data, **fields}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            lead = Lead.objects.get(pk=response.data["id"])
            self.assertEqual(lead.branch, "Kochi")
            self.assertEqual(lead.status, "QUALIFIED")
            self.assertEqual(lead.assigned_ps_id, fields.get("ps_officer_id"))

    def test_capture_rejects_other_branches_and_ineligible_officers_without_writes(self):
        for fields in ({"branch": "Thrissur"}, {"ps_officer_id": self.thrissur.pk}, {"ps_officer_id": self.unassigned.pk}, {"ps_officer_id": self.disabled.pk}):
            response = self.client.post("/api/leads/", {**self.lead_data, **fields}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(Lead.objects.exists())

    def test_branchless_receptionist_cannot_capture_or_log_complaints(self):
        self.receptionist.location = ""
        self.receptionist.save(update_fields=["location"])
        for endpoint, data in (("/api/leads/", self.lead_data), ("/api/complaints/", self.complaint_data)):
            response = self.client.post(endpoint, data, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn("branch", response.data)
        self.assertFalse(Lead.objects.exists())
        self.assertFalse(Complaint.objects.exists())

    def test_branch_change_updates_access_without_moving_previous_records(self):
        lead = self.client.post("/api/leads/", {**self.lead_data, "ps_officer_id": self.kochi.pk}, format="json")
        self.assertEqual(lead.status_code, 201, lead.data)
        complaint = self.client.post("/api/complaints/", self.complaint_data, format="json")
        self.assertEqual(complaint.status_code, 201, complaint.data)
        self.assertEqual(self.client.get("/api/analytics/receptionist/").data["summary"]["total"], 1)
        self.assertEqual(self.client.get("/api/complaints/").data["count"], 1)
        self.assertEqual(self.client.post("/api/complaints/", {**self.complaint_data, "branch": "Thrissur"}, format="json").status_code, 400)
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/auth/users/{self.receptionist.pk}/", {"location": "Thrissur"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.receptionist.refresh_from_db()
        self.client.force_authenticate(self.receptionist)
        self.assertEqual(self.client.get("/api/auth/me/").data["user"]["location"], "Thrissur")
        officers = self.client.get("/api/auth/sales-officers/").data["results"]
        self.assertEqual([officer["id"] for officer in officers], [self.thrissur.pk])
        self.assertEqual(self.client.get("/api/analytics/receptionist/").data["summary"]["total"], 0)
        self.assertEqual(self.client.get("/api/complaints/").data["count"], 0)
        self.assertEqual(self.client.get(f'/api/complaints/{complaint.data["id"]}/').status_code, 404)
        new_lead = self.client.post("/api/leads/", {**self.lead_data, "ps_officer_id": self.thrissur.pk}, format="json")
        self.assertEqual(new_lead.status_code, 201, new_lead.data)
        self.assertEqual(new_lead.data["branch"], "Thrissur")
        self.assertEqual(Lead.objects.get(pk=lead.data["id"]).branch, "Kochi")
        self.assertEqual(Complaint.objects.get(pk=complaint.data["id"]).branch, "Kochi")

    def test_receptionist_cannot_change_their_own_branch(self):
        response = self.client.patch(f"/api/auth/users/{self.receptionist.pk}/", {"location": "Thrissur"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.receptionist.refresh_from_db()
        self.assertEqual(self.receptionist.location, "Kochi")
