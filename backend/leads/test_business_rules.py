"""Regression checks for colour entry and closed-lead follow-up reporting."""
import importlib
from datetime import timedelta
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from analytics.views import color_rows
from leads.models import FollowUp, Lead, LeadQualification, SystemConfig
from leads.serializers import LeadSerializer, QualificationSerializer, SystemConfigSerializer
from leads.metrics import actionable_followups


class LeadColourRulesTests(TestCase):
    def setUp(self):
        SystemConfig.objects.update_or_create(pk=1, defaults={"lists": {
            "branches": ["Kochi"], "models": ["Indie"], "sources": ["WEBSITE"],
            "colorVariants": ["Blue", "Color not set", " no preference "]}})
        self.client = APIClient()
        self.payload = {"name": "Customer", "phone": "9876543210", "source": "WALKIN", "rto": "KL-07",
                        "model_interest": "Indie", "enquiry_date": str(timezone.localdate())}

    def test_all_manual_creation_roles_require_explicit_colour(self):
        for index, role in enumerate(["ADMIN", "CRE", "SO", "RECEPTIONIST"]):
            user = User.objects.create_user(f"{role}@example.com", role=role, location="Kochi")
            self.client.force_authenticate(user)
            path = "/api/leads/so-create/" if role == "SO" else "/api/leads/"
            data = {**self.payload, "phone": f"98765432{index:02}"}
            for qualification in (None, {}, {"variant": ""}, {"variant": "  "}, {"variant": "Color not set"}, {"variant": "Colour not set"}):
                with self.subTest(role=role, qualification=qualification):
                    body = data if qualification is None else {**data, "qualification_input": qualification}
                    response = self.client.post(path, body, format="json")
                    self.assertEqual(response.status_code, 400, response.data)
            response = self.client.post(path, {**data, "qualification_input": {"variant": "No Preference"}}, format="json")
            self.assertEqual(response.status_code, 201, response.data)
            self.assertEqual(Lead.objects.get(pk=response.data["id"]).qualification.variant, "No Preference")

    def test_configuration_and_edit_validation(self):
        config = SystemConfig.objects.get(pk=1)
        self.assertEqual(SystemConfigSerializer(config).data["lists"]["colorVariants"], ["No Preference", "Blue"])
        lead = Lead.objects.create(name="Existing", phone="9999999999", rto="KL-07")
        LeadQualification.objects.create(lead=lead, variant="Blue")
        for value in ("", "Color not set", "Colour not set", "Unknown"):
            serializer = QualificationSerializer(data={"variant": value}, context={"lead": lead}, partial=True)
            self.assertFalse(serializer.is_valid())
        admin = User.objects.create_user("admin@example.com", role="ADMIN")
        self.client.force_authenticate(admin)
        response = self.client.patch(f"/api/leads/{lead.pk}/so-update/", {"qualification": {"variant": "No Preference"}}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        lead.qualification.refresh_from_db()
        self.assertEqual(lead.qualification.variant, "No Preference")
        partial = LeadSerializer(lead, data={"name": "Renamed"}, partial=True)
        self.assertTrue(partial.is_valid(), partial.errors)
        partial.save()
        self.assertEqual(lead.qualification.variant, "No Preference")
        officer = User.objects.create_user("restricted@example.com", role="SO")
        lead.assigned_ps = officer
        lead.save(update_fields=["assigned_ps"])
        self.client.force_authenticate(officer)
        response = self.client.patch(f"/api/leads/{lead.pk}/", {"qualification_input": {"variant": "Blue"}}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        lead.qualification.refresh_from_db()
        self.assertEqual(lead.qualification.variant, "No Preference")

    def test_colour_migration_merges_blanks_without_rewriting_real_colours(self):
        leads = [Lead.objects.create(name=str(i), phone=f"90000000{i:02}") for i in range(6)]
        for lead, value in zip(leads, ["", "  ", "Color not set", "no preference", "Blue"]):
            LeadQualification.objects.create(lead=lead, variant=value, notes="Retain notes")
        migration = importlib.import_module("leads.migrations.0026_normalize_lead_colors")
        migration.normalize_colors(apps, SimpleNamespace(connection=connection))
        migration.normalize_colors(apps, SimpleNamespace(connection=connection))
        self.assertEqual(list(LeadQualification.objects.order_by("lead_id").values_list("variant", flat=True)),
                         ["No Preference"] * 4 + ["Blue", "No Preference"])
        self.assertEqual(LeadQualification.objects.filter(notes="Retain notes").count(), 5)
        self.assertEqual({row["color"]: row["total"] for row in color_rows(Lead.objects.all())}, {"No Preference": 5, "Blue": 1})

    def test_lost_lead_has_no_next_followup_even_with_legacy_open_records(self):
        owner = User.objects.create_user("ps@example.com", role="SO")
        for status in ("LOST", "UNQUALIFIED"):
            lead = Lead.objects.create(name=status, phone="9000000000", status=status, assigned_ps=owner)
            FollowUp.objects.create(lead=lead, so=owner, scheduled_for=timezone.now() + timedelta(days=1))
            self.assertIsNone(LeadSerializer(lead).data["next_follow_up"])
            self.assertFalse(actionable_followups().filter(lead=lead).exists())
            self.assertEqual(lead.follow_ups.count(), 1)

    def test_lost_outcome_resolves_open_work_and_rejects_another_followup(self):
        officer = User.objects.create_user("closing@example.com", role="SO", location="Kochi")
        lead = Lead.objects.create(name="Closing lead", phone="9000000011", status="PENDING", assigned_ps=officer)
        followup = FollowUp.objects.create(lead=lead, so=officer, scheduled_for=timezone.now() + timedelta(days=1))
        self.client.force_authenticate(officer)
        url = f"/api/leads/{lead.pk}/so-update/"
        payload = {"call_status": "Connected", "call_outcome": "Not Interested", "remarks": "Customer declined"}
        response = self.client.patch(url, {**payload, "follow_up_at": (timezone.now() + timedelta(days=2)).isoformat()}, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        followup.refresh_from_db()
        self.assertIsNotNone(followup.resolved_at)
        self.assertIsNone(response.data["next_follow_up"])
        self.assertEqual(lead.follow_ups.count(), 1)
        self.assertEqual(lead.call_logs.count(), 1)
        self.assertFalse(actionable_followups().filter(lead=lead).exists())
