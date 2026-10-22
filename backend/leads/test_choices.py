from django.test import TestCase
from django.http import QueryDict
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from ceo.filters import ReportFilters
from .models import Lead, LeadAudit, LeadQualification, SystemConfig
from .serializers import LeadSerializer, QualificationSerializer, SystemConfigSerializer


class ConfiguredChoiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.config, _ = SystemConfig.objects.update_or_create(pk=1, defaults={"lists": {
            "sources": ["Meta"], "branches": ["Kochi"], "models": ["Indie"],
            "colorVariants": ["Blue"], "activities": ["Bank Display"],
            "subActivities": {"Bank Display": ["Launch"]},
        }})
        cls.users = {role: User.objects.create_user(email=f"choices-{role}@example.com", role=role, location=" KOCHI ")
                     for role in ("ADMIN", "CRE", "SO", "SALES_MANAGER", "CEO")}
        cls.ids = []
        for index, transform in enumerate((str.lower, str.upper, lambda value: f" {value} ")):
            lead = Lead.objects.create(name=f"Case {index}", phone=f"900000010{index}", source=transform("Meta"),
                branch=transform("Kochi"), model_interest=transform("Indie"), activity=transform("Bank Display"),
                sub_activity=transform("Launch"), assigned_so=cls.users["CRE"], assigned_ps=cls.users["SO"],
                enquiry_date=timezone.localdate())
            LeadQualification.objects.create(lead=lead, variant=transform("Blue"))
            LeadAudit.objects.create(lead=lead, actor=cls.users["CRE"], event="created")
            cls.ids.append(lead.pk)
        Lead.objects.create(name="Other branch", phone="9000000104", source="Meta", branch="Other", enquiry_date=timezone.localdate())
        Lead.objects.create(name="Different source", phone="9000000105", source="Metaverse", branch="Kochi", enquiry_date=timezone.localdate())

    def setUp(self):
        self.client = APIClient()

    def test_filters_match_existing_case_and_spaces_for_all_lead_roles(self):
        before = list(Lead.objects.order_by("pk").values())
        params = {"source": " mEtA ", "branch": " koCHI ", "model": " INDIE ", "color": " blue ",
                  "activity": " BANK DISPLAY ", "sub_activity": " LAUNCH "}
        for role in ("ADMIN", "CRE", "SO", "SALES_MANAGER"):
            with self.subTest(role=role):
                self.client.force_authenticate(self.users[role])
                path = "/api/leads/manager-leads/" if role == "SALES_MANAGER" else "/api/leads/"
                response = self.client.get(path, params)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual({row["id"] for row in response.data["results"]}, set(self.ids))
        for role in ("CRE", "SO"):
            self.client.force_authenticate(self.users[role])
            response = self.client.get("/api/leads/my-dashboard/", {"source": " meta ", "range": "all", "section": "all"})
            self.assertEqual({row["id"] for row in response.data["results"]}, set(self.ids))
        self.assertEqual(list(Lead.objects.order_by("pk").values()), before)

    def test_manager_counts_and_drilldowns_merge_case_variants(self):
        self.client.force_authenticate(self.users["SALES_MANAGER"])
        response = self.client.get("/api/analytics/sales-manager/", {"range": "all", "source": " META ", "color": " BLUE ", "include": "ps,source,lost"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["summary"]["total"], 3)
        for field, label, expected in (("source", "source", "Meta"), ("models", "model", "Indie"), ("colors", "color", "Blue")):
            self.assertEqual([(row[label], row["total"]) for row in response.data[field]], [(expected, 3)])
        self.assertEqual(response.data["ps"][0]["total"], 3)

    def test_ceo_current_and_snapshot_filters_match_same_leads(self):
        self.client.force_authenticate(self.users["CEO"])
        params = {"range": "all", "source": " meta ", "branch": " kochi ", "activity": " bank display ", "sub_activity": " launch ", "model_interest": " indie "}
        for mode in ("period", "cohort"):
            for metric in ("", "E"):
                response = self.client.get("/api/ceo/leads/", {**params, "mode": mode, "metric": metric})
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual({row["id"] for row in response.data["results"]}, set(self.ids))
        report = self.client.get("/api/ceo/segments/", {**params, "dimension": "source"})
        self.assertEqual([(row["label"], row["E"]) for row in report.data["results"]], [("Meta", 3)])
        query = QueryDict(mutable=True)
        query.update(params)
        self.assertEqual(ReportFilters(query).events().count(), 3)

    def test_configured_validation_accepts_case_and_preserves_linked_options(self):
        data = {"qualification_input": {"variant": "No Preference"}, "name": "New", "phone": "9000000110", "rto": "KL-07", "source": " META ", "branch": "kochi",
                "model_interest": "INDIE", "activity": "bank display", "sub_activity": "LAUNCH"}
        serializer = LeadSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        for field, expected in (("source", "Meta"), ("branch", "Kochi"), ("model_interest", "Indie"), ("activity", "Bank Display"), ("sub_activity", "Launch")):
            self.assertEqual(serializer.validated_data[field], expected)
        color = QualificationSerializer(data={"variant": " BLUE "})
        self.assertTrue(color.is_valid(), color.errors)
        self.assertEqual(color.validated_data["variant"], "Blue")
        lists = {**self.config.lists, "sources": ["Meta", " META "], "models": ["Indie", "indie"],
                 "colorVariants": ["Blue", " BLUE "], "branches": ["Kochi", " KOCHI "], "activities": ["Bank Display", "bank display"],
                 "subActivities": {"Bank Display": ["Launch"], " BANK DISPLAY ": ["LAUNCH", "Second Event"]}}
        config = SystemConfigSerializer(self.config, data={"lists": lists})
        self.assertTrue(config.is_valid(), config.errors)
        self.assertEqual(config.validated_data["lists"]["branches"], ["Kochi"])
        self.assertEqual(config.validated_data["lists"]["sources"], ["WALKIN", "Meta"])
        self.assertEqual(config.validated_data["lists"]["models"], ["Indie"])
        self.assertEqual(config.validated_data["lists"]["colorVariants"], ["No Preference", "Blue"])
        self.assertEqual(config.validated_data["lists"]["subActivities"], {"Bank Display": ["Launch", "Second Event"]})
        invalid = LeadSerializer(data={**data, "sub_activity": "Not configured"})
        self.assertFalse(invalid.is_valid())
