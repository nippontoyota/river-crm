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
        self.receptionist = User.objects.create_user(email="intake-front@example.com", role=User.Role.RECEPTIONIST, location="Kochi")
        self.config = SystemConfig.objects.create(id=1, lists={"branches": ["Kochi"], "models": ["River Indie"], "sources": ["WEBSITE"], "activities": ["Roadshow", "Exhibition"], "subActivities": {"Roadshow": ["Kochi"], "Exhibition": ["Thrissur"]}})
        self.client.force_authenticate(self.admin)

    def test_admin_configuration_and_creation_across_intake_roles(self):
        response = self.client.put("/api/system-config/", {"lists": self.config.lists}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        for user, endpoint, source in [(self.admin, "/api/leads/", "WEBSITE"), (self.receptionist, "/api/leads/", "WALKIN"), (self.so, "/api/leads/so-create/", "WEBSITE")]:
            self.client.force_authenticate(user)
            response = self.client.post(endpoint, {"rto": "KL-07", "name": "Roadshow enquiry", "phone": "9876543210", "source": source, "activity": "Roadshow", "sub_activity": "Kochi", "model_interest": "River Indie", "enquiry_date": timezone.localdate().isoformat()}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(response.data["sub_activity"], "Kochi")
            self.assertEqual(Lead.objects.get(pk=response.data["id"]).activity, "Roadshow")
        self.assertEqual(self.client.put("/api/system-config/", {"lists": {}}, format="json").status_code, 403)

    def test_invalid_pairs_and_retired_values(self):
        payload = {"rto": "KL-07", "name": "Enquiry", "phone": "9876543210", "source": "WEBSITE"}
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
        response = self.client.post("/api/leads/", {"rto": "KL-07", "name": "Walk-in enquiry", "phone": "9876543210", "source": "WALKIN", "model_interest": "River Indie", "ps_officer_id": self.so.pk}, format="json")
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


class ConfiguredLeadFieldsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(email="lists-admin@example.com", role=User.Role.ADMIN)
        self.ce = User.objects.create_user(email="lists-ce@example.com", role=User.Role.CRE)
        self.ps = User.objects.create_user(email="lists-ps@example.com", role=User.Role.SALES_OFFICER, location="Kochi")
        self.lists = {
            "branches": ["Kochi", "Thrissur"], "models": ["Indie"], "colorVariants": ["Blue"],
            "sources": ["Event"], "activities": ["Roadshow", "Exhibition"],
            "subActivities": {"Roadshow": ["Mall"], "Exhibition": ["Expo"]},
        }
        self.config = SystemConfig.objects.create(id=1, lists=self.lists)

    def test_ce_and_ps_create_use_admin_lists_and_cannot_bypass_empty_lists(self):
        payload = {"rto": "KL-07", "name": "Configured customer", "phone": "9000000001", "source": "Event",
                   "model_interest": "Indie", "branch": "Kochi", "enquiry_date": timezone.localdate().isoformat(),
                   "activity": "Roadshow", "sub_activity": "Mall", "qualification_input": {"variant": "Blue"}}
        for user, endpoint in [(self.ce, "/api/leads/"), (self.ps, "/api/leads/so-create/")]:
            self.client.force_authenticate(user)
            with self.subTest(role=user.role):
                response = self.client.post(endpoint, payload, format="json")
                self.assertEqual(response.status_code, 201, response.data)
                self.assertEqual(response.data["branch"], "Kochi")
                for fields in [{"model_interest": "Typo"}, {"source": "Typo"},
                               {"qualification_input": {"variant": "Typo"}}, {"sub_activity": "Expo"}]:
                    rejected = self.client.post(endpoint, {**payload, **fields}, format="json")
                    self.assertEqual(rejected.status_code, 400, rejected.data)
                self.config.lists = {}
                self.config.save()
                rejected = self.client.post(endpoint, payload, format="json")
                self.assertEqual(rejected.status_code, 400, rejected.data)
                self.assertIn("model_interest", rejected.data)
                self.assertIn("qualification_input", rejected.data)
                self.set_config()
        self.client.force_authenticate(self.ce)
        self.assertEqual(self.client.post("/api/leads/", {**payload, "branch": "Typo"}, format="json").status_code, 400)
        self.ps.location = "Unconfigured branch"
        self.ps.save()
        self.client.force_authenticate(self.ps)
        response = self.client.post("/api/leads/so-create/", payload, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("branch", response.data)

    def set_config(self):
        self.config.lists = self.lists
        self.config.save()

    def test_edit_validates_configured_choices_and_preserves_retired_values(self):
        from leads.models import LeadQualification
        for user in (self.admin, self.ce, self.ps):
            for suffix in ("", "so-update/"):
                with self.subTest(role=user.role, endpoint=suffix):
                    lead = Lead.objects.create(name="Old customer", phone="9000000002", assigned_so=self.ce,
                                               assigned_ps=self.ps, source="Retired source", branch="Retired branch",
                                               model_interest="Retired model", activity="Retired activity", sub_activity="Retired child")
                    LeadQualification.objects.create(lead=lead, variant="Retired color")
                    self.client.force_authenticate(user)
                    url = f"/api/leads/{lead.pk}/{suffix}"
                    payload = {"name": "Updated customer", "source": lead.source, "branch": lead.branch,
                               "model_interest": lead.model_interest, "activity": lead.activity, "sub_activity": lead.sub_activity}
                    response = self.client.patch(url, payload, format="json")
                    self.assertEqual(response.status_code, 200, response.data)
                    for field in ("source", "branch", "model_interest"):
                        rejected = self.client.patch(url, {field: "Unconfigured"}, format="json")
                        self.assertEqual(rejected.status_code, 400, rejected.data)
                        self.assertIn(field, rejected.data)
                    response = self.client.patch(url, {"source": "event", "branch": "Thrissur", "model_interest": "Indie",
                                                       "activity": "Roadshow", "sub_activity": "Mall"}, format="json")
                    self.assertEqual(response.status_code, 200, response.data)
                    lead.refresh_from_db()
                    self.assertEqual((lead.source, lead.branch, lead.model_interest, lead.activity, lead.sub_activity),
                                     ("Event", "Thrissur", "Indie", "Roadshow", "Mall"))
                    self.assertEqual(self.client.patch(url, {"sub_activity": "Expo"}, format="json").status_code, 400)
                    self.config.lists = {}
                    self.config.save()
                    response = self.client.patch(url, {"branch": "Thrissur", "model_interest": "Indie"}, format="json")
                    self.assertEqual(response.status_code, 200, response.data)
                    response = self.client.patch(url, {"branch": "New branch", "model_interest": "New model"}, format="json")
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertIn("branch", response.data)
                    self.assertIn("model_interest", response.data)
                    if user == self.admin and suffix:
                        response = self.client.patch(url, {"qualification": {"variant": "Retired color", "notes": "Updated"}}, format="json")
                        self.assertEqual(response.status_code, 200, response.data)
                        self.assertEqual(self.client.patch(url, {"qualification": {"variant": "New color"}}, format="json").status_code, 400)
                    self.set_config()
