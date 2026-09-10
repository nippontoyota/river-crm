from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from complaints.catalogue import COMPLAINT_SUBTYPES
from complaints.models import Complaint


class ComplaintSubtypeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.cre = User.objects.create_user(email="subtype-cre@example.com", role=User.Role.CRE)
        self.client.force_authenticate(self.cre)
        self.payload = {"customer_name": "Customer", "customer_phone": "9876543210", "category": "PRODUCT_DEFECT", "subtype": "Charging", "subject": "Charging issue", "description": "Charger does not start", "branch": "Kochi"}

    def test_catalogue_and_valid_creation(self):
        self.assertEqual(set(COMPLAINT_SUBTYPES), set(Complaint.Category.values))
        self.assertEqual(self.client.get("/api/system-config/").data["complaint_subtypes"], COMPLAINT_SUBTYPES)
        response = self.client.post("/api/complaints/", self.payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["subtype"], "Charging")
        self.assertEqual(self.client.get(f'/api/complaints/{response.data["id"]}/').data["subtype"], "Charging")

    def test_invalid_missing_subtypes_and_legacy_record(self):
        for subtype in ("", "Refund delay", "Unknown"):
            response = self.client.post("/api/complaints/", {**self.payload, "subtype": subtype}, format="json")
            self.assertEqual(response.status_code, 400)
            self.assertIn("subtype", response.data)
        legacy_payload = {key: value for key, value in self.payload.items() if key != "subtype"}
        self.assertEqual(self.client.post("/api/complaints/", legacy_payload, format="json").status_code, 400)
        legacy = Complaint.objects.create(logged_by=self.cre, **legacy_payload)
        self.assertEqual(self.client.get(f"/api/complaints/{legacy.id}/").data["subtype"], "")
