from datetime import timedelta
from uuid import uuid4

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.cache import cache
from django.db import connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from complaints.models import Complaint, ComplaintNote
from servicing.models import ServiceRequest, Vehicle
from .models import CallLog, FollowUp, InboundInteraction, Lead, SystemConfig


class CallCenterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ce = User.objects.create_user(email="answer@example.test", role="CRE", first_name="Answering CE")
        cls.owner = User.objects.create_user(email="owner@example.test", role="CRE", first_name="Assigned CE")
        cls.ps = User.objects.create_user(email="ps@example.test", role="SO", location="Kochi")
        cls.admin = User.objects.create_user(email="admin@example.test", role="ADMIN")
        cls.lead = Lead.objects.create(name="Shared Customer", phone="9876543210", assigned_so=cls.owner, branch="Kochi", city="Kochi")
        SystemConfig.objects.create(id=1, lists={"branches": ["Kochi"], "models": ["Indie"], "colorVariants": ["Blue"], "sources": ["WEBSITE"]})

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()
        self.client.force_authenticate(self.ce)

    def detail(self):
        response = self.client.get(f"/api/call-center/leads/{self.lead.pk}/")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def payload(self, **values):
        self.lead.refresh_from_db()
        return {"submission_id": str(uuid4()), "kind": "NOTE", "lead_id": self.lead.pk,
                "lead_version": self.lead.updated_at.isoformat(), "confirm_customer": True,
                "caller_phone": "+91 91234 56789", "caller_name": "Caller", "reason": "Returning missed call",
                "notes": "Customer requests assistance", **values}

    def post(self, payload):
        return self.client.post("/api/call-center/interactions/", payload, format="json")

    def test_shared_read_search_and_personal_scope(self):
        self.assertEqual(self.detail()["assigned_so"], self.owner.pk)
        self.assertTrue(self.detail()["outcome_policy"]["can_update"])
        self.assertEqual(self.client.get(f"/api/leads/{self.lead.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/leads/").data["count"], 0)
        self.assertEqual(self.client.get("/api/leads/my-dashboard/?section=all").data["results"], [])
        for mode, value in [("phone", "+91 98765 43210"), ("name", "shared"), ("lead_id", f"#{self.lead.pk:06d}")]:
            result = self.client.get("/api/leads/customer-lookup/", {"search_by": mode, "query": value})
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual(result.data["count"], 1)
            self.assertTrue(result.data["results"][0]["can_open"])
        for mode, value in [("name", "ab"), ("phone", "123"), ("lead_id", "no"), ("invalid", "test")]:
            self.assertEqual(self.client.get("/api/leads/customer-lookup/", {"search_by": mode, "query": value}).status_code, 400)

    def test_inbound_record_changes_neither_ownership_progress_nor_reminders(self):
        old = FollowUp.objects.create(lead=self.lead, so=self.owner, scheduled_for=timezone.now() + timedelta(days=1))
        response = self.post(self.payload())
        self.assertEqual(response.status_code, 201, response.data)
        self.lead.refresh_from_db(); old.refresh_from_db()
        self.assertEqual((self.lead.assigned_so_id, self.lead.assigned_ps_id, self.lead.status, self.lead.phone), (self.owner.pk, None, "FRESH", "9876543210"))
        self.assertIsNone(old.resolved_at)
        self.assertEqual(CallLog.objects.count(), 0)
        self.assertEqual(response.data["caller_phone"], "9123456789")
        self.assertEqual(response.data["handled_by"], self.ce.pk)
        self.assertEqual(self.client.get("/api/call-center/summary/").data["inbound_calls_today"], 1)
        self.assertEqual(self.detail()["call_count"], 0)

    def test_idempotency_and_changed_payload_rejection(self):
        payload = self.payload(kind="CALLBACK", callback_at=(timezone.now() + timedelta(hours=1)).isoformat())
        first = self.post(payload)
        second = self.post(payload)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(FollowUp.objects.count(), 1)
        self.assertEqual(InboundInteraction.objects.count(), 1)
        self.assertEqual(self.post({**payload, "notes": "Changed"}).status_code, 409)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.post(payload).status_code, 409)

    def test_callbacks_go_to_owner_and_are_visible_independent_of_lead_status(self):
        at = (timezone.now() + timedelta(hours=1)).isoformat()
        result = self.post(self.payload(kind="CALLBACK", callback_at=at))
        self.assertEqual(result.status_code, 201, result.data)
        followup = FollowUp.objects.get()
        self.assertEqual(followup.so_id, self.owner.pk)
        self.assertEqual(followup.origin, "INBOUND")
        self.assertEqual(self.client.get("/api/call-center/callbacks/").data["count"], 0)
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get("/api/call-center/callbacks/").data["count"], 1)
        self.client.force_authenticate(self.ce)
        Lead.objects.filter(pk=self.lead.pk).update(status="WON", assigned_ps=self.ps)
        result = self.post(self.payload(kind="CALLBACK", callback_at=at))
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(FollowUp.objects.get(pk=result.data["follow_up_id"]).so_id, self.ps.pk)
        self.client.force_authenticate(self.ps)
        task = self.client.get("/api/call-center/callbacks/").data["results"][0]
        result = self.client.post("/api/call-center/callbacks/", self.payload(kind="CALLBACK_COMPLETE", follow_up_id=task["id"], follow_up_version=task["version"]), format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(self.client.get("/api/call-center/callbacks/").data["count"], 0)
        self.assertIsNone(FollowUp.objects.get(pk=followup.pk).resolved_at)

    def test_explicit_callback_reschedule_and_stale_version(self):
        self.post(self.payload(kind="CALLBACK", callback_at=(timezone.now() + timedelta(hours=1)).isoformat()))
        task = self.detail()["callbacks"][0]
        payload = self.payload(kind="CALLBACK_RESCHEDULE", follow_up_id=task["id"], follow_up_version=task["version"], callback_at=(timezone.now() + timedelta(hours=2)).isoformat())
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertEqual(self.post({**payload, "submission_id": str(uuid4())}).status_code, 409)
        self.assertEqual(FollowUp.objects.get().so_id, self.owner.pk)

    def test_unmatched_and_inactive_routing_review(self):
        response = self.post(self.payload(lead_id=None, kind="SERVICE"))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["state"], "UNMATCHED")
        self.assertEqual(Lead.objects.count(), 1)
        User.objects.filter(pk=self.owner.pk).update(is_active=False)
        waiting = self.post(self.payload(kind="CALLBACK", callback_at=(timezone.now() + timedelta(hours=1)).isoformat()))
        self.assertEqual(waiting.data["state"], "AWAITING_ROUTING")
        self.assertEqual(FollowUp.objects.count(), 0)
        self.assertEqual(self.client.get("/api/call-center/interactions/?pending=true").status_code, 403)
        review = self.payload(kind="REVIEW", interaction_id=waiting.data["id"], interaction_version=waiting.data["updated_at"], review_state="RECORDED", callback_at=(timezone.now() + timedelta(hours=2)).isoformat())
        self.assertEqual(self.post(review).status_code, 403)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.client.get("/api/call-center/interactions/?pending=true").data["count"], 2)
        self.assertEqual(self.post(review).status_code, 400)
        User.objects.filter(pk=self.owner.pk).update(is_active=True)
        self.assertEqual(self.post(review).status_code, 201)
        self.assertEqual(FollowUp.objects.get().so_id, self.owner.pk)

    def test_shared_updates_are_versioned_and_preserve_owners_and_outbound_counts(self):
        url = f"/api/call-center/leads/{self.lead.pk}/"
        payload = {"submission_id": str(uuid4()), "lead_version": self.detail()["updated_at"], "name": "Corrected name"}
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.patch(url, payload, format="json").status_code, 200)
        self.assertEqual(self.client.patch(url, {**payload, "submission_id": str(uuid4())}, format="json").status_code, 409)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_so_id, self.owner.pk)
        self.assertEqual(self.lead.name, "Corrected name")
        self.assertEqual(CallLog.objects.count(), 0)
        self.assertEqual(self.client.get("/api/call-center/summary/").data["inbound_calls_today"], 0)
        for field, value in [("assigned_so", self.ce.pk), ("assigned_ps", self.ps.pk), ("follow_up_at", timezone.now().isoformat())]:
            result = self.client.patch(url, {"submission_id": str(uuid4()), "lead_version": self.detail()["updated_at"], field: value}, format="json")
            self.assertEqual(result.status_code, 400, result.data)

    def test_first_qualification_and_existing_ps_protection(self):
        url = f"/api/call-center/leads/{self.lead.pk}/"
        payload = {"submission_id": str(uuid4()), "lead_version": self.detail()["updated_at"], "status": "QUALIFIED", "call_outcome": "QUALIFIED", "ps_officer_id": self.ps.pk, "city": "Kochi", "branch": "Kochi", "qualification": {"variant": "Blue", "notes": "Qualified by answering CE"}}
        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["assigned_ps"], self.ps.pk)
        self.assertEqual(response.data["assigned_so"], self.owner.pk)
        other = User.objects.create_user(email="otherps@example.test", role="SO", location="Kochi")
        response = self.client.patch(url, {"submission_id": str(uuid4()), "lead_version": self.detail()["updated_at"], "ps_officer_id": other.pk}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_outbound_update_does_not_clear_inbound_tasks(self):
        row = self.post(self.payload(kind="CALLBACK", callback_at=(timezone.now() + timedelta(hours=1)).isoformat()))
        self.client.force_authenticate(self.owner)
        result = self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {"call_outcome": "LOST", "status": "LOST", "remarks": "No purchase"}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertIsNone(FollowUp.objects.get(pk=row.data["follow_up_id"]).resolved_at)

    def test_ticket_creation_linking_repeat_notes_and_duplicate_protection(self):
        values = {"category": "AFTER_SALES", "subtype": "No callback", "branch": "Kochi", "subject": "Please call back", "description": "Waiting", "priority": "MEDIUM"}
        payload = self.payload(kind="COMPLAINT", complaint=values)
        result = self.post(payload)
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(self.post(payload).data["complaint_id"], result.data["complaint_id"])
        ticket = Complaint.objects.get()
        self.assertEqual((ticket.logged_by_id, ticket.related_lead_id), (self.ce.pk, self.lead.pk))
        self.assertEqual(self.post(self.payload(kind="COMPLAINT", complaint=values)).status_code, 409)
        self.client.force_authenticate(self.owner)
        listing = self.client.get(f"/api/call-center/leads/{self.lead.pk}/tickets/")
        self.assertEqual(listing.status_code, 200, listing.data)
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(self.client.get(f"/api/call-center/leads/{self.lead.pk}/tickets/?ticket_id={ticket.pk}").data["count"], 1)
        self.assertEqual(self.client.get(f"/api/call-center/leads/{self.lead.pk}/tickets/?ticket_id={ticket.pk + 1}").data["count"], 0)
        note = self.payload(kind="COMPLAINT_NOTE", ticket_id=ticket.pk, ticket_version=ticket.updated_at.isoformat(), confirm_ticket=True)
        self.assertEqual(self.post(note).status_code, 201)
        self.assertEqual(self.post(note).status_code, 201)
        self.assertEqual(ComplaintNote.objects.count(), 1)
        self.assertEqual(self.post({**note, "submission_id": str(uuid4())}).status_code, 409)
        self.assertEqual(self.client.patch(f"/api/complaints/{ticket.pk}/", {"status": "RESOLVED"}, format="json").status_code, 403)

    def test_service_intake_and_customer_messages_preserve_department_progress(self):
        Lead.objects.filter(pk=self.lead.pk).update(status="WON", sales_outcome="RETAILED", assigned_ps=self.ps)
        vehicle = Vehicle.objects.create(chassis_number="CC-001", model="Indie", related_lead=self.lead, created_by=self.ps, customer_name=self.lead.name, customer_phone=self.lead.phone)
        payload = self.payload(kind="SERVICE", service={"vehicle": vehicle.pk, "branch": "Kochi", "issue": "Repair request"})
        response = self.post(payload)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.post(payload).status_code, 201)
        self.assertEqual(self.post(self.payload(kind="SERVICE", service={"vehicle": "not-an-id"})).status_code, 400)
        ticket = ServiceRequest.objects.get()
        self.assertEqual(ticket.status, "FORWARDED")
        self.assertEqual(ticket.created_by_id, self.ce.pk)
        self.assertEqual(self.post(self.payload(kind="SERVICE", service=payload["service"])).status_code, 409)
        listing = self.client.get(f"/api/call-center/leads/{self.lead.pk}/tickets/?kind=service")
        self.assertEqual(listing.status_code, 200, listing.data)
        note = self.payload(kind="SERVICE_NOTE", ticket_id=ticket.pk, ticket_version=str(ticket.revision), confirm_ticket=True)
        self.assertEqual(self.post(note).status_code, 201)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, "FORWARDED")
        self.assertEqual(ticket.events.filter(action="note").count(), 1)

    def test_legacy_phone_ticket_requires_confirmation_and_foreign_ticket_is_denied(self):
        ticket = Complaint.objects.create(customer_name="Legacy", customer_phone=self.lead.phone, category="OTHER", subject="Legacy", description="Old", logged_by=self.owner)
        payload = self.payload(kind="COMPLAINT_NOTE", ticket_id=ticket.pk, ticket_version=ticket.updated_at.isoformat())
        self.assertEqual(self.post(payload).status_code, 400)
        ticket.customer_phone = "9000000000"; ticket.save()
        payload.update(confirm_ticket=True, ticket_version=ticket.updated_at.isoformat())
        self.assertEqual(self.post(payload).status_code, 403)
        self.assertFalse(ComplaintNote.objects.exists())

    def test_stale_deleted_unconfirmed_and_unrelated_roles(self):
        stale = self.payload()
        self.lead.name = "New name"; self.lead.save()
        self.assertEqual(self.post(stale).status_code, 409)
        self.assertEqual(self.post(self.payload(confirm_customer=False)).status_code, 400)
        for role in User.Role.values:
            if role in {"CRE", "ADMIN"}:
                continue
            user = User.objects.create_user(email=f"role-{role}@example.test", role=role)
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get(f"/api/call-center/leads/{self.lead.pk}/").status_code, 403)
            self.assertEqual(self.post(self.payload()).status_code, 403)
        self.client.force_authenticate(self.ce)
        self.lead.deleted_at = timezone.now(); self.lead.save()
        self.assertEqual(self.post(self.payload()).status_code, 404)


@skipUnlessDBFeature("has_select_for_update")
class CallCenterConcurrencyTests(TransactionTestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.ce = User.objects.create_user(email="first@example.test", role="CRE")
        self.other = User.objects.create_user(email="second@example.test", role="CRE")
        self.lead = Lead.objects.create(name="Concurrent customer", phone="9876543210", assigned_so=self.other)
        SystemConfig.objects.create(id=1, lists={"branches": ["Kochi"]})

    def race(self, actions):
        barrier = Barrier(len(actions))
        def run(action):
            try:
                client = APIClient()
                client.force_authenticate(action[0])
                barrier.wait(timeout=10)
                response = getattr(client, action[1])(action[2], action[3], format="json")
                return response.status_code, response.data
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            return list(pool.map(run, actions))

    def payload(self, **changes):
        return {"submission_id": str(uuid4()), "kind": "CALLBACK", "lead_id": self.lead.pk,
                "lead_version": self.lead.updated_at.isoformat(), "confirm_customer": True,
                "caller_phone": self.lead.phone, "reason": "Callback requested", "notes": "Please call",
                "callback_at": (timezone.now() + timedelta(hours=1)).isoformat(), **changes}

    def test_simultaneous_retry_creates_one_callback(self):
        action = (self.ce, "post", "/api/call-center/interactions/", self.payload())
        results = self.race([action, action])
        self.assertEqual([r[0] for r in results], [201, 201], results)
        self.assertEqual(results[0][1]["id"], results[1][1]["id"])
        self.assertEqual(FollowUp.objects.count(), 1)
        self.assertEqual(InboundInteraction.objects.count(), 1)

    def test_simultaneous_edits_detect_stale_record(self):
        url = f"/api/call-center/leads/{self.lead.pk}/"
        payload = {"submission_id": str(uuid4()), "lead_version": self.lead.updated_at.isoformat(), "name": "First edit"}
        results = self.race([(self.ce, "patch", url, payload), (self.other, "patch", url, {**payload, "submission_id": str(uuid4()), "name": "Second edit"})])
        self.assertEqual(sorted(r[0] for r in results), [200, 409], results)
        self.assertEqual(InboundInteraction.objects.count(), 1)
        self.assertFalse(CallLog.objects.exists())

    def test_concurrent_complaints_for_different_customers_have_unique_numbers(self):
        second = Lead.objects.create(name="Other customer", phone="9876543211", assigned_so=self.ce)
        details = {"category": "AFTER_SALES", "subtype": "No callback", "branch": "Kochi", "subject": "Please call", "description": "Waiting"}
        first_payload = self.payload(kind="COMPLAINT", complaint=details)
        second_payload = self.payload(kind="COMPLAINT", complaint=details, lead_id=second.pk, lead_version=second.updated_at.isoformat())
        results = self.race([(self.ce, "post", "/api/call-center/interactions/", first_payload), (self.other, "post", "/api/call-center/interactions/", second_payload)])
        self.assertEqual([r[0] for r in results], [201, 201], results)
        self.assertEqual(Complaint.objects.values("ticket_number").distinct().count(), 2)

    def test_personal_qualification_and_shared_edit_use_compatible_locks(self):
        ps = User.objects.create_user(email="qualifier-ps@example.test", role="SO", location="Kochi")
        owner = User.objects.create_user(email="qualifier-ce@example.test", role="CRE")
        self.lead.assigned_so = owner
        self.lead.city = "Kochi"
        self.lead.save()
        SystemConfig.objects.filter(pk=1).update(lists={"branches": ["Kochi"], "colorVariants": ["Blue"]})
        qualification = {"call_outcome": "QUALIFIED", "ps_officer_id": ps.pk, "city": "Kochi", "qualification": {"variant": "Blue"}}
        edit = {"submission_id": str(uuid4()), "lead_version": self.lead.updated_at.isoformat(), "email": "updated@example.test"}
        results = self.race([(owner, "patch", f"/api/leads/{self.lead.pk}/so-update/", qualification),
                             (self.ce, "patch", f"/api/call-center/leads/{self.lead.pk}/", edit)])
        self.assertTrue(all(code in {200, 409} for code, _ in results), results)
        self.assertTrue(any(code == 200 for code, _ in results), results)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assigned_so_id, owner.pk)
