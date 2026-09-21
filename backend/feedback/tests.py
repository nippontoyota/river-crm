from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch

from django.db import transaction
from django.test import TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User
from accounts.offboarding import enable_user, offboard_user, offboarding_impact
from leads.models import Lead, LeadAudit
from notifications.models import Notification
from .questionnaires import QUESTIONNAIRES
from .models import FeedbackAttempt, FeedbackState, FeedbackTask
from .services import morning_after, record_audit, reconcile_assignments
from .tasks import process_feedback_queue


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FeedbackWorkflowTests(APITestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 12, 5, 0, tzinfo=dt_timezone.utc)
        self.clock = patch("django.utils.timezone.now", side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        FeedbackState.objects.update_or_create(pk=1, defaults={"activated_at": self.now - timedelta(days=1)})
        self.admin = self.user("admin", "ADMIN")
        self.ceo = self.user("ceo", "CEO")
        self.manager = self.user("manager", "SALES_MANAGER")
        self.caller = self.user("caller", "FEEDBACK")
        self.second = self.user("second", "FEEDBACK")
        self.other = self.user("other", "FEEDBACK", "Thrissur")
        self.so = self.user("so", "SO")
        self.cre = self.user("cre", "CRE")
        self.lead = Lead.objects.create(name="Feedback Customer", phone="9876500000", branch=" Kochi ",
            assigned_so=self.cre, assigned_ps=self.so, status="QUALIFIED")

    def user(self, name, role, branch="Kochi"):
        return User.objects.create_user(f"{name}@test.local", "password", first_name=name, role=role, location=branch)

    def event(self, kind, lead=None, bulk=False):
        lead = lead or self.lead
        if kind == "TDF":
            lead.test_drive_completed_at = self.now
            lead.save(update_fields=["test_drive_completed_at"])
            audit = LeadAudit(lead=lead, actor=self.so, event="test_drive_completed")
        else:
            before = lead.sales_outcome
            lead.sales_outcome = {"PBF": "BOOKED", "PSF": "RETAILED"}[kind]
            lead.save(update_fields=["sales_outcome"])
            audit = LeadAudit(lead=lead, actor=self.so, event="so_updated", before={"sales_outcome": before}, after={"sales_outcome": lead.sales_outcome})
        if bulk:
            LeadAudit.objects.bulk_create([audit])
        else:
            audit.save()
        return FeedbackTask.objects.get(lead=lead, kind=kind)

    def attempt(self, task, outcome="NO_ANSWER", **extra):
        task.refresh_from_db()
        if outcome == "COLLECTED":
            extra = {"answers": {key: "YES" for key in QUESTIONNAIRES[1][task.kind]}, "satisfaction": None, "further_help": False, **extra}
        self.client.force_authenticate(task.assigned_to)
        return self.client.post(f"/api/feedback/{task.pk}/attempt/", {"revision": task.revision, "outcome": outcome, **extra}, format="json")

    def test_events_dates_and_duplicate_delivery(self):
        tasks = [self.event(kind, bulk=kind == "PSF") for kind in ["TDF", "PBF", "PSF"]]
        for task in tasks:
            local = timezone.localtime(task.original_due_at)
            self.assertEqual((local.day, local.hour), (15 if task.kind == "PSF" else 13, 9))
            record_audit(task.source_audit)
        self.assertEqual(FeedbackTask.objects.count(), 3)
        self.assertEqual([task.assigned_to_id for task in tasks], [self.caller.id, self.second.id, self.caller.id])
        self.lead.status, self.lead.sales_outcome = "LOST", "LOST"
        self.lead.save()
        self.assertEqual(FeedbackTask.objects.filter(status="OPEN").count(), 3)
        boundary = datetime(2026, 12, 31, 18, 29, tzinfo=dt_timezone.utc)
        self.assertEqual(timezone.localtime(morning_after(boundary)).isoformat(), "2027-01-01T09:00:00+05:30")

    def test_no_appointment_or_historical_backfill_or_inferred_booking(self):
        LeadAudit.objects.create(lead=self.lead, event="status_changed", before={"status": "QUALIFIED"}, after={"status": "WALKIN"})
        self.assertFalse(FeedbackTask.objects.exists())
        self.event("PSF")
        self.assertFalse(FeedbackTask.objects.filter(kind="PBF").exists())
        self.now -= timedelta(days=10)
        self.event_audit_only = LeadAudit.objects.create(lead=self.lead, event="so_updated", before={"sales_outcome": "PENDING"}, after={"sales_outcome": "BOOKED"})
        self.assertFalse(FeedbackTask.objects.filter(kind="PBF").exists())

    def test_three_attempts_retry_and_duplicate_submission(self):
        task = self.event("TDF")
        self.assertEqual(self.attempt(task).status_code, 400)
        for attempt_number in range(3):
            task.refresh_from_db()
            self.now = task.next_call_at + timedelta(hours=1)
            revision = task.revision
            response = self.attempt(task)
            self.assertEqual(response.status_code, 200, response.data)
            duplicate = self.client.post(f"/api/feedback/{task.pk}/attempt/", {"revision": revision, "outcome": "NO_ANSWER"}, format="json")
            self.assertEqual(duplicate.status_code, 400)
        task.refresh_from_db()
        self.assertEqual(task.status, "UNREACHABLE")
        self.assertEqual(task.attempts.count(), 3)
        self.assertEqual(task.unsuccessful_attempts, 3)

    def test_callback_completion_and_required_notes(self):
        task = self.event("PBF")
        self.now = task.next_call_at
        self.assertEqual(self.attempt(task, "CALLBACK").status_code, 400)
        callback = self.now + timedelta(days=2)
        self.assertEqual(self.attempt(task, "CALLBACK", callback_at=callback.isoformat()).status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.unsuccessful_attempts, 0)
        self.now = callback
        self.assertEqual(self.attempt(task, "COLLECTED").status_code, 400)
        self.assertEqual(self.attempt(task, "COLLECTED", notes="Booking was straightforward.").status_code, 200)
        task.refresh_from_db()
        self.assertFalse(task.on_time)
        self.assertEqual(task.original_due_at, morning_after(task.occurred_at))

    def test_permissions_and_notifications_do_not_leak(self):
        task = self.event("TDF")
        self.now = task.next_call_at
        self.attempt(task, "COLLECTED", notes="Private feedback text")
        for user in [self.cre, self.so]:
            self.client.force_authenticate(user)
            for path in ["/api/feedback/", "/api/feedback/summary/", "/api/feedback/export/", f"/api/feedback/{task.pk}/"]:
                self.assertEqual(self.client.get(path).status_code, 403)
            self.assertNotIn("Private feedback text", str(self.client.get(f"/api/leads/{self.lead.pk}/").data))
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f"/api/feedback/{task.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/feedback/").data["count"], 0)
        self.client.force_authenticate(self.caller)
        self.assertEqual(self.client.get("/api/leads/").status_code, 403)
        self.assertEqual(self.client.get("/api/auth/sales-officers/").status_code, 403)
        self.client.force_authenticate(self.ceo)
        self.assertEqual(self.client.get(f"/api/feedback/{task.pk}/").status_code, 200)
        self.assertEqual(self.client.post(f"/api/feedback/{task.pk}/attempt/", {}).status_code, 403)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get(f"/api/feedback/{task.pk}/").status_code, 200)

    def test_branch_transfer_staffing_and_missing_branch(self):
        task = self.event("TDF")
        self.lead.branch = "Thrissur"
        self.lead.save()
        LeadAudit.objects.create(lead=self.lead, event="details_updated", before={"branch": " Kochi "}, after={"branch": "Thrissur"})
        task.refresh_from_db()
        self.assertEqual(task.assigned_to, self.other)
        self.assertFalse(Notification.objects.filter(user=self.caller, feedback_task=task).exists())
        self.lead.branch = ""
        self.lead.save()
        reconcile_assignments()
        task.refresh_from_db()
        self.assertIsNone(task.assigned_to)
        self.lead.branch = "New Branch"
        self.lead.save()
        reconcile_assignments()
        new_caller = self.user("new", "FEEDBACK", "New Branch")
        reconcile_assignments()
        task.refresh_from_db()
        self.assertEqual(task.assigned_to, new_caller)

    def test_offboarding_reassigns_open_preserves_completed(self):
        completed = self.event("TDF")
        self.now = completed.next_call_at
        self.attempt(completed, "COLLECTED", notes="Good drive")
        pending = self.event("PBF")
        self.assertEqual(pending.assigned_to, self.caller)
        preview = offboarding_impact(self.caller)
        offboard_user(self.caller.pk, self.admin, "DISABLED", preview["version"], [])
        pending.refresh_from_db()
        completed.refresh_from_db()
        self.assertEqual(pending.assigned_to, self.second)
        self.assertEqual(completed.assigned_to, self.caller)
        self.assertEqual(completed.attempts.first().caller, self.caller)
        enable_user(self.caller.pk, self.admin)

    def test_notifications_deduplicate_and_reads_do_not_complete(self):
        task = self.event("TDF")
        self.now = task.next_call_at
        process_feedback_queue()
        process_feedback_queue()
        self.assertEqual(Notification.objects.filter(feedback_task=task).count(), 2)
        self.client.force_authenticate(self.caller)
        self.assertEqual(self.client.get("/api/notifications/unread_count/?feedback=true").data["count"], 2)
        self.client.post("/api/notifications/mark_read/?feedback=true")
        task.refresh_from_db()
        self.assertEqual(task.status, "OPEN")
        self.now += timedelta(days=1)
        process_feedback_queue()
        process_feedback_queue()
        self.assertEqual(Notification.objects.filter(feedback_task=task, kind="FEEDBACK_OVERDUE").count(), 1)

    def test_reports_export_and_original_due_cohort(self):
        first = self.event("TDF")
        self.event("PBF")
        self.now = first.next_call_at
        self.attempt(first, "COLLECTED", notes="Good")
        self.client.force_authenticate(self.ceo)
        data = self.client.get("/api/ceo/feedback/?range=all").data
        self.assertEqual(data["summary"]["total"], 2)
        self.assertEqual(data["summary"]["completion_rate"], 50)
        self.assertEqual(data["coverage"], {"leads_with_feedback": 1, "all_leads": 1})
        self.assertEqual(data["activity"]["attempts"], 1)
        self.assertEqual(sum(t["total"] for t in data["types"]), 2)
        self.assertEqual(self.client.get("/api/feedback/export/?kind=TDF").status_code, 200)
        self.assertEqual(self.client.get("/api/feedback/?bucket=completed").data["count"], 1)
        self.assertEqual(self.client.get("/api/feedback/summary/?caller=oops").status_code, 400)

    def test_feedback_user_branch_required_and_cross_branch_reassign_denied(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/auth/users/", {"email": "bad@test.local", "password": "password", "role": "FEEDBACK"}, format="json")
        self.assertEqual(response.status_code, 400)
        task = self.event("TDF")
        self.client.force_authenticate(self.manager)
        response = self.client.post(f"/api/feedback/{task.pk}/reassign/", {"revision": task.revision, "assigned_to": self.other.pk}, format="json")
        self.assertEqual(response.status_code, 404)
        response = self.client.post(f"/api/feedback/{task.pk}/reassign/", {"revision": task.revision, "assigned_to": self.second.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)

    def test_trigger_and_task_rollback_together(self):
        try:
            with transaction.atomic():
                self.event("TDF")
                raise ValueError("rollback")
        except ValueError:
            pass
        self.assertFalse(FeedbackTask.objects.exists())
        self.assertFalse(LeadAudit.objects.filter(event="test_drive_completed").exists())

    def test_sales_actions_generate_tasks_without_changing_ownership(self):
        self.client.force_authenticate(self.so)
        response = self.client.post(f"/api/leads/{self.lead.pk}/complete-test-drive/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(FeedbackTask.objects.filter(lead=self.lead, kind="TDF").exists())
        response = self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {
            "call_status": "Connected", "call_outcome": "Booking Done", "remarks": "Customer confirmed booking.",
            "follow_up_at": (self.now + timedelta(days=2)).isoformat()}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(FeedbackTask.objects.filter(lead=self.lead, kind="PBF").exists())
        self.lead.refresh_from_db()
        self.assertEqual((self.lead.assigned_so, self.lead.assigned_ps), (self.cre, self.so))

    def test_caller_move_and_delete_preserve_history(self):
        task = self.event("TDF")
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/auth/users/{self.caller.pk}/", {"location": "Thrissur"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        task.refresh_from_db()
        self.assertEqual(task.assigned_to, self.second)
        response = self.client.patch(f"/api/auth/users/{self.caller.pk}/", {"location": ""}, format="json")
        self.assertEqual(response.status_code, 400)
        self.now = task.next_call_at
        self.attempt(task, "DECLINED", notes="Customer does not want feedback calls.")
        preview = offboarding_impact(self.second)
        offboard_user(self.second.pk, self.admin, "DELETED", preview["version"], [], "Employee left")
        task.refresh_from_db()
        self.assertEqual(task.status, "DECLINED")
        self.assertIsNotNone(task.attempts.first().caller.deleted_at)


@skipUnlessDBFeature("has_select_for_update")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FeedbackConcurrencyTests(TransactionTestCase):
    def test_concurrent_distribution_and_duplicate_attempt(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import close_old_connections
        from rest_framework.exceptions import ValidationError
        from .services import save_attempt

        FeedbackState.objects.update_or_create(pk=1, defaults={"activated_at": timezone.now() - timedelta(days=1)})
        callers = [User.objects.create_user(f"concurrent{i}@test.local", "password", role="FEEDBACK", location="Kochi") for i in range(2)]
        barrier = Barrier(2)

        def generate(index):
            close_old_connections()
            try:
                lead = Lead.objects.create(name=f"Concurrent {index}", phone=f"987660000{index}", branch="Kochi", sales_outcome="BOOKED")
                barrier.wait(timeout=10)
                with transaction.atomic():
                    LeadAudit.objects.create(lead=lead, event="so_updated", before={"sales_outcome": "PENDING"}, after={"sales_outcome": "BOOKED"})
                return FeedbackTask.objects.get(lead=lead).pk
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(generate, range(2)))
        self.assertEqual(set(FeedbackTask.objects.values_list("assigned_to_id", flat=True)), {c.pk for c in callers})
        task = FeedbackTask.objects.select_related("assigned_to").get(pk=ids[0])
        task.next_call_at = timezone.now() - timedelta(minutes=1)
        task.save(update_fields=["next_call_at"])

        def attempt(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                try:
                    save_attempt(task.pk, task.assigned_to, {"revision": task.revision, "outcome": "COLLECTED", "notes": "Collected once", "answers": {key: "YES" for key in QUESTIONNAIRES[1][task.kind]}, "satisfaction": None, "further_help": False})
                    return "saved"
                except ValidationError:
                    return "stale"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(attempt, range(2))), ["saved", "stale"])
        self.assertEqual(FeedbackAttempt.objects.filter(task=task).count(), 1)
