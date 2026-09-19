from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from .metrics import etbr_aggregates
from .models import CallLog, FollowUp, Lead, LeadAudit
from .outcomes import CONNECTED, NOT_CONNECTED
from .serializers import SOLeadUpdateSerializer


class OutcomePolicyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.enterContext(patch("leads.views.LeadViewSet.throttle_classes", []))
        self.so = User.objects.create_user(email="outcomes-so@example.com", role=User.Role.SALES_OFFICER)
        self.cre = User.objects.create_user(email="outcomes-ce@example.com", role=User.Role.CRE)
        self.admin = User.objects.create_user(email="outcomes-admin@example.com", role=User.Role.ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.so)

    def lead(self, state="QUALIFIED", completed=False):
        lead = Lead.objects.create(
            name="Outcome customer", phone="9876543210", assigned_ps=self.so, assigned_so=self.cre,
            status=state, sales_outcome={"WALKIN": "BOOKED", "WON": "RETAILED", "LOST": "LOST"}.get(state, "PENDING"),
            test_drive_completed_at=timezone.now() if completed else None,
        )

        from servicing.models import Vehicle
        Vehicle.objects.create(chassis_number=f"OUTCOME-{lead.pk}", model="Indie", related_lead=lead, created_by=self.so, customer_name=lead.name, customer_phone=lead.phone)
        return lead

    def payload(self, call_status="Connected", outcome="Call Me Back", follow_up=True):
        return {"call_status": call_status, "call_outcome": outcome, "remarks": "Customer follow-up recorded.",
                "follow_up_at": (timezone.now() + timedelta(days=1)).isoformat() if follow_up else None}

    def update(self, lead, data, endpoint="so-update"):
        method = self.client.patch if endpoint == "so-update" else self.client.post
        return method(f"/api/leads/{lead.pk}/{endpoint}/", data, format="json")

    def test_every_outcome_against_milestones_and_contact_status(self):
        for state, completed in [("QUALIFIED", False), ("QUALIFIED", True), ("WALKIN", False), ("WALKIN", True), ("WON", True), ("LOST", True), ("UNQUALIFIED", False)]:
            for call_status, outcomes in (("Connected", CONNECTED), ("Not Connected", NOT_CONNECTED)):
                for outcome, expected_status in outcomes.items():
                    with self.subTest(state=state, completed=completed, call_status=call_status, outcome=outcome):
                        lead = self.lead(state, completed)
                        policy = self.client.get(f"/api/leads/{lead.pk}/").data["outcome_policy"]
                        allowed = state not in {"WON", "LOST", "UNQUALIFIED"} and outcome != "Need SO Call" and not (completed and outcome == "Need Test Drive") and not (state == "WALKIN" and outcome == "Booking Done")
                        self.assertEqual(outcome in [item["label"] for item in policy["outcomes"][call_status]], allowed)
                        data = self.payload(call_status, outcome, expected_status not in {"WON", "LOST"})
                        response = self.update(lead, data)
                        self.assertEqual(response.status_code, 200 if allowed else 400, response.data)
                        lead.refresh_from_db()
                        if allowed:
                            if state == "WALKIN" and expected_status not in {"WON", "LOST"}:
                                expected_status = "WALKIN"
                            self.assertEqual(lead.status, expected_status)
                            self.assertEqual(lead.sales_outcome, {"WALKIN": "BOOKED", "WON": "RETAILED", "LOST": "LOST"}.get(expected_status, "PENDING"))
                            self.assertEqual(lead.call_logs.get().call_status, call_status)
                        else:
                            self.assertEqual(lead.status, state)
                            self.assertFalse(lead.call_logs.exists())
                            self.assertFalse(lead.follow_ups.exists())
                        self.assertEqual(bool(lead.test_drive_completed_at), completed)

    def test_need_so_call_is_only_available_to_admin(self):
        for user in (self.so, self.admin):
            self.client.force_authenticate(user)
            for endpoint in ("so-update", "log-call"):
                with self.subTest(role=user.role, endpoint=endpoint):
                    lead = self.lead()
                    policy = self.client.get(f"/api/leads/{lead.pk}/").data["outcome_policy"]
                    self.assertEqual(
                        "Need SO Call" in [item["label"] for item in policy["outcomes"]["Connected"]],
                        user == self.admin,
                    )
                    response = self.update(lead, self.payload(outcome="Need SO Call"), endpoint)
                    self.assertEqual(response.status_code, 200 if user == self.admin else 400, response.data)
                    self.assertEqual(lead.call_logs.exists(), user == self.admin)
                    self.assertEqual(lead.follow_ups.exists(), user == self.admin)

    def test_wrong_contact_pairings_and_missing_fields_are_atomic(self):
        lead = self.lead("WALKIN", True)
        existing = FollowUp.objects.create(lead=lead, so=self.so, scheduled_for=timezone.now() + timedelta(days=1))
        invalid = [
            self.payload("Not Connected", outcome, False) for outcome in CONNECTED
        ] + [self.payload("Connected", outcome) for outcome in NOT_CONNECTED]
        invalid += [
            {**self.payload(), "call_status": ""}, {**self.payload(), "remarks": " "},
            {**self.payload(), "call_outcome": "invented"}, self.payload(follow_up=False),
            {**self.payload(), "status": "PENDING"}, {**self.payload(), "sales_outcome": "PENDING"},
            {**self.payload(), "follow_up_at": (timezone.now() - timedelta(days=1)).isoformat()},
            {**self.payload(), "follow_up_at": (timezone.now() + timedelta(days=4)).isoformat()},
            self.payload(outcome="Retail Done", follow_up=True),
        ]
        for data in invalid:
            with self.subTest(data=data):
                self.assertEqual(self.update(lead, data).status_code, 400)
        lead.refresh_from_db()
        existing.refresh_from_db()
        self.assertEqual((lead.status, lead.sales_outcome), ("WALKIN", "BOOKED"))
        self.assertIsNone(existing.resolved_at)
        self.assertFalse(CallLog.objects.filter(lead=lead).exists())
        self.assertFalse(LeadAudit.objects.filter(lead=lead).exists())

    def test_booked_counts_survive_retries_and_loss_or_retail_are_explicit(self):
        lead = self.lead("WALKIN", True)
        for call_status, outcome in [("Connected", "Call Me Back"), ("Not Connected", "RNR"), ("Not Connected", "No Response")]:
            self.assertEqual(self.update(lead, self.payload(call_status, outcome)).status_code, 200)
            self.assertEqual(Lead.objects.filter(pk=lead.pk).aggregate(**etbr_aggregates())["etbr_booked"], 1)
            self.assertEqual(lead.follow_ups.filter(resolved_at__isnull=True).count(), 1)
        self.assertEqual(self.update(lead, self.payload(outcome="Not Interested", follow_up=False)).status_code, 200)
        self.assertFalse(lead.follow_ups.filter(resolved_at__isnull=True).exists())
        self.assertEqual(self.update(self.lead("WALKIN"), self.payload(outcome="Retail Done", follow_up=False)).status_code, 200)

    def test_completion_idempotency_closed_leads_and_stale_outcomes(self):
        lead = self.lead()
        path = f"/api/leads/{lead.pk}/complete-test-drive/"
        first = self.client.post(path)
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.data["outcome_policy"]["can_complete_test_drive"])
        self.assertEqual(self.client.post(path).data["test_drive_completed_at"], first.data["test_drive_completed_at"])
        self.assertEqual(lead.audit_events.filter(event="test_drive_completed").count(), 1)
        self.assertEqual(self.update(lead, self.payload(outcome="Need Test Drive")).status_code, 400)
        for state in ("WON", "LOST", "UNQUALIFIED"):
            closed = self.lead(state)
            self.assertEqual(self.client.post(f"/api/leads/{closed.pk}/complete-test-drive/").status_code, 400)
        self.assertEqual(self.update(lead, self.payload(outcome="Retail Done", follow_up=False)).status_code, 200)
        self.assertEqual(self.client.post(path).data["test_drive_completed_at"], first.data["test_drive_completed_at"])

    def test_other_interfaces_cannot_bypass_progress_or_role(self):
        lead = self.lead(completed=True)
        for user in (self.so, self.cre, self.admin):
            self.client.force_authenticate(user)
            for endpoint in ("so-update", "log-call"):
                with self.subTest(user=user.role, endpoint=endpoint):
                    response = self.update(lead, {**self.payload(outcome="Need Test Drive"), "status": "PENDING"}, endpoint)
                    self.assertEqual(response.status_code, 400, response.data)
            self.assertEqual(self.client.patch(f"/api/leads/{lead.pk}/", {"status": "WON"}, format="json").status_code, 400)
        self.client.force_authenticate(self.so)
        self.assertEqual(self.update(lead, self.payload("Not Connected", "No Response"), "log-call").status_code, 200)
        self.client.force_authenticate(self.cre)
        policy = self.client.get(f"/api/leads/{lead.pk}/").data["outcome_policy"]
        self.assertEqual(policy["outcomes"], {"Connected": [], "Not Connected": []})
        self.assertFalse(policy["can_complete_test_drive"])

    def test_change_between_validation_and_lock_returns_conflict(self):
        lead = self.lead()
        original = SOLeadUpdateSerializer.is_valid

        def complete_during_validation(serializer, *args, **kwargs):
            result = original(serializer, *args, **kwargs)
            Lead.objects.filter(pk=lead.pk).update(test_drive_completed_at=timezone.now(), updated_at=timezone.now())
            return result

        with patch.object(SOLeadUpdateSerializer, "is_valid", complete_during_validation):
            response = self.update(lead, self.payload(outcome="Need Test Drive"))
        self.assertEqual(response.status_code, 409)
        self.assertFalse(lead.call_logs.exists())
        self.assertFalse(lead.follow_ups.exists())

    def test_explicit_reopen_resets_sales_state_and_keeps_test_drive(self):
        lead = self.lead("LOST", True)
        self.client.force_authenticate(self.admin)
        response = self.client.post(f"/api/leads/{lead.pk}/reopen/")
        self.assertEqual(response.status_code, 200)
        lead.refresh_from_db()
        self.assertEqual((lead.status, lead.sales_outcome), ("QUALIFIED", "PENDING"))
        self.assertIsNotNone(lead.test_drive_completed_at)
