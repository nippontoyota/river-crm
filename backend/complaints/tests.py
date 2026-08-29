from datetime import timedelta

from django.core.cache import caches
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import SystemConfig
from .models import Complaint

cache = caches["analytics"]


class ComplaintAccessTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.cre = User.objects.create_user(email="cre@example.com", password="password", role=User.Role.CRE, first_name="CRE")
        self.other_cre = User.objects.create_user(email="other-cre@example.com", password="password", role=User.Role.CRE, first_name="Other")
        self.resolver = User.objects.create_user(email="resolver@example.com", password="password", role=User.Role.COMPLAINTS, first_name="Resolver")
        self.other_resolver = User.objects.create_user(email="other-resolver@example.com", password="password", role=User.Role.COMPLAINTS, first_name="Other Resolver")
        self.admin = User.objects.create_user(email="admin@example.com", password="password", role=User.Role.ADMIN)
        self.so = User.objects.create_user(email="so@example.com", password="password", role=User.Role.SALES_OFFICER)
        self.receptionist = User.objects.create_user(email="receptionist@example.com", password="password", role=User.Role.RECEPTIONIST)
        SystemConfig.objects.create(id=1, lists={"branches": ["Kochi"]})

    def payload(self, phone="9876543210"):
        return {
            "customer_name": "Aarav Customer",
            "customer_phone": phone,
            "category": Complaint.Category.SERVICE_DELAY,
            "priority": Complaint.Priority.HIGH,
            "subject": "Service delay",
            "description": "The service is delayed.",
            "branch": "Kochi",
        }

    def test_resolver_analytics_query_budget(self):
        self.complaint()
        self.client.force_authenticate(self.resolver)

        with self.assertNumQueries(5):
            response = self.client.get("/api/complaints/analytics/?range=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Cache"], "BYPASS")

    @override_settings(CACHE_TTL_SECONDS=10)
    def test_complaint_analytics_are_cached(self):
        cache.clear()
        self.complaint()
        self.client.force_authenticate(self.resolver)

        first = self.client.get("/api/complaints/analytics/?range=all")
        with self.assertNumQueries(0):
            second = self.client.get("/api/complaints/analytics/?range=all")

        self.assertEqual(first["X-Cache"], "MISS")
        self.assertEqual(second["X-Cache"], "HIT")
        self.assertEqual(first.data, second.data)

    def complaint(self, logged_by=None, assigned_to=None, **overrides):
        data = {**self.payload(overrides.pop("phone", "9876543210")), **overrides}
        return Complaint.objects.create(logged_by=logged_by or self.cre, assigned_to=assigned_to, **data)

    def test_cre_can_create_and_only_view_own_complaints(self):
        self.client.force_authenticate(self.cre)
        created = self.client.post("/api/complaints/", self.payload(), format="json")

        self.assertEqual(created.status_code, 201)
        complaint = Complaint.objects.get(id=created.data["id"])
        self.assertEqual(complaint.logged_by, self.cre)
        self.assertIsNone(complaint.assigned_to)

        own = self.complaint(phone="9876543211", logged_by=self.cre)
        self.complaint(phone="9876543212", logged_by=self.other_cre)
        response = self.client.get("/api/complaints/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual({row["id"] for row in response.data["results"]}, {complaint.id, own.id})

    def test_cre_cannot_update_status_priority_resolution_or_notes(self):
        complaint = self.complaint()
        self.client.force_authenticate(self.cre)

        patch = self.client.patch(
            f"/api/complaints/{complaint.id}/",
            {
                "status": Complaint.Status.RESOLVED,
                "priority": Complaint.Priority.LOW,
                "resolution_notes": "Resolved.",
            },
            format="json",
        )
        note = self.client.post(f"/api/complaints/{complaint.id}/add-note/", {"content": "Called customer."}, format="json")

        self.assertEqual(patch.status_code, 403)
        self.assertEqual(note.status_code, 403)
        complaint.refresh_from_db()
        self.assertEqual(complaint.status, Complaint.Status.OPEN)
        self.assertEqual(complaint.priority, Complaint.Priority.HIGH)
        self.assertEqual(complaint.resolution_notes, "")
        self.assertIsNone(complaint.assigned_to)

    def test_complaints_department_can_view_all_add_notes_and_resolve(self):
        own = self.complaint(logged_by=self.cre)
        other = self.complaint(phone="9876543211", logged_by=self.other_cre)
        self.client.force_authenticate(self.resolver)

        response = self.client.get("/api/complaints/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)
        self.assertEqual({row["id"] for row in response.data["results"]}, {own.id, other.id})

        detail = self.client.get(f"/api/complaints/{other.id}/")
        note = self.client.post(f"/api/complaints/{other.id}/add-note/", {"content": "Customer updated."}, format="json")
        resolved = self.client.patch(
            f"/api/complaints/{other.id}/",
            {"status": Complaint.Status.RESOLVED, "priority": Complaint.Priority.MEDIUM, "resolution_notes": "Vehicle delivered."},
            format="json",
        )

        self.assertEqual(detail.status_code, 200)
        self.assertEqual(note.status_code, 201)
        self.assertEqual(resolved.status_code, 200)
        other.refresh_from_db()
        self.assertEqual(other.status, Complaint.Status.RESOLVED)
        self.assertEqual(other.priority, Complaint.Priority.MEDIUM)
        self.assertEqual(other.resolution_notes, "Vehicle delivered.")
        self.assertEqual(other.assigned_to, self.resolver)
        self.assertIsNotNone(other.resolved_at)

        self.client.force_authenticate(self.other_cre)
        cre_detail = self.client.get(f"/api/complaints/{other.id}/")
        self.assertEqual(cre_detail.status_code, 200)
        self.assertEqual([item["content"] for item in cre_detail.data["notes"]], ["Vehicle delivered.", "Customer updated."])

        self.client.force_authenticate(self.admin)
        admin_detail = self.client.get(f"/api/complaints/{other.id}/")
        self.assertEqual(admin_detail.status_code, 200)
        self.assertEqual([item["content"] for item in admin_detail.data["notes"]], ["Vehicle delivered.", "Customer updated."])

    def test_admin_can_view_and_analyze_but_not_resolve(self):
        resolved = self.complaint(assigned_to=self.resolver, status=Complaint.Status.RESOLVED, resolved_at=timezone.now())
        resolved.created_at = timezone.now() - timedelta(hours=2)
        resolved.save(update_fields=["created_at"])
        self.complaint(phone="9876543211", assigned_to=self.resolver, status=Complaint.Status.IN_PROGRESS)
        self.complaint(phone="9876543212", assigned_to=self.other_resolver, status=Complaint.Status.ESCALATED)

        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/complaints/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/complaints/{resolved.id}/").status_code, 200)
        self.assertEqual(self.client.patch(f"/api/complaints/{resolved.id}/", {"status": Complaint.Status.CLOSED, "resolution_notes": "Closed."}, format="json").status_code, 403)
        self.assertEqual(self.client.post(f"/api/complaints/{resolved.id}/add-note/", {"content": "Admin note."}, format="json").status_code, 403)
        self.assertEqual(self.client.post("/api/complaints/", self.payload("9876543213"), format="json").status_code, 403)

        analytics = self.client.get("/api/complaints/analytics/?range=all")
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(analytics.data["summary"]["total"], 3)
        self.assertIn("by_resolution_team", analytics.data)
        self.assertNotIn("by_cre", analytics.data)
        resolver_row = next(row for row in analytics.data["by_resolution_team"] if row["id"] == self.resolver.id)
        self.assertEqual(resolver_row["total"], 2)
        self.assertEqual(resolver_row["in_progress"], 1)
        self.assertEqual(resolver_row["resolved"], 1)
        self.assertEqual(resolver_row["resolution_rate"], 50.0)
        self.assertEqual(resolver_row["avg_resolution_hours"], 2.0)

        self.client.force_authenticate(self.resolver)
        resolver_analytics = self.client.get("/api/complaints/analytics/?range=all")
        self.assertEqual(resolver_analytics.status_code, 200)
        self.assertEqual(resolver_analytics.data["summary"]["total"], 3)
        self.assertNotIn("by_resolution_team", resolver_analytics.data)

    def test_sales_and_receptionist_roles_have_no_complaint_access(self):
        complaint = self.complaint()
        for user in (self.so, self.receptionist):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get("/api/complaints/").status_code, 403)
            self.assertEqual(self.client.get(f"/api/complaints/{complaint.id}/").status_code, 403)
            self.assertEqual(self.client.post("/api/complaints/", self.payload("9876543219"), format="json").status_code, 403)
            self.assertEqual(self.client.get("/api/complaints/analytics/").status_code, 403)
