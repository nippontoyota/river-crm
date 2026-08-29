import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.test import override_settings
from rest_framework.test import APIClient

from accounts.models import User
from complaints.models import Complaint
from leads.models import SystemConfig


@override_settings(ALLOWED_HOSTS=["testserver"])
def run_tests():
    SystemConfig.objects.update_or_create(id=1, defaults={"lists": {"branches": ["Kochi"]}})
    cre_user, _ = User.objects.get_or_create(
        email="cre_test@example.com",
        defaults={"role": User.Role.CRE, "first_name": "Test", "last_name": "CRE"},
    )
    resolver, _ = User.objects.get_or_create(
        email="resolver_test@example.com",
        defaults={"role": User.Role.COMPLAINTS, "first_name": "Complaint", "last_name": "Resolver"},
    )
    admin_user, _ = User.objects.get_or_create(
        email="admin_test@example.com",
        defaults={"role": User.Role.ADMIN, "first_name": "Test", "last_name": "Admin"},
    )

    client = APIClient()
    payload = {
        "customer_name": "John Doe",
        "customer_phone": "9876543210",
        "category": Complaint.Category.SERVICE_DELAY,
        "priority": Complaint.Priority.HIGH,
        "subject": "Late service",
        "description": "The service was delayed by 2 days.",
        "branch": "Kochi",
        "source": Complaint.Source.PHONE,
    }

    client.force_authenticate(user=cre_user)
    response = client.post("/api/complaints/", payload, format="json")
    print(f"CRE create complaint: {response.status_code}")
    complaint_id = response.json()["id"]
    print(f"CRE add note blocked: {client.post(f'/api/complaints/{complaint_id}/add-note/', {'content': 'CRE note'}, format='json').status_code}")
    print(f"CRE update blocked: {client.patch(f'/api/complaints/{complaint_id}/', {'status': Complaint.Status.IN_PROGRESS}, format='json').status_code}")

    client.force_authenticate(user=resolver)
    print(f"Resolver sees queue: {client.get('/api/complaints/').status_code}")
    print(f"Resolver add note: {client.post(f'/api/complaints/{complaint_id}/add-note/', {'content': 'Customer updated.'}, format='json').status_code}")
    print(
        "Resolver resolve: "
        f"{client.patch(f'/api/complaints/{complaint_id}/', {'status': Complaint.Status.RESOLVED, 'resolution_notes': 'Resolved.'}, format='json').status_code}"
    )

    client.force_authenticate(user=admin_user)
    analytics = client.get("/api/complaints/analytics/?range=all")
    print(f"Admin analytics: {analytics.status_code}")
    if analytics.status_code == 200:
        print(f"Resolver rows: {len(analytics.json().get('by_resolution_team', []))}")


if __name__ == "__main__":
    run_tests()
