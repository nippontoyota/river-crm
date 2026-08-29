from django.test import TestCase
from rest_framework.test import APIClient
from accounts.models import User
from leads.models import Lead

class ReproduceBugTest(TestCase):
    def test_reproduce(self):
        admin = User.objects.create_superuser("admin@revera.com", "password")
        client = APIClient()
        client.force_authenticate(admin)
        
        lead = Lead.objects.create(name="Test", phone="1234567890", status="QUALIFIED")
        
        response = client.patch(f"/api/leads/{lead.id}/so-update/", {
            "call_outcome": "Need SO Call",
            "status": "PENDING",
            "category": "WARM",
            "follow_up_at": "2026-08-22T09:00:00.000Z",
            "remarks": "test",
            "sales_outcome": "PENDING"
        }, format="json")
        
        print("STATUS CODE:", response.status_code)
        print("RESPONSE:", response.data)
