from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from ceo.models import OperationEvent
from complaints.models import Complaint, ComplaintNote
from leads.models import SystemConfig


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], CACHE_TTL_SECONDS=0)
class ComplaintDetailsTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user("admin@example.invalid", role="ADMIN")
        self.creator = User.objects.create_user("creator@example.invalid", role="CRE")
        self.handler = User.objects.create_user("handler@example.invalid", role="COMPLAINTS", location="Kochi")
        SystemConfig.objects.create(id=1, lists={"models": ["Indie"], "branches": ["Kochi"]})
        self.complaint = Complaint.objects.create(customer_name="Customer", customer_phone="9876543210",
            customer_email="old@example.invalid", category="PRODUCT_DEFECT", subtype="Charging", subject="Charger issue",
            description="Charger does not start", source="PHONE", model_interest="Indie", branch="Kochi",
            priority="HIGH", status="RESOLVED", resolution_notes="Fixed", resolved_at=timezone.now(),
            logged_by=self.creator, assigned_to=self.handler)
        ComplaintNote.objects.create(complaint=self.complaint, author=self.handler, content="Fixed")
        self.path = f"/api/complaints/{self.complaint.pk}/details/"
        self.client.force_authenticate(self.admin)

    def test_admin_correction_preserves_workflow_and_records_changed_values(self):
        protected = {field: getattr(self.complaint, field) for field in ("branch", "priority", "status", "assigned_to_id",
            "resolution_notes", "resolved_at", "ticket_number", "uid", "logged_by_id", "created_at", "related_lead_id")}
        changes = {"customer_name": "Corrected customer", "customer_phone": "9876543211", "customer_email": "new@example.invalid",
                   "category": "OTHER", "subtype": "Other", "subject": "Helmet issue", "description": "Helmet quality issue",
                   "source": "WALKIN", "model_interest": ""}
        response = self.client.patch(self.path, changes, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.complaint.refresh_from_db()
        self.assertEqual({key: getattr(self.complaint, key) for key in protected}, protected)
        self.assertEqual({key: response.data[key] for key in changes}, changes)
        self.assertEqual(response.data["notes"][0]["content"], "Fixed")
        event = OperationEvent.objects.get(complaint=self.complaint, kind="complaint_updated")
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.after, changes)
        self.assertEqual(event.before["customer_name"], "Customer")
        self.assertEqual(set(event.before), set(changes))
        self.assertEqual(ComplaintNote.objects.count(), 1)
        self.assertEqual(self.client.get("/api/complaints/?q=Corrected").data["count"], 1)
        self.assertEqual(self.client.get("/api/complaints/?category=PRODUCT_DEFECT").data["count"], 0)
        self.assertEqual(self.client.get("/api/complaints/analytics/?range=all").data["by_category"], [{"category": "OTHER", "count": 1}])

    def test_other_roles_cannot_edit_details(self):
        for role in ("CRE", "RECEPTIONIST", "COMPLAINTS", "SO", "SALES_MANAGER", "CEO", "FEEDBACK", "SERVICE", "META_UPLOADER"):
            user = User.objects.create_user(f"{role}@example.invalid", role=role, location="Kochi")
            self.client.force_authenticate(user)
            self.assertEqual(self.client.patch(self.path, {"subject": "No"}, format="json").status_code, 403, role)
        self.client.force_authenticate(None)
        self.assertIn(self.client.patch(self.path, {"subject": "No"}, format="json").status_code, (401, 403))
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.subject, "Charger issue")

    def test_protected_or_unknown_fields_reject_entire_request(self):
        for key, value in {"branch": "Thrissur", "status": "CLOSED", "priority": "LOW", "assigned_to": self.admin.pk,
                           "resolution_notes": "Overwritten", "resolved_at": None, "logged_by": self.admin.pk,
                           "ticket_number": "CMP-99999", "related_lead": None, "created_at": "2020-01-01", "unknown": True}.items():
            response = self.client.patch(self.path, {key: value, "subject": "Must not save"}, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn(key, response.data)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.subject, "Charger issue")
        self.assertFalse(OperationEvent.objects.filter(kind="complaint_updated").exists())
        self.assertEqual(self.client.patch(f"/api/complaints/{self.complaint.pk}/", {"status": "CLOSED"}, format="json").status_code, 403)

    def test_invalid_values_and_category_subtype_pair(self):
        for changes in ({"customer_name": "  "}, {"customer_phone": "123"}, {"customer_email": "invalid"}, {"subject": ""},
                        {"description": ""}, {"source": "UNKNOWN"}, {"model_interest": "Unknown"},
                        {"category": "OTHER"}, {"subtype": "Refund delay"}, {"subtype": ""}, [{"subject": "Invalid structure"}]):
            response = self.client.patch(self.path, changes, format="json")
            self.assertEqual(response.status_code, 400, response.data)
        self.assertFalse(OperationEvent.objects.filter(kind="complaint_updated").exists())

    def test_legacy_options_and_noop_updates(self):
        Complaint.objects.filter(pk=self.complaint.pk).update(subtype="Retired subtype", model_interest="Retired model")
        response = self.client.patch(self.path, {"customer_name": "New name", "subtype": "Retired subtype", "model_interest": "Retired model"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(OperationEvent.objects.get(kind="complaint_updated").after, {"customer_name": "New name"})
        timestamp = response.data["updated_at"]
        response = self.client.patch(self.path, {"customer_name": "New name"}, format="json")
        self.assertEqual(response.data["updated_at"], timestamp)
        self.assertEqual(OperationEvent.objects.filter(kind="complaint_updated").count(), 1)
        Complaint.objects.filter(pk=self.complaint.pk).update(subtype="")
        self.assertEqual(self.client.patch(self.path, {"subject": "Legacy correction"}, format="json").status_code, 200)
