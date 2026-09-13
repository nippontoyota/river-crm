from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta
from unittest.mock import patch

from django.db import close_old_connections
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APITestCase, APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from accounts.offboarding import enable_user, offboard_user, offboarding_impact
from leads.models import Lead, SystemConfig
from notifications.models import Notification
from .models import ServiceRequest, Vehicle


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ServiceWorkflowTests(APITestCase):
    def setUp(self):
        SystemConfig.objects.update_or_create(pk=1, defaults={"lists": {"branches": ["Kochi", "Thrissur"], "sources": ["Website"]}})
        self.admin = self.user("admin", "ADMIN")
        self.ceo = self.user("ceo", "CEO")
        self.ce = self.user("ce", "CRE")
        self.other_ce = self.user("other-ce", "CRE")
        self.so = self.user("so", "SO")
        self.service = self.user("service", "SERVICE")
        self.other_service = self.user("other-service", "SERVICE", "Thrissur")
        self.lead = Lead.objects.create(name="Scooter Customer", phone="9876543210", email="rider@test.local", model_interest="Indie", branch="Kochi", assigned_so=self.ce, assigned_ps=self.so, status="QUALIFIED")
        self.vehicle = Vehicle.objects.create(chassis_number="RIVER123", model="Indie", related_lead=self.lead, created_by=self.so, **{"customer_name": self.lead.name, "customer_phone": self.lead.phone})

    def user(self, name, role, branch="Kochi"):
        return User.objects.create_user(f"{name}@service.test", "password", first_name=name, role=role, location=branch)

    def create_request(self, user=None, **overrides):
        self.client.force_authenticate(user or self.ce)
        return self.client.post("/api/service-requests/", {"vehicle": self.vehicle.pk, "branch": "Kochi", "issue": "Rear brake noise", **overrides}, format="json")

    def action(self, row, action, user=None, **values):
        self.client.force_authenticate(user or self.service)
        record = ServiceRequest.objects.get(pk=row["id"])
        return self.client.post(f"/api/service-requests/{record.pk}/{action}/", {"revision": record.revision, **values}, format="json")

    def test_ce_forward_branch_resolve_and_repeat_visit_history(self):
        response = self.create_request()
        self.assertEqual(response.status_code, 201, response.data)
        row = response.data
        self.assertEqual(row["status"], "RECORDED")
        self.client.force_authenticate(self.service)
        self.assertEqual(self.client.get("/api/service-requests/").data["count"], 0)
        response = self.action(row, "forward", self.ce)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(Notification.objects.filter(user=self.service, service_request_id=row["id"]).exists())
        self.assertEqual(self.action(row, "resolve", note="Fixed").status_code, 403)
        self.assertEqual(self.action(row, "progress", status="IN_PROGRESS").status_code, 200)
        self.assertEqual(self.action(row, "progress", status="WAITING").status_code, 400)
        self.assertEqual(self.action(row, "progress", status="WAITING", note="Awaiting customer visit").status_code, 200)
        self.assertEqual(self.action(row, "resolve").status_code, 400)
        response = self.action(row, "resolve", note="Adjusted brake; road tested")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["resolved_at"])
        self.assertEqual(response.data["history"][0]["events"][-1]["note"], "Adjusted brake; road tested")
        self.client.force_authenticate(self.ce)
        self.assertEqual(self.client.get(f'/api/service-requests/{row["id"]}/').data["status"], "RESOLVED")
        next_visit = self.create_request(self.other_service, branch="Thrissur", issue="Annual service")
        self.assertEqual(next_visit.status_code, 201, next_visit.data)
        self.client.force_authenticate(self.other_service)
        history = self.client.get(f"/api/vehicles/{self.vehicle.pk}/?chassis=river123").data["history"]
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["resolution_notes"], "Adjusted brake; road tested")

    def test_roles_branch_scope_and_cross_branch_history_are_read_only(self):
        row = self.create_request(self.service).data
        self.client.force_authenticate(self.other_ce)
        self.assertEqual(self.client.get("/api/service-requests/").data["count"], 0)
        self.assertEqual(self.client.get(f'/api/service-requests/{row["id"]}/').status_code, 404)
        self.assertEqual(self.action(row, "note", self.other_ce, note="Not mine").status_code, 404)
        self.assertEqual(self.action(row, "progress", self.other_service, status="IN_PROGRESS").status_code, 404)
        self.client.force_authenticate(self.other_service)
        self.assertEqual(len(self.client.get(f"/api/vehicles/{self.vehicle.pk}/?chassis=RIVER123").data["history"]), 1)
        self.assertEqual(self.client.get(f"/api/vehicles/{self.vehicle.pk}/").status_code, 404)
        self.assertEqual(self.create_request(self.other_service).status_code, 400)
        self.assertEqual(self.action(row, "resolve", self.ceo, note="Forbidden").status_code, 403)
        self.assertEqual(self.action(row, "note", self.so, note="Forbidden").status_code, 403)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.get("/api/service-requests/").data["count"], 1)

    def test_reopen_cancel_and_intake_edits_preserve_history(self):
        row = self.create_request().data
        response = self.client.patch(f'/api/service-requests/{row["id"]}/', {"issue": "Brake and tyre", "revision": row["revision"]}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.action(row, "forward", self.ce).status_code, 200)
        self.client.force_authenticate(self.ce)
        revision = ServiceRequest.objects.get(pk=row["id"]).revision
        self.assertEqual(self.client.patch(f'/api/service-requests/{row["id"]}/', {"issue": "Changed", "revision": revision}, format="json").status_code, 403)
        self.assertEqual(self.action(row, "progress", status="IN_PROGRESS").status_code, 200)
        self.assertEqual(self.action(row, "resolve", note="Tyre inflated").status_code, 200)
        self.assertEqual(self.action(row, "reopen").status_code, 400)
        response = self.action(row, "reopen", note="Customer reports noise again")
        self.assertEqual(response.data["resolution_notes"], "")
        self.assertIn("Tyre inflated", [e["note"] for e in response.data["events"]])
        self.assertEqual(self.action(row, "cancel", note="Customer declined repair").data["status"], "CANCELLED")
        self.assertEqual(self.action(row, "progress", status="IN_PROGRESS").status_code, 403)

    def test_stale_updates_and_duplicate_requests(self):
        row = self.create_request(self.service).data
        self.assertEqual(self.create_request().status_code, 409)
        self.assertEqual(self.create_request(acknowledge_active=True, issue="Separate electrical issue").status_code, 201)
        self.assertEqual(self.action(row, "progress", status="IN_PROGRESS").status_code, 200)
        self.client.force_authenticate(self.service)
        response = self.client.post(f'/api/service-requests/{row["id"]}/resolve/', {"revision": 1, "note": "Stale resolution"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(ServiceRequest.objects.get(pk=row["id"]).status, "IN_PROGRESS")

    def test_transfer_and_staff_branch_changes_remove_old_notifications(self):
        row = self.create_request(self.service).data
        self.assertTrue(Notification.objects.filter(user=self.service, service_request_id=row["id"]).exists())
        self.assertEqual(self.action(row, "transfer", self.admin, branch="Thrissur").status_code, 400)
        self.assertEqual(self.action(row, "transfer", self.admin, branch="Thrissur", note="Customer closer to branch").status_code, 200)
        self.client.force_authenticate(self.service)
        self.assertEqual(self.client.get("/api/notifications/?service=true").data["count"], 0)
        self.client.force_authenticate(self.other_service)
        self.assertEqual(self.client.get("/api/notifications/?service=true").data["count"], 1)
        self.other_service.location = "Kochi"
        self.other_service.save()
        self.assertEqual(self.client.get("/api/notifications/?service=true").data["count"], 0)

    def test_unknown_registration_normalization_link_permissions_and_corrections(self):
        self.client.force_authenticate(self.ce)
        data = {"chassis_number": "  new 123  ", "model": "Indie", "customer_name": "Walk-in rider", "customer_phone": "9988776655"}
        response = self.client.post("/api/vehicles/", data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["chassis_number"], "NEW123")
        self.assertEqual(self.client.post("/api/vehicles/", {**data, "chassis_number": "new123"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f'/api/vehicles/{response.data["id"]}/', {"chassis_number": "BAD"}, format="json").status_code, 400)
        self.client.force_authenticate(self.other_ce)
        self.assertEqual(self.client.post("/api/vehicles/", {**data, "chassis_number": "UNAUTHORIZED", "related_lead": self.lead.pk}, format="json").status_code, 400)
        row = self.create_request().data
        self.lead.name = "Updated CRM Name"
        self.lead.save()
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get(f"/api/vehicles/{self.vehicle.pk}/").data["customer_name"], "Updated CRM Name")
        correction = self.client.patch(f"/api/vehicles/{self.vehicle.pk}/", {"chassis_number": "CORRECT123", "reason": "Corrected transposed number"}, format="json")
        self.assertEqual(correction.status_code, 200, correction.data)
        self.assertEqual(self.vehicle.events.count(), 1)
        self.assertEqual(self.client.get(f'/api/service-requests/{row["id"]}/').data["vehicle_snapshot"]["chassis_number"], "RIVER123")
        self.assertEqual(self.client.get(f'/api/service-requests/{row["id"]}/').data["customer_snapshot"]["customer_name"], "Scooter Customer")

    def test_retail_requires_vehicle_all_entrypoints_and_legacy_can_be_backfilled(self):
        self.vehicle.related_lead = None
        self.vehicle.save()
        self.client.force_authenticate(self.so)
        booking = self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {"call_status": "Connected", "call_outcome": "Booking Done", "remarks": "Booking accepted", "follow_up_at": (timezone.now() + timedelta(days=1)).isoformat()}, format="json")
        self.assertEqual(booking.status_code, 200, booking.data)
        self.assertEqual(booking.data["sales_outcome"], "BOOKED")
        payload = {"call_status": "Connected", "call_outcome": "Retail Done", "remarks": "Delivered scooter"}
        for action in ["so-update", "log-call"]:
            response = (self.client.patch if action == "so-update" else self.client.post)(f"/api/leads/{self.lead.pk}/{action}/", payload, format="json")
            self.assertEqual(response.status_code, 400, response.data)
            self.assertIn("chassis_number", response.data)
        self.client.force_authenticate(self.ce)
        self.assertEqual(self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {"status": "WON", "sales_outcome": "RETAILED"}, format="json").status_code, 400)
        self.client.force_authenticate(self.so)
        response = self.client.post("/api/vehicles/", {"chassis_number": "SALE123", "model": "Indie", "related_lead": self.lead.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sales_outcome"], "RETAILED")
        legacy = Lead.objects.create(name="Legacy sale", phone="8877665544", assigned_ps=self.so, status="WON", sales_outcome="RETAILED")
        self.assertEqual(self.client.post("/api/vehicles/", {"chassis_number": "LEGACY123", "model": "Indie", "related_lead": legacy.pk}, format="json").status_code, 201)

    def test_service_account_access_creation_and_lifecycle(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/auth/users/", {"email": "new@service.test", "password": "password", "role": "SERVICE", "location": "Unknown"}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/auth/users/", {"email": "new@service.test", "password": "password", "role": "SERVICE", "location": " kochi "}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["location"], "Kochi")
        token = str(RefreshToken.for_user(self.service).access_token)
        self.client.force_authenticate(user=None)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        for path in ["/api/leads/", "/api/feedback/", "/api/auth/sales-officers/", "/api/complaints/"]:
            self.assertEqual(self.client.get(path).status_code, 403, path)
        self.assertEqual(self.client.get("/api/system-config/").status_code, 200)
        self.client.credentials()
        row = self.create_request(self.service).data
        preview = offboarding_impact(self.service)
        offboard_user(self.service.pk, self.admin, "DISABLED", preview["version"], [])
        self.service.refresh_from_db()
        self.assertFalse(self.service.is_active)
        self.client.force_authenticate(self.service)
        self.assertEqual(self.client.get("/api/service-requests/").status_code, 403)
        enable_user(self.service.pk, self.admin)
        self.service.refresh_from_db()
        offboard_user(self.service.pk, self.admin, "DELETED", offboarding_impact(self.service)["version"], [], "Employee left")
        self.assertTrue(ServiceRequest.objects.filter(pk=row["id"]).exists())
        self.assertEqual(ServiceRequest.objects.get(pk=row["id"]).events.count(), 1)

    def test_unstaffed_branch_and_invalid_requests(self):
        self.other_service.is_active = False
        self.other_service.save()
        row = self.create_request(branch="Thrissur").data
        result = self.action(row, "forward", self.ce)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertFalse(result.data["branch_staff_available"])
        self.assertEqual(self.create_request(branch="Invalid").status_code, 400)
        self.assertEqual(self.create_request(odometer=-1).status_code, 400)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ServiceConcurrencyTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_chassis_registration_returns_one_record(self):
        users = [User.objects.create_user(f"racer{index}@service.test", role="CRE") for index in range(2)]
        barrier = Barrier(2)
        from .views import VehicleViewSet
        original = VehicleViewSet.perform_create

        def synchronized(view, serializer):
            barrier.wait(timeout=10)
            return original(view, serializer)

        def register(user):
            close_old_connections()
            try:
                client = APIClient()
                client.force_authenticate(user)
                return client.post("/api/vehicles/", {"chassis_number": "RACE123", "model": "Indie", "customer_name": "Rider", "customer_phone": "9876543210"}, format="json").status_code
            finally:
                close_old_connections()

        with patch.object(VehicleViewSet, "perform_create", synchronized), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(register, users))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(Vehicle.objects.filter(chassis_number="RACE123").count(), 1)
