from datetime import timedelta
from unittest.mock import patch

from django.db import transaction
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from complaints.models import Complaint
from leads.models import Lead, LeadAudit, SystemConfig
from notifications.models import Notification
from servicing.models import ServiceEvent, ServiceRequest, Vehicle
from .models import FeedbackAttempt, FeedbackIssue, FeedbackRequest, FeedbackState, FeedbackTask
from .questionnaires import QUESTIONNAIRES
from .services import record_service_event, reconcile_assignments
from .tasks import process_feedback_queue


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UpgradeTests(APITestCase):
    def setUp(self):
        self.now = timezone.now()
        self.clock = patch("django.utils.timezone.now", side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        FeedbackState.objects.update_or_create(pk=1, defaults={"activated_at": self.now - timedelta(days=1)})
        SystemConfig.objects.create(lists={"branches": ["Kochi", "Thrissur"]})
        self.admin = self.user("admin", "ADMIN")
        self.manager = self.user("manager", "SALES_MANAGER")
        self.other_manager = self.user("other-manager", "SALES_MANAGER", "Thrissur")
        self.caller = self.user("caller", "FEEDBACK")
        self.other = self.user("other", "FEEDBACK", "Thrissur")
        self.so = self.user("so", "SO")
        self.cre = self.user("cre", "CRE")
        self.service_user = self.user("service", "SERVICE")
        self.resolver = self.user("resolver", "COMPLAINTS")
        self.ceo = self.user("ceo", "CEO")
        self.lead = Lead.objects.create(name="Customer", phone="9876500123", branch="Kochi", assigned_so=self.cre, assigned_ps=self.so)
        self.vehicle = Vehicle.objects.create(chassis_number="CHASSIS01", model="Indie", customer_name="Service only", customer_phone="9876512345", created_by=self.service_user)
        self.service = ServiceRequest.objects.create(vehicle=self.vehicle, branch="Kochi", status="IN_PROGRESS", issue="Brake noise", customer_snapshot=self.vehicle.customer(), vehicle_snapshot={"model": "Indie", "chassis_number": "CHASSIS01"}, created_by=self.service_user)

    def user(self, name, role, branch="Kochi"):
        return User.objects.create_user(f"{name}@upgrade.test", "password", role=role, location=branch, first_name=name)

    def post(self, user, url, data):
        self.client.force_authenticate(user)
        return self.client.post(url, data, format="json")

    def transition(self, action):
        self.service.refresh_from_db()
        response = self.post(self.service_user, f"/api/service-requests/{self.service.pk}/{action}/", {"revision": self.service.revision, "note": f"Service {action}"})
        self.assertEqual(response.status_code, 200, response.data)
        self.service.refresh_from_db()
        return self.service.events.order_by("id").last()

    def collect(self, task, **overrides):
        self.now = max(self.now, task.next_call_at)
        return self.post(task.assigned_to, f"/api/feedback/{task.pk}/attempt/", {"revision": task.revision, "outcome": "COLLECTED", "notes": "Customer comments", "satisfaction": None, "further_help": False, "answers": {key: "YES" for key in QUESTIONNAIRES[1][task.kind]}, **overrides})

    def request_call(self, actor=None, lead=None):
        return self.post(actor or self.so, "/api/feedback-requests/", {"lead": (lead or self.lead).pk, "reason": "Please check the delivery concern", "preferred_at": (self.now + timedelta(days=1)).isoformat()})

    def test_service_only_resolution_reopen_cycles_and_atomicity(self):
        event = self.transition("resolve")
        task = FeedbackTask.objects.get(service_event=event)
        self.assertIsNone(task.lead_id)
        self.assertEqual(task.assigned_to, self.caller)
        self.assertEqual(timezone.localtime(task.next_call_at).hour, 9)
        record_service_event(event)
        self.assertEqual(FeedbackTask.objects.count(), 1)
        self.client.force_authenticate(self.caller)
        detail = self.client.get(f"/api/feedback/{task.pk}/").data
        self.assertEqual(detail["customer"], "Service only")
        self.assertEqual(detail["service"]["ticket"], self.service.ticket_number)
        self.assertEqual(self.client.get("/api/service-requests/").status_code, 403)
        self.assertEqual(self.client.get("/api/vehicles/").status_code, 403)
        self.transition("reopen")
        task.refresh_from_db()
        self.assertEqual(task.status, "CANCELLED")
        self.assertIn("reopened", task.cancellation_reason)
        second_event = self.transition("resolve")
        second = FeedbackTask.objects.get(service_event=second_event)
        self.assertEqual(self.collect(second).status_code, 200)
        self.transition("reopen")
        second.refresh_from_db()
        self.assertEqual(second.status, "COMPLETED")
        try:
            with transaction.atomic():
                self.transition("resolve")
                raise RuntimeError("rollback")
        except RuntimeError:
            pass
        self.assertEqual(FeedbackTask.objects.count(), 2)
        self.assertEqual(self.service.events.filter(action="resolve").count(), 2)

    def test_service_staffing_branch_is_independent_of_sales_branch(self):
        self.lead.branch = "Thrissur"
        self.lead.save()
        self.vehicle.related_lead = self.lead
        self.vehicle.save()
        self.transition("resolve")
        task = FeedbackTask.objects.get(kind="SVC")
        self.assertEqual(task.assigned_to, self.caller)
        self.caller.is_active = False
        self.caller.save()
        reconcile_assignments()
        task.refresh_from_db()
        self.assertIsNone(task.assigned_to)
        self.assertEqual(task.assignments.count(), 2)
        self.client.force_authenticate(self.manager)
        self.assertIn("No active", self.client.get(f"/api/feedback/{task.pk}/").data["unassigned_reason"])
        self.client.force_authenticate(self.other_manager)
        self.assertEqual(self.client.get(f"/api/feedback/{task.pk}/").status_code, 404)

    def test_requests_scope_review_duplicate_and_later_request(self):
        other_lead = Lead.objects.create(name="Other", phone="9876501111", branch="Thrissur")
        self.assertEqual(self.request_call(self.so, other_lead).status_code, 404)
        self.assertEqual(self.request_call(self.manager, other_lead).status_code, 404)
        response = self.request_call()
        self.assertEqual(response.status_code, 201, response.data)
        row = FeedbackRequest.objects.get(pk=response.data["id"])
        self.assertEqual(row.status, "PENDING")
        self.assertFalse(FeedbackTask.objects.exists())
        self.assertEqual(self.request_call(self.cre).status_code, 400)
        review = f"/api/feedback-requests/{row.pk}/review/"
        data = {"revision": row.revision, "decision": "APPROVED"}
        self.assertEqual(self.post(self.so, review, data).status_code, 403)
        self.assertEqual(self.post(self.other_manager, review, data).status_code, 404)
        self.assertEqual(self.post(self.manager, review, data).status_code, 200)
        self.assertEqual(self.post(self.admin, review, data).status_code, 400)
        task = FeedbackTask.objects.get(manual_request=row)
        self.assertEqual(task.assigned_to, self.caller)
        self.assertEqual(self.request_call(self.admin).status_code, 400)
        self.assertEqual(self.collect(task, satisfaction=1).status_code, 200)
        self.client.force_authenticate(self.so)
        data = self.client.get("/api/feedback-requests/").data
        self.assertEqual(data["results"][0]["status"], "APPROVED")
        self.assertNotIn("Customer comments", str(data))
        self.assertEqual(self.client.get(f"/api/feedback/{task.pk}/").status_code, 403)
        self.assertEqual(self.request_call(self.admin).status_code, 201)
        self.assertEqual(FeedbackTask.objects.filter(kind="GEN").count(), 2)

    def test_rejection_requires_reason_and_overdue_approval_reschedules(self):
        row = self.request_call().data
        url = f"/api/feedback-requests/{row['id']}/review/"
        self.assertEqual(self.post(self.manager, url, {"revision": 0, "decision": "REJECTED"}).status_code, 400)
        self.assertEqual(self.post(self.manager, url, {"revision": 0, "decision": "REJECTED", "review_notes": "Need more context"}).status_code, 200)
        self.assertFalse(FeedbackTask.objects.exists())
        row = self.request_call().data
        self.now += timedelta(days=2)
        url = f"/api/feedback-requests/{row['id']}/review/"
        self.assertEqual(self.post(self.manager, url, {"revision": 0, "decision": "APPROVED"}).status_code, 400)
        self.assertEqual(self.post(self.manager, url, {"revision": 0, "decision": "APPROVED", "preferred_at": (self.now + timedelta(days=1)).isoformat()}).status_code, 200)

    def test_questionnaire_validation_issue_escalation_and_review(self):
        self.transition("resolve")
        task = FeedbackTask.objects.get()
        for data in [{"answers": {}}, {"satisfaction": 0}, {"satisfaction": 6}, {"further_help": True}, {"answers": {"issue_resolved": "MAYBE"}}]:
            self.assertEqual(self.collect(task, **data).status_code, 400)
        self.assertFalse(FeedbackAttempt.objects.exists())
        result = self.collect(task, satisfaction=2, further_help=True, help_details="Please arrange repair")
        self.assertEqual(result.status_code, 200, result.data)
        task.refresh_from_db()
        self.assertEqual(task.status, "COMPLETED")
        self.assertEqual(task.issue.status, "OPEN")
        self.assertEqual(Notification.objects.filter(kind="FEEDBACK_ISSUE", user=self.manager).count(), 1)
        self.assertFalse(Notification.objects.filter(kind="FEEDBACK_ISSUE", user=self.admin).exists())
        self.now += timedelta(hours=24)
        process_feedback_queue()
        process_feedback_queue()
        self.assertEqual(Notification.objects.filter(kind="FEEDBACK_ISSUE", user=self.admin).count(), 1)
        url = f"/api/feedback/{task.pk}/issue/"
        self.assertEqual(self.post(self.other_manager, url, {"revision": task.revision, "status": "ACKNOWLEDGED", "notes": "Review"}).status_code, 404)
        response = self.post(self.manager, url, {"revision": task.revision, "status": "ACKNOWLEDGED", "notes": "Calling service team"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["issue"]["status"], "ACKNOWLEDGED")
        self.assertEqual(self.post(self.manager, url, {"revision": task.revision, "status": "RESOLVED", "notes": "Fixed"}).status_code, 400)
        task.refresh_from_db()
        response = self.post(self.manager, url, {"revision": task.revision, "status": "RESOLVED", "notes": "Repair arranged and completed"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["issue"]["events"]), 3)

    def test_service_unresolved_without_rating_and_no_manager_falls_back_to_admin(self):
        self.manager.is_active = False
        self.manager.save()
        self.transition("resolve")
        task = FeedbackTask.objects.get()
        response = self.collect(task, answers={"issue_resolved": "NO", "turnaround_acceptable": "YES", "charges_explained": "NOT_DISCUSSED"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Notification.objects.filter(kind="FEEDBACK_ISSUE", user=self.admin).count(), 1)
        self.client.force_authenticate(self.ceo)
        summary = self.client.get("/api/ceo/feedback/").data
        self.assertEqual(summary["summary"]["rated"], 0)
        self.assertIsNone(summary["summary"]["average_satisfaction"])
        self.assertEqual(summary["summary"]["issues"], 1)
        self.assertEqual(summary["coverage"]["leads_with_feedback"], 0)
        self.assertEqual(summary["customers"], 1)

    def test_complaint_is_explicit_scoped_deduplicated_and_resolution_syncs(self):
        self.transition("resolve")
        task = FeedbackTask.objects.get()
        self.assertEqual(self.collect(task, satisfaction=1).status_code, 200)
        self.assertFalse(Complaint.objects.exists())
        task.refresh_from_db()
        url = f"/api/feedback/{task.pk}/complaint/"
        data = {"revision": task.revision, "category": "AFTER_SALES", "subtype": "Unresolved repair", "description": "Repair still needed", "confirmed": True}
        self.assertEqual(self.post(self.caller, url, {**data, "confirmed": False}).status_code, 400)
        self.assertEqual(self.post(self.caller, url, {**data, "subtype": "Wrong"}).status_code, 400)
        response = self.post(self.caller, url, data)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.post(self.caller, url, data).status_code, 200)
        self.assertEqual(Complaint.objects.count(), 1)
        complaint = Complaint.objects.get()
        self.assertEqual(complaint.customer_name, "Service only")
        self.assertEqual(self.client.get(f"/api/complaints/{complaint.pk}/").status_code, 403)
        task.refresh_from_db()
        self.assertEqual(self.post(self.manager, f"/api/feedback/{task.pk}/issue/", {"revision": task.revision, "status": "RESOLVED", "notes": "Not yet"}).status_code, 400)
        self.now += timedelta(seconds=1)
        self.client.force_authenticate(self.resolver)
        response = self.client.patch(f"/api/complaints/{complaint.pk}/", {"status": "RESOLVED", "resolution_notes": "Brake replaced"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        issue = FeedbackIssue.objects.get(task=task)
        self.assertEqual(issue.status, "RESOLVED")
        self.assertEqual(issue.resolved_by, self.resolver)
        self.assertEqual(issue.resolution_notes, "Brake replaced")
        self.client.force_authenticate(self.caller)
        self.assertEqual(self.client.get(f"/api/feedback/{task.pk}/").data["complaint_status"], "RESOLVED")

    def test_historical_preview_import_recheck_dates_and_reporting(self):
        current = self.now
        self.now -= timedelta(days=10)
        audit = LeadAudit.objects.create(lead=self.lead, event="so_updated", before={"sales_outcome": "PENDING"}, after={"sales_outcome": "BOOKED"})
        service_event = self.transition("resolve")
        self.now = current
        self.assertFalse(FeedbackTask.objects.exists())
        self.client.force_authenticate(self.admin)
        response = self.client.get("/api/feedback/historical-preview/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(response.data), 2)
        self.assertFalse(FeedbackTask.objects.exists())
        selected = {"records": [f"sale:{audit.pk}"], "next_call_at": (self.now + timedelta(days=1)).isoformat()}
        url = "/api/feedback/historical-import/"
        self.assertEqual(self.post(self.manager, url, selected).status_code, 403)
        self.assertEqual(self.post(self.ceo, url, selected).status_code, 403)
        self.assertEqual(self.client.get("/api/feedback/historical-preview/").status_code, 403)
        self.assertEqual(self.post(self.admin, url, selected).status_code, 200)
        self.assertEqual(self.post(self.admin, url, selected).status_code, 200)
        self.assertEqual(FeedbackTask.objects.count(), 1)
        task = FeedbackTask.objects.get()
        self.assertEqual(task.occurred_at, audit.created_at)
        self.assertLess(task.original_due_at, self.now)
        self.assertEqual(task.origin, "HISTORICAL")
        self.assertEqual(self.collect(task, satisfaction=5).status_code, 200)
        task.refresh_from_db()
        self.assertIsNone(task.on_time)
        self.client.force_authenticate(self.ceo)
        report = self.client.get("/api/ceo/feedback/").data
        self.assertEqual(report["origins"]["HISTORICAL"]["completed"], 1)
        self.assertEqual(report["coverage"]["leads_with_feedback"], 0)
        self.assertEqual(report["summary"]["average_satisfaction"], 5)
        self.transition("reopen")
        selected["records"] = [f"service:{service_event.pk}"]
        self.assertEqual(self.post(self.admin, url, selected).status_code, 400)

    def test_contact_history_legacy_completion_and_read_only_ceo(self):
        self.request_call(self.admin)
        task = FeedbackTask.objects.get()
        task.questionnaire_version = None
        task.save()
        self.now = task.next_call_at
        response = self.post(self.caller, f"/api/feedback/{task.pk}/attempt/", {"revision": task.revision, "outcome": "COLLECTED", "notes": "Legacy feedback"})
        self.assertEqual(response.status_code, 200, response.data)
        self.request_call(self.admin)
        second = FeedbackTask.objects.order_by("pk").last()
        self.client.force_authenticate(self.caller)
        response = self.client.get(f"/api/feedback/{second.pk}/")
        self.assertEqual(response.data["contact_history"][0]["notes"], "Legacy feedback")
        self.assertEqual(self.client.get("/api/feedback/export/").status_code, 200)
        for action, data in [("reassign", {}), ("issue", {}), ("complaint", {})]:
            self.assertEqual(self.post(self.ceo, f"/api/feedback/{task.pk}/{action}/", data).status_code, 403)


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class UpgradeConcurrencyTests(TransactionTestCase):
    def setUp(self):
        FeedbackState.objects.update_or_create(pk=1, defaults={"activated_at": timezone.now() - timedelta(days=1)})
        self.caller = User.objects.create_user("caller@parallel.test", "password", role="FEEDBACK", location="Kochi")
        self.service_user = User.objects.create_user("service@parallel.test", "password", role="SERVICE", location="Kochi")
        self.admin = User.objects.create_user("admin@parallel.test", "password", role="ADMIN")
        self.lead = Lead.objects.create(name="Parallel", phone="9876500000", branch="Kochi")
        vehicle = Vehicle.objects.create(chassis_number="PARALLEL01", model="Indie", customer_name="Parallel service", customer_phone="9876501234", created_by=self.service_user)
        self.service = ServiceRequest.objects.create(vehicle=vehicle, branch="Kochi", status="IN_PROGRESS", issue="Brake noise", customer_snapshot=vehicle.customer(), vehicle_snapshot={"model": "Indie"}, created_by=self.service_user)

    def together(self, operation):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections
        from rest_framework.test import APIClient
        barrier = Barrier(2)
        def run(index):
            close_old_connections()
            try:
                client = APIClient()
                barrier.wait(timeout=10)
                return operation(client, index)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    def test_concurrent_service_resolution_creates_one_and_reopen_vs_attempt(self):
        def resolve(client, _):
            client.force_authenticate(self.service_user)
            return client.post(f"/api/service-requests/{self.service.pk}/resolve/", {"revision": 1, "note": "Repaired"}, format="json").status_code
        self.assertEqual(sorted(self.together(resolve)), [200, 409])
        task = FeedbackTask.objects.get()
        FeedbackTask.objects.filter(pk=task.pk).update(next_call_at=timezone.now() - timedelta(minutes=1))
        def reopen_or_call(client, index):
            if index:
                client.force_authenticate(self.service_user)
                return client.post(f"/api/service-requests/{self.service.pk}/reopen/", {"revision": 2, "note": "Needs more work"}, format="json").status_code
            client.force_authenticate(self.caller)
            return client.post(f"/api/feedback/{task.pk}/attempt/", {"revision": task.revision, "outcome": "COLLECTED", "notes": "Customer comment", "answers": {key: "YES" for key in QUESTIONNAIRES[1]["SVC"]}, "satisfaction": 5, "further_help": False}, format="json").status_code
        result = self.together(reopen_or_call)
        self.assertEqual(result[1], 200)
        self.assertIn(result[0], [200, 400])
        task.refresh_from_db()
        self.assertEqual(task.status, "COMPLETED" if result[0] == 200 else "CANCELLED")
        self.assertEqual(task.attempts.count(), int(result[0] == 200))

    def test_concurrent_requests_and_historical_import_are_deduplicated(self):
        def create(client, _):
            client.force_authenticate(self.admin)
            return client.post("/api/feedback-requests/", {"lead": self.lead.pk, "reason": "Check concern", "preferred_at": (timezone.now() + timedelta(days=1)).isoformat()}, format="json").status_code
        self.assertEqual(sorted(self.together(create)), [201, 400])
        self.assertEqual(FeedbackRequest.objects.count(), 1)
        self.assertEqual(FeedbackTask.objects.count(), 1)
        # Create a verified pre-activation audit without automatic task generation.
        with patch("django.utils.timezone.now", return_value=timezone.now() - timedelta(days=5)):
            audit = LeadAudit.objects.create(lead=self.lead, event="so_updated", before={"sales_outcome": "PENDING"}, after={"sales_outcome": "BOOKED"})
        def backfill(client, _):
            client.force_authenticate(self.admin)
            return client.post("/api/feedback/historical-import/", {"records": [f"sale:{audit.pk}"], "next_call_at": (timezone.now() + timedelta(days=1)).isoformat()}, format="json").status_code
        self.assertEqual(self.together(backfill), [200, 200])
        self.assertEqual(FeedbackTask.objects.filter(kind="PBF").count(), 1)

    def test_negative_feedback_does_not_deadlock_a_sales_event(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from django.db import close_old_connections
        from . import services

        audit = LeadAudit.objects.create(lead=self.lead, event="so_updated", before={"sales_outcome": "PENDING"}, after={"sales_outcome": "BOOKED"})
        task = FeedbackTask.objects.get(source_audit=audit)
        FeedbackTask.objects.filter(pk=task.pk).update(next_call_at=timezone.now() - timedelta(minutes=1))
        source_locked, feedback_locked = Event(), Event()
        original = services.ensure_issue
        def issue(*args, **kwargs):
            feedback_locked.set()
            return original(*args, **kwargs)
        def sales_event():
            close_old_connections()
            try:
                with transaction.atomic():
                    lead = Lead.objects.select_for_update().get(pk=self.lead.pk)
                    source_locked.set()
                    self.assertTrue(feedback_locked.wait(timeout=10))
                    LeadAudit.objects.create(lead=lead, event="so_updated", before={"sales_outcome": "BOOKED"}, after={"sales_outcome": "RETAILED"})
            finally:
                close_old_connections()
        def negative_call():
            close_old_connections()
            try:
                self.assertTrue(source_locked.wait(timeout=10))
                return services.save_attempt(task.pk, self.caller, {"revision": task.revision, "outcome": "COLLECTED", "notes": "Need assistance", "satisfaction": 1, "further_help": False, "answers": {key: "YES" for key in QUESTIONNAIRES[1][task.kind]}})
            finally:
                close_old_connections()
        with patch.object(services, "ensure_issue", side_effect=issue), ThreadPoolExecutor(max_workers=2) as pool:
            event_future = pool.submit(sales_event)
            call_future = pool.submit(negative_call)
            self.assertEqual(call_future.result(timeout=15).status, "COMPLETED")
            event_future.result(timeout=15)
        self.assertEqual(FeedbackTask.objects.count(), 2)
        self.assertEqual(FeedbackIssue.objects.count(), 1)
