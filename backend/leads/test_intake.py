from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import Lead, SystemConfig


class ActivityIntakeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(email="intake-admin@example.com", role=User.Role.ADMIN)
        self.so = User.objects.create_user(email="intake-so@example.com", role=User.Role.SALES_OFFICER, location="Kochi")
        self.receptionist = User.objects.create_user(email="intake-front@example.com", role=User.Role.RECEPTIONIST)
        self.config = SystemConfig.objects.create(id=1, lists={"sources": ["WEBSITE"], "activities": ["Roadshow", "Exhibition"], "subActivities": {"Roadshow": ["Kochi"], "Exhibition": ["Thrissur"]}})
        self.client.force_authenticate(self.admin)

    def test_admin_configuration_and_creation_across_intake_roles(self):
        response = self.client.put("/api/system-config/", {"lists": self.config.lists}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        for user, endpoint, source in [(self.admin, "/api/leads/", "WEBSITE"), (self.receptionist, "/api/leads/", "WALKIN"), (self.so, "/api/leads/so-create/", "Referral")]:
            self.client.force_authenticate(user)
            response = self.client.post(endpoint, {"name": "Roadshow enquiry", "phone": "9876543210", "source": source, "activity": "Roadshow", "sub_activity": "Kochi", "model_interest": "River Indie", "enquiry_date": timezone.localdate().isoformat()}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["sub_activity"], "Kochi")
            self.assertEqual(Lead.objects.get(pk=response.data["id"]).activity, "Roadshow")
        self.assertEqual(self.client.put("/api/system-config/", {"lists": {}}, format="json").status_code, 403)

    def test_invalid_pairs_and_retired_values(self):
        payload = {"name": "Enquiry", "phone": "9876543210", "source": "WEBSITE"}
        for fields in [{"activity": "Roadshow", "sub_activity": "Thrissur"}, {"sub_activity": "Kochi"}, {"activity": "Unknown"}]:
            self.assertEqual(self.client.post("/api/leads/", {**payload, **fields}, format="json").status_code, 400)
        lead = Lead.objects.create(**payload, activity="Retired", sub_activity="Old location")
        response = self.client.patch(f"/api/leads/{lead.id}/so-update/", {"name": "Updated", "activity": "Retired", "sub_activity": "Old location"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        response = self.client.patch(f"/api/leads/{lead.id}/so-update/", {"activity": "Roadshow"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sub_activity"], "")
        self.assertEqual(self.client.put("/api/system-config/", {"lists": {"activities": ["Roadshow"], "subActivities": {"Missing": ["Kochi"]}}}, format="json").status_code, 400)

    def test_receptionist_can_capture_without_color_or_timeline(self):
        self.client.force_authenticate(self.receptionist)
        response = self.client.post("/api/leads/", {"name": "Walk-in enquiry", "phone": "9876543210", "source": "WALKIN", "model_interest": "River Indie", "ps_officer_id": self.so.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        lead = Lead.objects.get(pk=response.data["id"])
        self.assertEqual(lead.source, Lead.Source.WALKIN)
        self.assertEqual(lead.status, Lead.Status.QUALIFIED)
        self.assertEqual(lead.assigned_ps, self.so)
        self.assertEqual(lead.model_interest, "River Indie")
        self.assertIsNone(response.data["qualification"])

    def test_model_seed_preserves_configuration_and_is_idempotent(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        self.config.lists["models"] = ["Legacy model"]
        self.config.save()
        seed = import_module("leads.migrations.0018_seed_river_indie").seed_river_indie
        editor = connection.schema_editor()
        seed(apps, editor)
        seed(apps, editor)
        self.config.refresh_from_db()
        self.assertEqual(self.config.lists["models"], ["Legacy model", "River Indie"])
        self.assertEqual(self.config.lists["subActivities"]["Roadshow"], ["Kochi"])
