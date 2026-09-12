from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from leads.models import Lead, LeadAudit
from .models import WhatsAppContact, WhatsAppMessage
from .whatsapp import normalize_phone, record_lead_audit, send_whatsapp_message, whatsapp_mode


@override_settings(WHATSAPP_MODE="preview", WHATSAPP_BUSINESS_NAME="Example Motors")
class WhatsAppWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.cre = User.objects.create_user("cre@whatsapp.test", role=User.Role.CRE)
        cls.admin = User.objects.create_user("admin@whatsapp.test", role=User.Role.ADMIN)
        cls.so = User.objects.create_user("so@whatsapp.test", role=User.Role.SALES_OFFICER,
            first_name="Asha", last_name="Nair", phone="9876543210", location="Kochi")
        cls.other_so = User.objects.create_user("other@whatsapp.test", role=User.Role.SALES_OFFICER,
            first_name="Ravi", phone="+91 98765 43211", location="Kochi")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.cre)
        self.lead = Lead.objects.create(name="Customer", phone="9123456789", assigned_so=self.cre, branch="Kochi")

    def qualify(self, agreed=True, **overrides):
        response = self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {
            "call_outcome": "QUALIFIED", "city": "Kochi", "ps_officer_id": self.so.pk,
            "whatsapp_agreed": agreed, **overrides,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.lead.refresh_from_db()
        return response

    def agree(self, agreed):
        return self.client.patch(f"/api/leads/{self.lead.pk}/whatsapp-agreement/", {"agreed": agreed}, format="json")

    def reassign(self, so):
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/leads/{self.lead.pk}/", {"ps_officer_id": so.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.lead.refresh_from_db()

    def test_qualification_previews_exact_customer_and_so_details_without_sending(self):
        with patch("notifications.whatsapp.send_whatsapp_message") as send:
            response = self.qualify()
        send.assert_not_called()
        message = WhatsAppMessage.objects.get()
        self.assertEqual(message.status, "PREVIEW")
        self.assertEqual(message.mode, "preview")
        self.assertEqual(message.recipient, "+919123456789")
        self.assertEqual(message.variables, {"customer_name": "Customer", "business_name": "Example Motors", "so_name": "Asha Nair", "so_phone": "+919876543210"})
        self.assertIn("Your Sales Officer, Asha Nair, will contact you", message.body)
        self.assertEqual(response.data["whatsapp"]["messages"][0]["status_label"], "Preview only — not sent")
        contact = WhatsAppContact.objects.get()
        self.assertTrue(contact.agreed)
        self.assertEqual(contact.recorded_by, self.cre)
        self.assertIsNotNone(contact.enrolled_at)
        self.assertEqual(contact.phone, message.recipient)

    def test_no_agreement_is_optional_and_audited_as_skipped(self):
        self.qualify(agreed=False)
        self.assertEqual(self.lead.status, Lead.Status.QUALIFIED)
        message = WhatsAppMessage.objects.get()
        self.assertEqual(message.status, "SKIPPED")
        self.assertIn("agreement not recorded", message.reason)

    def test_old_client_without_agreement_field_does_not_opt_in(self):
        response = self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {
            "call_outcome": "QUALIFIED", "city": "Kochi", "ps_officer_id": self.so.pk,
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(WhatsAppMessage.objects.get().status, "SKIPPED")
        self.assertFalse(WhatsAppContact.objects.get().agreed)

    def test_duplicate_qualification_and_replayed_event_do_not_duplicate_preview(self):
        self.qualify()
        message = WhatsAppMessage.objects.get()
        response = self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {
            "call_outcome": "QUALIFIED", "ps_officer_id": self.so.pk,
        }, format="json")
        self.assertEqual(response.status_code, 400)
        record_lead_audit(message.source_audit)
        self.reassign(self.so)
        self.assertEqual(WhatsAppMessage.objects.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            message.pk = None
            message.save(force_insert=True)

    def test_assignment_a_b_a_creates_distinct_updates_and_cancels_old_previews(self):
        self.qualify()
        original_audit = WhatsAppMessage.objects.get().source_audit
        self.reassign(self.other_so)
        self.reassign(self.so)
        record_lead_audit(original_audit)
        messages = list(WhatsAppMessage.objects.all())
        self.assertEqual(len(messages), 3)
        self.assertEqual([item.kind for item in messages], ["REASSIGNMENT", "REASSIGNMENT", "INTRODUCTION"])
        self.assertEqual([item.status for item in messages], ["PREVIEW", "CANCELLED", "CANCELLED"])
        self.assertEqual(messages[0].so, self.so)
        self.assertEqual(messages[1].variables["so_name"], "Ravi")

    def test_individual_and_bulk_assignment_use_same_trigger(self):
        self.qualify()
        self.client.force_authenticate(self.admin)
        for endpoint, so in ((f"{self.lead.pk}/assign-ps", self.other_so), ("bulk-assign-ps", self.so)):
            Lead.objects.filter(pk=self.lead.pk).update(assigned_ps=None)
            response = self.client.post(f"/api/leads/{endpoint}/", {"sales_officer_id": so.pk, "filters": {}}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(WhatsAppMessage.objects.count(), 3)
        self.assertEqual(WhatsAppMessage.objects.first().so, self.so)

    def test_offboarding_and_pool_reassignment_generate_updates(self):
        self.qualify()
        self.client.force_authenticate(self.admin)
        impact = self.client.get(f"/api/auth/users/{self.so.pk}/offboarding-impact/").data
        response = self.client.post(f"/api/auth/users/{self.so.pk}/disable/", {
            "impact_version": impact["version"], "reason": "Leaving branch",
            "routes": [{"status": "QUALIFIED", "destination": "DISTRIBUTE", "recipient_ids": [self.other_so.pk]}],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(WhatsAppMessage.objects.first().so, self.other_so)
        impact = self.client.get(f"/api/auth/users/{self.other_so.pk}/offboarding-impact/").data
        response = self.client.post(f"/api/auth/users/{self.other_so.pk}/disable/", {
            "impact_version": impact["version"], "routes": [{"status": "QUALIFIED", "destination": "POOL", "recipient_ids": []}],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(WhatsAppMessage.objects.filter(status="PREVIEW").exists())
        User.objects.filter(pk=self.so.pk).update(is_active=True)
        response = self.client.post("/api/leads/bulk-reassign/", {
            "role": "SO", "lead_ids": [self.lead.pk], "recipient_ids": [self.so.pk],
        }, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(WhatsAppMessage.objects.count(), 3)
        self.assertEqual(WhatsAppMessage.objects.first().status, "PREVIEW")

    def test_agreement_withdrawal_cancels_and_future_assignment_is_skipped(self):
        self.qualify()
        response = self.agree(False)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(WhatsAppMessage.objects.get().status, "CANCELLED")
        self.reassign(self.other_so)
        self.assertEqual(WhatsAppMessage.objects.first().status, "SKIPPED")
        self.assertEqual(self.agree(True).status_code, 200)
        self.assertEqual(WhatsAppMessage.objects.count(), 2)  # Agreement alone never replays an old introduction.
        self.assertEqual(self.lead.audit_events.filter(event="whatsapp_agreement").count(), 3)

    def test_phone_edit_clears_agreement_in_both_edit_paths(self):
        self.qualify()
        for endpoint, number in (("so-update/", "9000000001"), ("", "9000000002")):
            self.client.force_authenticate(self.admin)
            response = self.client.patch(f"/api/leads/{self.lead.pk}/{endpoint}", {"phone": number}, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            contact = WhatsAppContact.objects.get()
            self.assertFalse(contact.agreed)
            self.assertEqual(contact.phone, "+91" + number)
            self.assertEqual(WhatsAppMessage.objects.get().status, "CANCELLED")
            self.assertEqual(self.agree(True).status_code, 200)

    def test_fresh_agreement_can_be_recorded_with_a_number_change(self):
        self.qualify(phone="9000000003")
        self.assertEqual(WhatsAppMessage.objects.get().recipient, "+919000000003")
        self.assertTrue(WhatsAppContact.objects.get().agreed)

    def test_closed_and_deleted_leads_cancel_previews_and_skip_assignment_messages(self):
        self.qualify()
        self.client.force_authenticate(self.admin)
        response = self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {"call_outcome": "LOST", "status": "LOST"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.reassign(self.other_so)
        self.assertEqual(WhatsAppMessage.objects.count(), 1)
        self.assertEqual(WhatsAppMessage.objects.get().status, "CANCELLED")
        self.assertEqual(self.client.delete(f"/api/leads/{self.lead.pk}/").status_code, 204)
        self.assertEqual(self.client.get(f"/api/leads/{self.lead.pk}/").status_code, 404)

    def test_invalid_so_details_skip_without_failing_qualification(self):
        for fields in ({"phone": ""}, {"phone": "invalid"}, {"first_name": "", "last_name": ""}):
            with self.subTest(fields=fields), transaction.atomic():
                User.objects.filter(pk=self.so.pk).update(**fields)
                self.qualify()
                self.assertEqual(WhatsAppMessage.objects.get().status, "SKIPPED")
                self.assertIn("full name and valid contact", WhatsAppMessage.objects.get().reason)
                transaction.set_rollback(True)

    def test_missing_customer_number_and_inactive_so_are_never_previewed(self):
        self.qualify()
        Lead.objects.filter(pk=self.lead.pk).update(phone="bad")
        User.objects.filter(pk=self.other_so.pk).update(is_active=False)
        with transaction.atomic():
            lead = Lead.objects.select_for_update().get(pk=self.lead.pk)
            lead.assigned_ps = self.other_so
            lead.save(update_fields=["assigned_ps"])
            LeadAudit.objects.create(lead=lead, event="assigned_ps", after={"assigned_ps": self.other_so.pk})
        self.assertEqual(WhatsAppMessage.objects.first().status, "SKIPPED")

    def test_imported_walkin_and_self_generated_leads_are_not_enrolled(self):
        self.client.force_authenticate(self.admin)
        for fields in ({}, {"source": "WALKIN"}, {"generated_by": self.so}):
            lead = Lead.objects.create(name="Existing", phone="9000000001", status="QUALIFIED", **fields)
            LeadAudit.objects.create(lead=lead, event="imported", after={"status": "QUALIFIED"})
            response = self.client.patch(f"/api/leads/{lead.pk}/", {"ps_officer_id": self.so.pk}, format="json")
            self.assertEqual(response.status_code, 200)
            self.assertFalse(WhatsAppContact.objects.filter(lead=lead, enrolled_at__isnull=False).exists())
        self.assertEqual(WhatsAppMessage.objects.count(), 0)

    def test_permission_and_history_are_limited_to_authorized_lead_users(self):
        self.qualify()
        for role in (User.Role.CRE, User.Role.SALES_OFFICER, User.Role.SALES_MANAGER, User.Role.CEO):
            user = User.objects.create_user(f"{role}@outsider.test", role=role, location="Kochi")
            self.client.force_authenticate(user)
            response = self.agree(False)
            self.assertIn(response.status_code, {403, 404})
            if role != User.Role.SALES_MANAGER:
                self.assertEqual(self.client.get(f"/api/leads/{self.lead.pk}/").status_code, 404)
        self.client.force_authenticate(self.so)
        detail = self.client.get(f"/api/leads/{self.lead.pk}/").data
        self.assertFalse(detail["whatsapp"]["can_record_agreement"])
        self.assertEqual(len(detail["whatsapp"]["messages"]), 1)
        self.assertEqual(self.agree(False).status_code, 403)
        self.assertEqual(self.client.patch(f"/api/leads/{self.lead.pk}/so-update/", {"whatsapp_agreed": False}, format="json").status_code, 400)
        self.client.force_authenticate(self.admin)
        self.assertEqual(self.agree(False).status_code, 200)

    def test_qualification_and_agreement_roll_back_together(self):
        with transaction.atomic():
            self.qualify()
            transaction.set_rollback(True)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "FRESH")
        self.assertFalse(WhatsAppMessage.objects.exists())
        self.assertFalse(WhatsAppContact.objects.exists())

    @override_settings(WHATSAPP_MODE="disabled")
    def test_disabled_mode_records_skip_and_preview_can_never_be_sent(self):
        self.qualify()
        self.assertEqual(WhatsAppMessage.objects.get().reason, "WhatsApp automation is disabled.")
        with self.assertRaises(ImproperlyConfigured):
            send_whatsapp_message(WhatsAppMessage.objects.get())

    def test_live_mode_rejected_and_history_never_released(self):
        self.qualify()
        with override_settings(WHATSAPP_MODE="live"), self.assertRaises(ImproperlyConfigured):
            whatsapp_mode()
        with self.assertRaises(ImproperlyConfigured):
            send_whatsapp_message(WhatsAppMessage.objects.get())
        self.assertEqual(WhatsAppMessage.objects.get().status, "PREVIEW")

    def test_phone_normalization(self):
        for raw, expected in (("9876543210", "+919876543210"), ("91 98765-43210", "+919876543210"), ("+44 7911 123456", "+447911123456"), ("123", ""), ("letters", ""), ("+00000000000", "")):
            self.assertEqual(normalize_phone(raw), expected)
